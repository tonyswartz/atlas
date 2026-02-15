#!/usr/bin/env python3
"""Send Bambu completion prompts to Tony, with Spoolman options filtered by material + color.

Flow:
- Bambu watcher writes pending entries to memory/bambu-pending-prompts.md, including:
  - filament_material (e.g. PLA)
  - filament_color_hex (e.g. FFFFFF)
  - filament_used_g
- This poller reads pending entries, fetches spools from Spoolman, filters them, and sends a Telegram prompt.
- It also writes the exact options it presented to memory/bambu-last-options.json so the reply handler can map numbers.
"""

from __future__ import annotations

import json
import os
import re
import sys
import yaml
from datetime import datetime
from pathlib import Path

# Add parent directory to path for common imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from common.credentials import get_telegram_token

PROMPT_FILE = Path("/Users/printer/atlas/memory/bambu-pending-prompts.md")
OPTIONS_FILE = Path("/Users/printer/atlas/memory/bambu-last-options.json")
LOG_FILE = Path("/Users/printer/atlas/logs/bambu-prompt-poller.log")
CONFIG_FILE = Path("/Users/printer/atlas/args/bambu_group.yaml")
JEEVESUI_URL = "http://localhost:6001"
TELEGRAM_TARGET = "8241581699"  # Fallback individual chat


def log(msg: str) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    LOG_FILE.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")


def load_config() -> dict:
    """Load Bambu group configuration."""
    try:
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        log(f"Failed to load config: {e}")
    return {}


def get_target_chat_id() -> str:
    """Get target chat ID from config (group if enabled, else individual)."""
    config = load_config()
    if config.get("enabled"):
        chat_id = config.get("chat_id", "").strip()
        if chat_id and chat_id != "CHAT_ID_HERE":
            log(f"Using group chat: {chat_id}")
            return chat_id
    return TELEGRAM_TARGET


def get_spools(material: str | None) -> list[dict]:
    """Fetch spools from JeevesUI; if material provided, filter by filament.material."""
    import urllib.request

    url = f"{JEEVESUI_URL}/api/filament/spools"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            if not isinstance(data, list):
                return []
            # Filter by material if provided
            if material:
                data = [s for s in data if (s.get("filament") or {}).get("material", "").upper() == material.upper()]
            return data
    except Exception as e:
        log(f"Failed to fetch spools from JeevesUI: {e}")
        return []


def normalize_hex(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip().lstrip("#")
    return s.upper()


def hex_to_rgb(h: str | None) -> tuple[int, int, int] | None:
    h = normalize_hex(h)
    if not h or len(h) < 6:
        return None
    h = h[:6]
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return None


# Basic, human-friendly color names (CSS-ish). We pick nearest by RGB distance.
COLOR_PALETTE: list[tuple[str, str]] = [
    ("000000", "black"),
    ("FFFFFF", "white"),
    ("808080", "gray"),
    ("C0C0C0", "silver"),
    ("800000", "maroon"),
    ("FF0000", "red"),
    ("800080", "purple"),
    ("FF00FF", "magenta"),
    ("008000", "green"),
    ("00FF00", "lime"),
    ("808000", "olive"),
    ("FFFF00", "yellow"),
    ("000080", "navy"),
    ("0000FF", "blue"),
    ("008080", "teal"),
    ("00FFFF", "cyan"),
    ("FFA500", "orange"),
    ("A52A2A", "brown"),
]


def color_name(h: str | None) -> str | None:
    rgb = hex_to_rgb(h)
    if not rgb:
        return None
    best = None
    best_d = 10**18
    for hx, name in COLOR_PALETTE:
        prgb = hex_to_rgb(hx)
        if not prgb:
            continue
        d = (rgb[0]-prgb[0])**2 + (rgb[1]-prgb[1])**2 + (rgb[2]-prgb[2])**2
        if d < best_d:
            best_d = d
            best = name
    return best


def color_distance(a: str, b: str) -> int:
    """Distance by RGB squared error (lower is closer)."""
    ra = hex_to_rgb(a)
    rb = hex_to_rgb(b)
    if not ra or not rb:
        return 10**9
    return (ra[0]-rb[0])**2 + (ra[1]-rb[1])**2 + (ra[2]-rb[2])**2


def parse_pending_prompts() -> list[dict]:
    """Parse YAML-ish pending blocks.

    Hard guardrail: if the file doesn't contain a `status: pending` block delimiter
    structure, we treat it as empty (prevents reacting to placeholder text like
    "(see attached image)").
    """
    if not PROMPT_FILE.exists():
        return []

    content = PROMPT_FILE.read_text(encoding="utf-8").strip()
    if not content:
        return []

    # If there's no pending marker at all, don't try to parse.
    if "status: pending" not in content:
        return []

    prompts: list[dict] = []
    blocks = re.split(r"^---\s*$", content, flags=re.MULTILINE)
    for block in blocks:
        if "status: pending" not in block:
            continue
        prompt: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line and not line.strip().startswith("---"):
                key, val = line.split(":", 1)
                prompt[key.strip()] = val.strip().strip('"')
        if prompt:
            prompts.append(prompt)

    return prompts


def mark_sent(print_name: str) -> None:
    """Remove the first pending block matching print_name.

    This assumes watcher writes blocks as:
      ---
      print_name: "..."
      ...
      status: pending
      ---

    If the prompt file is in an unexpected format, we leave it untouched.
    """
    if not PROMPT_FILE.exists():
        return

    content = PROMPT_FILE.read_text(encoding="utf-8")
    if "status: pending" not in content:
        return

    lines = content.splitlines()
    new_lines: list[str] = []
    in_block = False
    block_lines: list[str] = []
    removed_one = False

    def flush_block() -> None:
        nonlocal removed_one, block_lines
        if not block_lines:
            return
        block_text = "\n".join(block_lines)
        if (not removed_one) and ("status: pending" in block_text) and ("print_name:" in block_text) and (print_name in block_text):
            removed_one = True
            block_lines = []
            return
        new_lines.extend(block_lines)
        block_lines = []

    for line in lines:
        if line.strip() == "---":
            if in_block:
                block_lines.append(line)
                flush_block()
                in_block = False
            else:
                in_block = True
                block_lines = [line]
            continue

        if in_block:
            block_lines.append(line)
        else:
            new_lines.append(line)

    # If file ended mid-block, just keep it.
    if block_lines:
        new_lines.extend(block_lines)

    PROMPT_FILE.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def send_telegram(message: str) -> bool:
    import urllib.request
    import urllib.error

    token = get_telegram_token()
    if not token:
        log("TELEGRAM_BOT_TOKEN not found in environment or .env")
        return False

    chat_id = get_target_chat_id()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.URLError as e:
        log(f"Failed to send Telegram: {e}")
        return False


def parse_ams_status(ams_json: str | None) -> list[dict] | None:
    """Parse AMS status from JSON string."""
    if not ams_json:
        return None
    try:
        data = json.loads(ams_json)
        return data.get("trays", [])
    except Exception:
        return None


def find_matching_spool(spools: list[dict], filament_material: str, filament_color: str | None) -> dict | None:
    """Find best matching spool based on filament type and color from AMS."""
    if not spools:
        return None

    # First pass: filter by material
    material_matches = [s for s in spools if (s.get("filament") or {}).get("material", "").upper() == filament_material.upper()]
    candidates = material_matches if material_matches else spools

    # Second pass: match by color if we have one
    if filament_color:
        # Exact color match
        exact = [s for s in candidates if normalize_hex((s.get("filament") or {}).get("colorHex")) == filament_color]
        if exact:
            return exact[0]

        # Closest color match
        def color_score(sp):
            sp_hex = normalize_hex((sp.get("filament") or {}).get("colorHex"))
            return color_distance(filament_color, sp_hex) if sp_hex else 10**9
        candidates = sorted(candidates, key=color_score)

    return candidates[0] if candidates else None


def find_best_spool_with_ams(spools: list[dict], filament_material: str, filament_color: str | None, ams_trays: list[dict] | None) -> dict | None:
    """Find best matching spool considering both JeevesUI colors and AMS tray colors."""
    if not spools:
        return None

    # Filter by material
    material_matches = [s for s in spools if (s.get("filament") or {}).get("material", "").upper() == filament_material.upper()]
    candidates = material_matches if material_matches else spools

    if not candidates:
        return None

    # If we have both filament color and AMS trays, match both
    if filament_color and ams_trays:
        best_spool = None
        best_dist = 10**9

        for spool in candidates:
            sp_hex = normalize_hex((spool.get("filament") or {}).get("colorHex"))
            if not sp_hex:
                continue

            for tray in ams_trays:
                if tray.get("type", "").upper() != filament_material.upper():
                    continue
                tray_color = tray.get("color", "")

                # Distance: how close is tray to 3mf color + how close is spool to 3mf color
                tray_dist = color_distance(filament_color, tray_color)
                spool_dist = color_distance(filament_color, sp_hex)
                total_dist = tray_dist + spool_dist

                if total_dist < best_dist:
                    best_dist = total_dist
                    best_spool = spool

        return best_spool

    # Fallback: match by color only
    if filament_color:
        exact = [s for s in candidates if normalize_hex((s.get("filament") or {}).get("colorHex")) == filament_color]
        if exact:
            return exact[0]

        candidates = sorted(candidates, key=lambda sp: color_distance(filament_color, normalize_hex((sp.get("filament") or {}).get("colorHex")) or "FFFFFF"))

    return candidates[0] if candidates else None


def build_full_spool_options() -> list[dict]:
    """Fetch all spools and return numbered options: name | remaining g."""
    spools = get_spools(None)  # no material filter
    if not spools:
        return []
    options = []
    for i, sp in enumerate(spools, start=1):
        fil = sp.get("filament") or {}
        name = f"{fil.get('brand','')} {fil.get('name','')}".strip() or f"{fil.get('material','?')}"
        rem = sp.get("remainingWeightG")
        rem_s = f"{round(rem)}g" if isinstance(rem, (int, float)) else "?g"
        label = f"{name} | {rem_s}"
        options.append({"n": i, "spool_id": sp.get("id"), "label": label})
    return options


def main() -> int:
    prompts = parse_pending_prompts()
    if not prompts:
        return 0

    options = build_full_spool_options()
    if not options:
        log("No spools from JeevesUI; cannot send prompt")
        return 0

    for prompt in prompts:
        print_name = prompt.get("print_name", "(unknown)")
        ts = prompt.get("timestamp", "")

        # Skip if we already sent a prompt for this print and are waiting on a reply
        if OPTIONS_FILE.exists():
            try:
                prev = json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
                if prev.get("print_name") == print_name:
                    log(f"Already prompted for {print_name}, waiting for reply — skipping")
                    mark_sent(print_name)
                    break
            except Exception:
                pass

        # Get filament metadata: prefer BambuBuddy data, fallback to .3mf parsing
        slice_info = None
        filament_source = None

        # Try BambuBuddy metadata first (from bambu_buddy_watcher)
        if prompt.get("filament_type") or prompt.get("filament_color") or prompt.get("filament_grams"):
            slice_info = {
                "material": prompt.get("filament_type"),
                "color": normalize_hex(prompt.get("filament_color")),
                "used_g": prompt.get("filament_grams"),
            }
            filament_source = "BambuBuddy"
            log(f"Using BambuBuddy filament metadata: {slice_info}")

        # Fallback: download + parse slice_info from the 3mf
        if not slice_info:
            try:
                from bambu_watcher import ftp_list_gcode_3mf, ftp_download, parse_slice_info_from_3mf
                import tempfile
                entries = ftp_list_gcode_3mf()
                # Match strictly by filename — do NOT fall back to newest.
                target_name = print_name.split("/")[-1].replace(" (Handy app)", "")
                match = next((e for e in entries if e["name"] == target_name), None)
                if match:
                    tmp = Path(tempfile.gettempdir()) / "poller_last.gcode.3mf"
                    if ftp_download(match["name"], tmp):
                        slice_info = parse_slice_info_from_3mf(tmp)
                        filament_source = "3MF file"
                        tmp.unlink(missing_ok=True)
            except Exception as e:
                log(f"slice_info fetch failed: {e}")

        # If we have slice_info, find the best matching spool and pre-fill
        prefilled_spool = None
        prefilled_grams = None
        if slice_info:
            prefilled_grams = slice_info.get("used_g")
            mat = slice_info.get("material")
            col = normalize_hex(slice_info.get("color"))
            if mat and col:
                spools_raw = get_spools(mat)
                best = find_matching_spool(spools_raw, mat, col)
                if best:
                    # Find which option number this spool corresponds to
                    for opt in options:
                        if opt["spool_id"] == best.get("id"):
                            prefilled_spool = opt
                            break

        lines = [
            f"🖨️ New print completed: *{print_name}* at {ts}",
            "",
        ]

        # Show pre-filled info if available
        if slice_info:
            mat = slice_info.get("material", "?")
            col = slice_info.get("color", "?")
            cname = color_name(col) or col
            src = f" ({filament_source})" if filament_source else ""
            lines.append(f"_Filament{src}: {mat} #{col} ({cname}), {slice_info.get('used_g','?')}g used_")
            lines.append("")

        if prefilled_spool and prefilled_grams:
            lines.append(f"_(1)_ Spool — best match: *{prefilled_spool['n']}. {prefilled_spool['label']}*")
            lines.append(f"_(2)_ Grams used: *{prefilled_grams}g*")
            lines.append("_(3)_ Who printed this? (Jacob or Tony)")
            lines.append("")
            lines.append("If correct, reply: *name* (e.g. `Tony`)")
            lines.append("To override or add more spools:")
            lines.append("  Single: `6, 39.25g, Tony`")
            lines.append("  Multi: `5, 42g + 8, 18g, Tony`")
        else:
            lines.append("_(1)_ Which spool was used? (reply with number)")
            lines.append("")
            for opt in options:
                lines.append(f"  {opt['n']}. {opt['label']}")
            lines.extend([
                "",
                "_(2)_ How many grams were used? (e.g. 33 or 39.25g)",
                "",
                "_(3)_ Who printed this? (Jacob or Tony)",
                "",
                "Reply format:",
                "  Single spool: `6, 39.25g, Tony`",
                "  Multi-color: `5, 42g + 8, 18g, Tony`",
            ])

        msg = "\n".join(lines)

        if send_telegram(msg):
            saved = {
                "timestamp": ts,
                "print_name": print_name,
                "options": options,
            }
            if prefilled_spool:
                saved["prefilled_spool_id"] = prefilled_spool["spool_id"]
                saved["prefilled_spool_n"] = prefilled_spool["n"]
            if prefilled_grams is not None:
                saved["prefilled_grams"] = prefilled_grams
            OPTIONS_FILE.write_text(json.dumps(saved, indent=2), encoding="utf-8")
            mark_sent(print_name)
            log(f"Sent 3-question prompt for {print_name} with {len(options)} spools")
        break  # one prompt per run

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
