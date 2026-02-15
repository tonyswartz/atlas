#!/usr/bin/env python3
"""Bambu printer watcher.

Goals:
- Notify Bambu Telegram group when a new print starts (file name + start time)
- Detect print completion
- Pull latest *.gcode.3mf from printer via FTPS (port 990)
- Parse Metadata/slice_info.config for filament type/color and grams used
- Write a pending prompt entry (including parsed fields) for Telegram poller
- Append basic log entries to Obsidian Bambu/Print Log.md

Notes:
- Bambu printers expose implicit FTPS on port 990 (user=bblp, pass=access code)
- The .gcode.3mf is a ZIP; slice_info.config contains used_g + type + color
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import yaml
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.credentials import get_telegram_token

VAULT = Path.home() / "Library/CloudStorage/Dropbox/Obsidian/Tony's Vault"
PRINT_LOG = VAULT / "Bambu" / "Print Log.md"
STATE_FILE = Path("/Users/printer/atlas/data/bambu_last_state.json")
LOG_PATH = Path("/Users/printer/atlas/logs/bambu-watcher.log")
PROMPT_FILE = Path("/Users/printer/atlas/memory/bambu-pending-prompts.md")
BAMBU_GROUP_CONFIG = Path("/Users/printer/atlas/args/bambu_group.yaml")

BAMBU_IP = "192.168.4.159"
ACCESS_CODE_FILE = Path("/Users/printer/.config/bambu/p2s.code")

STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    LOG_PATH.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")


def sh(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return p.returncode, p.stdout


def load_access_code() -> str:
    return ACCESS_CODE_FILE.read_text(encoding="utf-8").strip()


def get_ams_status() -> dict | None:
    """Get AMS tray info via bambu-cli --json. Returns structured tray list."""
    rc, out = sh(["/opt/homebrew/bin/bambu-cli", "--json", "ams", "status"], timeout=15)
    if rc != 0:
        log(f"bambu-cli ams status failed: {out[:200]}")
        return None

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        log("bambu-cli ams --json returned unparseable output")
        return None

    # Flatten: extract trays from nested ams[].tray[] structure
    trays = []
    for ams_unit in data.get("ams", {}).get("ams", []):
        for tray in ams_unit.get("tray", []):
            trays.append({
                "tray": tray.get("id", ""),
                "name": tray.get("tray_id_name", ""),
                "type": tray.get("tray_type", ""),
                "color": (tray.get("tray_color") or "")[:6].upper(),
                "remain": tray.get("remain"),
                "state": tray.get("state"),
            })

    if not trays:
        return None

    return {"trays": trays, "detected_at": datetime.now().isoformat()}


def get_printer_status() -> dict | None:
    """Get current printer status via bambu-cli --json."""
    rc, out = sh(["/opt/homebrew/bin/bambu-cli", "--json", "status"], timeout=15)
    if rc != 0:
        log(f"bambu-cli status failed: {out[:200]}")
        return None

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        log("bambu-cli status --json returned unparseable output")
        return None

    return {
        "state": data.get("gcode_state", ""),
        "progress": str(data.get("percent", 0)),
        "file": data.get("file", ""),
        "error": str(data.get("error_code", 0)),
    }


def load_bambu_group_config() -> dict:
    """Load Bambu group config for Telegram chat_id."""
    if not BAMBU_GROUP_CONFIG.exists():
        return {}
    try:
        with BAMBU_GROUP_CONFIG.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log(f"Failed to load bambu_group config: {e}")
        return {}


def send_telegram_to_bambu_group(message: str) -> bool:
    """Send a message to the Bambu Telegram group (same group used for completion prompts)."""
    import urllib.request
    import urllib.error

    token = get_telegram_token()
    if not token:
        log("TELEGRAM_BOT_TOKEN not found; skipping print-start notification")
        return False

    config = load_bambu_group_config()
    if not config.get("enabled"):
        log("Bambu group disabled; skipping print-start notification")
        return False

    chat_id = (config.get("chat_id") or "").strip()
    if not chat_id or chat_id == "CHAT_ID_HERE":
        log("Bambu group chat_id not set; skipping print-start notification")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        log(f"Failed to send Telegram: {e}")
        return False


def load_last_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_last_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_print_log(title: str, lines: list[str]) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M")
    entry = "\n".join([f"### {ts}", f"- **Print**: {title}"] + [f"- {l}" for l in lines] + [""])
    if PRINT_LOG.exists():
        existing = PRINT_LOG.read_text(encoding="utf-8")
        if existing.strip():
            PRINT_LOG.write_text(entry + "\n" + existing, encoding="utf-8")
        else:
            PRINT_LOG.write_text(entry, encoding="utf-8")
    else:
        PRINT_LOG.parent.mkdir(parents=True, exist_ok=True)
        PRINT_LOG.write_text("# Bambu Print Log\n\n" + entry, encoding="utf-8")


def ftp_list_gcode_3mf() -> list[dict]:
    """List root directory over FTPS and return entries with name + dt."""
    code = load_access_code()
    rc, out = sh(["curl", "-k", "--ssl-reqd", "--user", f"bblp:{code}", f"ftps://{BAMBU_IP}/"], timeout=20)
    if rc != 0:
        log(f"FTPS list failed rc={rc}: {out[:200]}")
        return []

    entries = []
    # Example line:
    # -rwxr-xr-x    1 103      107        762026 Jan 26 18:22 Foo.gcode.3mf
    pat = re.compile(r"\s([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2})\s+(.+)$")
    for line in out.splitlines():
        m = pat.search(line)
        if not m:
            continue
        mon, day, hhmm, name = m.group(1), m.group(2), m.group(3), m.group(4)
        if not name.lower().endswith(".gcode.3mf"):
            continue
        # We don't get year; assume current year.
        year = datetime.now().year
        try:
            dt = datetime.strptime(f"{year} {mon} {day} {hhmm}", "%Y %b %d %H:%M")
        except Exception:
            dt = None
        entries.append({"name": name, "dt": dt})

    entries.sort(key=lambda e: e["dt"] or datetime.min, reverse=True)
    return entries


def ftp_download(name: str, out_path: Path) -> bool:
    code = load_access_code()
    rc, out = sh(["curl", "-k", "--ssl-reqd", "--user", f"bblp:{code}", f"ftps://{BAMBU_IP}/{name}", "-o", str(out_path)], timeout=30)
    if rc != 0:
        log(f"FTPS download failed rc={rc}: {out[:200]}")
        return False
    return True


def parse_slice_info_from_3mf(path: Path) -> dict | None:
    """Extract filament material/color and grams used from Metadata/slice_info.config."""
    import zipfile

    try:
        with zipfile.ZipFile(path, "r") as z:
            data = z.read("Metadata/slice_info.config")
    except Exception as e:
        log(f"Failed to read slice_info.config from 3mf: {e}")
        return None

    try:
        root = ET.fromstring(data)
    except Exception as e:
        log(f"Failed to parse slice_info.config XML: {e}")
        return None

    # Find first filament node
    filament_el = root.find(".//filament")
    if filament_el is None:
        return None

    material = filament_el.attrib.get("type")
    color = filament_el.attrib.get("color")  # like #FFFFFF
    used_g = filament_el.attrib.get("used_g")
    used_m = filament_el.attrib.get("used_m")

    return {
        "material": material,
        "color": color.lstrip("#") if isinstance(color, str) else None,
        "used_g": float(used_g) if used_g else None,
        "used_m": float(used_m) if used_m else None,
    }


def write_pending_prompt(print_title: str, source_file: str | None = None) -> None:
    """Write a minimal pending prompt (print name + timestamp). Spool/grams/who asked via Telegram."""
    ts = datetime.now().strftime("%y-%m-%d %H:%M")
    PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not PROMPT_FILE.exists():
        PROMPT_FILE.write_text("# Bambu Pending Prompts\n\n", encoding="utf-8")
    else:
        existing = PROMPT_FILE.read_text(encoding="utf-8").strip()
        if existing == "(see attached image)":
            PROMPT_FILE.write_text("# Bambu Pending Prompts\n\n", encoding="utf-8")

    parts = [
        "---",
        f'timestamp: "{ts}"',
        f'print_name: "{print_title}"',
    ]
    if source_file:
        parts.append(f'source_file: "{source_file}"')
    parts.append("status: pending")
    parts.append("target: jeevesui")
    parts.append("---")

    base = PROMPT_FILE.read_text(encoding="utf-8")
    if base and not base.endswith("\n"):
        base += "\n"
    PROMPT_FILE.write_text(base + "\n".join(parts) + "\n", encoding="utf-8")
    log(f"Queued prompt for {print_title}")


def find_best_spool_for_filament(material: str, color: str | None, ams_trays: list[dict] | None) -> str | None:
    """Find the best matching spool from JeevesUI based on filament material and color."""
    import urllib.request
    import json

    try:
        url = "http://localhost:6001/api/filament/spools"
        with urllib.request.urlopen(url, timeout=10) as resp:
            spools = json.loads(resp.read().decode())
    except Exception as e:
        log(f"Failed to fetch spools from JeevesUI: {e}")
        return None

    if not spools:
        return None

    def normalize_hex(h):
        if not h:
            return None
        h = h.strip().lstrip("#").upper()
        return h[:6] if len(h) >= 6 else None

    def hex_to_rgb(h):
        h = normalize_hex(h)
        if not h or len(h) < 6:
            return None
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except:
            return None

    def color_distance(a, b):
        ra = hex_to_rgb(a)
        rb = hex_to_rgb(b)
        if not ra or not rb:
            return 10**9
        return (ra[0]-rb[0])**2 + (ra[1]-rb[1])**2 + (ra[2]-rb[2])**2

    filament_color = normalize_hex(color)

    # If we have AMS trays, try to match both AMS tray color and JeevesUI spool color
    if ams_trays and filament_color:
        best_spool = None
        best_dist = 10**9

        for spool in spools:
            spool_mat = (spool.get("filament") or {}).get("material", "").upper()
            if spool_mat != material.upper():
                continue

            sp_hex = normalize_hex((spool.get("filament") or {}).get("colorHex"))
            if not sp_hex:
                continue

            for tray in ams_trays:
                if tray.get("type", "").upper() != material.upper():
                    continue
                tray_color = tray.get("color", "")

                # Distance: tray to filament color + spool to filament color
                tray_dist = color_distance(filament_color, tray_color)
                spool_dist = color_distance(filament_color, sp_hex)
                total_dist = tray_dist + spool_dist

                if total_dist < best_dist:
                    best_dist = total_dist
                    best_spool = spool

        if best_spool:
            return best_spool.get("id")

    # Fallback: just match by material and closest color
    candidates = [s for s in spools if (s.get("filament") or {}).get("material", "").upper() == material.upper()]
    if filament_color and candidates:
        candidates = sorted(candidates, key=lambda s: color_distance(
            filament_color,
            normalize_hex((s.get("filament") or {}).get("colorHex")) or "FFFFFF"
        ))

    return candidates[0].get("id") if candidates else None


def log_to_jeevesui(spool_id: str, user_name: str, filename: str, material_used_g: float) -> bool:
    """Record print job to JeevesUI API."""
    import urllib.request
    import urllib.error

    url = "http://localhost:6001/api/filament/print-jobs"
    data = {
        "spoolId": spool_id,
        "userName": user_name,
        "filename": filename,
        "materialUsedG": material_used_g,
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log(f"JeevesUI API response: {resp.status}")
            return True
    except urllib.error.URLError as e:
        log(f"JeevesUI API error: {e}")
        return False


def main() -> int:
    cur = get_printer_status()
    if not cur:
        return 1

    last = load_last_state()

    state = (cur.get("state") or "").upper()
    prog = cur.get("progress") or "0"
    file_path = cur.get("file") or ""

    # gcode_state from --json: PRINTING, PAUSE, FINISH, IDLE, etc.
    # is_printing when state indicates active work and progress < 100
    try:
        pct = int(prog)
    except ValueError:
        pct = 0
    is_printing_now = state in ("PRINTING", "PAUSE") or (pct < 100 and state not in ("FINISH", "IDLE", "UNKNOWN", ""))
    was_printing = bool(last.get("is_printing"))

    # Notify Bambu group when a new print starts (transition: was idle -> now printing)
    if not was_printing and is_printing_now and file_path:
        filename = file_path.split("/")[-1] if "/" in file_path else file_path
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"🖨️ Print started: {filename}\nStarted at {started_at}"
        if send_telegram_to_bambu_group(msg):
            log(f"Sent print-start notification for {filename}")

    # Persist last seen info
    last_completed = last.get("last_completed_print") or ""
    last_completed_at_raw = last.get("last_completed_at")  # ISO or "yy-mm-dd HH:MM:SS"
    last_completed_at: datetime | None = None
    if last_completed_at_raw:
        try:
            if "T" in str(last_completed_at_raw):
                last_completed_at = datetime.fromisoformat(last_completed_at_raw.replace("Z", "+00:00"))
            else:
                last_completed_at = datetime.strptime(last_completed_at_raw, "%y-%m-%d %H:%M:%S")
        except Exception:
            pass

    def try_handle_completion() -> tuple[str, datetime | None] | None:
        """If FTP has a new completion vs last_completed, queue prompt and return (latest_name, latest_dt). Else return None (no entries or duplicate)."""
        entries = ftp_list_gcode_3mf()
        if not entries:
            return None
        latest = entries[0]["name"]
        latest_dt = entries[0].get("dt")
        skip_as_duplicate = False
        if latest == last_completed and last_completed_at:
            # Same filename: Only treat as new if BOTH:
            # 1. File timestamp is newer than what we logged (actual re-print), AND
            # 2. We actually saw a print happen (was_printing was True recently)
            # Otherwise: it's the same old completed print sitting in FINISH state.
            if latest_dt and latest_dt > last_completed_at + timedelta(minutes=5):
                # File timestamp is clearly newer - this is a re-print
                skip_as_duplicate = False
            else:
                # Same file, same timestamp - duplicate
                skip_as_duplicate = True
        if skip_as_duplicate:
            log(f"Skipping duplicate completion for {latest} (already logged)")
            return None
        write_pending_prompt(latest, source_file=latest)
        return (latest, latest_dt)

    # Detect completion: (1) transition was printing -> now finished, or (2) fallback: we're FINISH@100% but missed the transition
    if was_printing and not is_printing_now:
        result = try_handle_completion()
        if result is not None:
            last_completed, last_completed_at = result[0], result[1] or datetime.now()
        else:
            # None = no FTP entries or duplicate. Only early-exit when FTP list is empty (avoid overwriting state).
            if not ftp_list_gcode_3mf():
                save_last_state({
                    "last_seen_at": datetime.now().strftime("%y-%m-%d %H:%M:%S"),
                    "state": cur.get("state"),
                    "progress": cur.get("progress"),
                    "file": file_path,
                    "is_printing": is_printing_now,
                    "last_completed_print": last_completed,
                    "last_completed_at": last.get("last_completed_at"),
                })
                return 0
            # Duplicate: keep last_completed, fall through to save state
    elif not is_printing_now and state == "FINISH" and pct >= 100:
        # Fallback: missed transition (e.g. watcher didn't run during print, or machine was asleep)
        result = try_handle_completion()
        if result is not None:
            last_completed, last_completed_at = result[0], result[1] or datetime.now()
            log("Detected completion via FINISH fallback (missed transition)")

    # Build state to save (include last_completed_at when we have it)
    state_to_save = {
        "last_seen_at": datetime.now().strftime("%y-%m-%d %H:%M:%S"),
        "state": cur.get("state"),
        "progress": cur.get("progress"),
        "file": file_path,
        "is_printing": is_printing_now,
        "last_completed_print": last_completed,
    }
    if last_completed:
        state_to_save["last_completed_at"] = (last_completed_at if last_completed_at else datetime.now()).strftime("%y-%m-%d %H:%M:%S")
    elif last.get("last_completed_at"):
        state_to_save["last_completed_at"] = last["last_completed_at"]
    save_last_state(state_to_save)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
