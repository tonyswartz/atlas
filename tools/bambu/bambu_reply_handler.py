#!/usr/bin/env python3
"""Handle Telegram replies for Bambu print logging.

Expected reply format:
- Single spool: spool_number, grams, name
  Examples: "6, 39.25g, Tony" or "9, 33, Jacob"

- Multiple spools: spool1, grams1 + spool2, grams2, name
  Examples: "5, 42g + 8, 18g, Tony" or "1, 30 + 3, 25, Jacob"

Maps option numbers to spool IDs via bambu-last-options.json (from bambu_prompt_poller).
Logs to JeevesUI and Obsidian Print Log.
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

LOG_FILE = Path("/Users/printer/atlas/logs/bambu-reply-handler.log")
CONFIG_FILE = Path("/Users/printer/atlas/args/bambu_group.yaml")
JEEVESUI_URL = "http://localhost:6001"
OPTIONS_FILE = Path("/Users/printer/atlas/memory/bambu-last-options.json")
LAST_REPLY_FILE = Path("/Users/printer/atlas/memory/bambu-last-reply.txt")
VAULT = Path.home() / "Library/CloudStorage/Dropbox/Obsidian/Tony's Vault"
PRINT_LOG = VAULT / "Bambu" / "Print Log.md"


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


def send_confirmation(message: str) -> bool:
    """Send confirmation message to Telegram."""
    import urllib.request
    import urllib.error

    config = load_config()
    if not config.get("send_confirmation", True):
        return True  # Confirmations disabled

    # Get chat ID (group if enabled, else individual)
    if config.get("enabled"):
        chat_id = config.get("chat_id", "").strip()
        if not chat_id or chat_id == "CHAT_ID_HERE":
            return False
    else:
        chat_id = config.get("fallback_chat_id", "8241581699")

    # Get bot token (works in both launchd and cron)
    token = get_telegram_token()
    if not token:
        log("TELEGRAM_BOT_TOKEN not found in environment or .env")
        return False

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
    except Exception as e:
        log(f"Failed to send confirmation: {e}")
        return False


def read_last_options() -> dict | None:
    if not OPTIONS_FILE.exists():
        return None
    try:
        return json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Failed to read options file: {e}")
        return None


def log_to_csv_fallback(spool_id: str, user_name: str, filename: str, grams: float) -> None:
    """Fallback: log to CSV when JeevesUI is unavailable."""
    fallback_csv = Path("/Users/printer/atlas/data/print_jobs_fallback.csv")
    fallback_csv.parent.mkdir(parents=True, exist_ok=True)

    # Create header if new file
    if not fallback_csv.exists():
        fallback_csv.write_text("timestamp,spool_id,user_name,filename,grams\n")

    # Append entry
    ts = datetime.now().isoformat()
    with fallback_csv.open("a") as f:
        # Escape commas in filename
        safe_filename = filename.replace(",", ";")
        f.write(f"{ts},{spool_id},{user_name},{safe_filename},{grams}\n")

    log(f"⚠️ Logged to CSV fallback: {filename} ({grams}g)")


def log_to_jeevesui(spool_id: str, user_name: str, filename: str, grams: float) -> bool:
    """Record print job to JeevesUI API with CSV fallback."""
    import urllib.request
    try:
        data = json.dumps({
            "spoolId": spool_id,
            "userName": user_name,
            "filename": filename,
            "materialUsedG": grams,
        }).encode()
        req = urllib.request.Request(
            f"{JEEVESUI_URL}/api/filament/print-jobs",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True
    except Exception as e:
        log(f"Failed to log to JeevesUI: {e}")
        # Fallback: log to CSV
        log_to_csv_fallback(spool_id, user_name, filename, grams)
        return False


def append_print_log(print_name: str, spool_label: str, grams: float) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M")
    entry = "\n".join([
        f"### {ts}",
        f"- **Print**: {print_name}",
        f"- **Spool**: {spool_label}",
        f"- **Used**: {grams}g",
        "",
    ])
    if PRINT_LOG.exists():
        existing = PRINT_LOG.read_text(encoding="utf-8")
        PRINT_LOG.write_text(entry + existing, encoding="utf-8")
    else:
        PRINT_LOG.parent.mkdir(parents=True, exist_ok=True)
        PRINT_LOG.write_text("# Bambu Print Log\n\n" + entry, encoding="utf-8")


# Bambu group chat ID (from bambu_group.yaml)
BAMBU_GROUP_ID = "-5286539940"
INCOMING_MSG_FILE = Path(f"/Users/printer/atlas/memory/group_{BAMBU_GROUP_ID}_last_message.txt")


def get_last_telegram_message_line() -> str | None:
    """Read the last incoming message from the Bambu group."""
    if not INCOMING_MSG_FILE.exists():
        return None
    text = INCOMING_MSG_FILE.read_text(encoding="utf-8").strip()
    return text if text else None


def parse_reply(text: str) -> tuple[list[tuple[int, float]] | None, str | None]:
    """Parse reply → ([(spool_choice, grams), ...], user_name).

    Formats supported:
    - Single: "6, 39.25g, Tony" → ([(6, 39.25)], "Tony")
    - Multi: "5, 42g + 8, 18g, Tony" → ([(5, 42.0), (8, 18.0)], "Tony")
    - Shorthand (if prefilled): "Tony" → (None, "Tony")
    """
    t = text.strip()

    # Extract user name first (Tony or Jacob)
    user_name = None
    m_user = re.search(r"\b(Tony|Jacob)\b", t, re.I)
    if m_user:
        user_name = m_user.group(1).capitalize()
        # Remove user name from text to avoid confusion
        t = t[:m_user.start()] + t[m_user.end():]
        t = t.strip().rstrip(",")

    # If text is just the name, return None for spools (will use prefilled)
    if not t or not any(c.isdigit() for c in t):
        return None, user_name

    # Split by + to handle multi-spool
    spool_parts = [p.strip() for p in t.split("+")]
    spools = []

    for part in spool_parts:
        # Each part should be "number, grams" or "number grams"
        # Remove trailing commas
        part = part.rstrip(",").strip()

        # Try comma-separated first
        tokens = [tok.strip() for tok in part.split(",")]
        if len(tokens) >= 2:
            try:
                choice = int(tokens[0])
                g_str = re.sub(r"\s*g\s*$", "", tokens[1], flags=re.I).strip()
                grams = float(g_str)
                spools.append((choice, grams))
                continue
            except ValueError:
                pass

        # Fallback: find number and grams in the part
        m_num = re.search(r"(\d+)", part)
        m_g = re.search(r"(\d+\.?\d*)\s*g", part, re.I)
        if m_num and m_g:
            choice = int(m_num.group(1))
            grams = float(m_g.group(1))
            spools.append((choice, grams))

    return spools if spools else None, user_name


def map_choice_to_spool(options_doc: dict, choice: int) -> tuple[str | None, str | None]:
    opts = options_doc.get("options") or []
    for opt in opts:
        if opt.get("n") == choice:
            return opt.get("spool_id"), opt.get("label")
    return None, None


def main() -> int:
    last_line = get_last_telegram_message_line()
    if not last_line:
        return 0

    last_processed = LAST_REPLY_FILE.read_text(encoding="utf-8").strip() if LAST_REPLY_FILE.exists() else ""
    if last_line.strip() == last_processed.strip():
        return 0

    options_doc = read_last_options()
    if not options_doc:
        log("No options_doc available; nothing to map")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0

    spools, user_name = parse_reply(last_line)

    # If prefilled values exist (from slice_info or BambuBuddy), use them as defaults
    if spools is None and options_doc.get("prefilled_spool_n") is not None:
        choice = options_doc["prefilled_spool_n"]
        grams = options_doc.get("prefilled_grams")
        if grams is not None:
            spools = [(choice, grams)]
            log(f"Using prefilled spool: {choice}, {grams}g")

    # Require spools and user_name
    if not spools:
        log("Reply missing spool info and no prefill available")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0
    if not user_name:
        log("Reply missing who (Tony or Jacob)")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0

    filename = options_doc.get("print_name", "(unknown)")
    success_count = 0
    all_spools_logged = []

    # Log each spool
    for choice, grams in spools:
        spool_id, spool_label = map_choice_to_spool(options_doc, choice)
        if spool_id is None:
            log(f"Choice {choice} not in options list, skipping")
            continue

        if log_to_jeevesui(spool_id, user_name, filename, float(grams)):
            log(f"Logged {grams}g to spool {spool_id} ({spool_label}, user: {user_name})")
            all_spools_logged.append((spool_label or "(unknown)", grams))
            success_count += 1

    # Append to Obsidian print log (single entry with all spools)
    if all_spools_logged:
        ts = datetime.now().strftime("%y-%m-%d %H:%M")
        spool_summary = " + ".join([f"{label} {g}g" for label, g in all_spools_logged])
        entry = "\n".join([
            f"### {ts}",
            f"- **Print**: {filename}",
            f"- **Spools**: {spool_summary}",
            f"- **User**: {user_name}",
            "",
        ])
        if PRINT_LOG.exists():
            existing = PRINT_LOG.read_text(encoding="utf-8")
            PRINT_LOG.write_text(entry + existing, encoding="utf-8")
        else:
            PRINT_LOG.parent.mkdir(parents=True, exist_ok=True)
            PRINT_LOG.write_text("# Bambu Print Log\n\n" + entry, encoding="utf-8")

    if success_count > 0:
        OPTIONS_FILE.unlink(missing_ok=True)

        # Send confirmation message
        spool_summary = " + ".join([f"{label} {g}g" for label, g in all_spools_logged])
        config = load_config()
        confirm_msg = config.get("confirmations", {}).get("success", "✅ Logged: {filename}\n{spools}\nUser: {user}")
        confirm_msg = confirm_msg.format(
            filename=filename,
            spools=spool_summary,
            user=user_name
        )
        send_confirmation(confirm_msg)

    LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
