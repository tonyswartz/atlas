#!/usr/bin/env python3
"""Handle Telegram replies for Bambu print logging.

Expected reply format: spool_number, grams, name
Examples: "6, 39.25g, Tony" or "9, 33, Jacob"

Maps option numbers to spool IDs via bambu-last-options.json (from bambu_prompt_poller).
Logs to JeevesUI and Obsidian Print Log.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("/Users/printer/atlas/logs/bambu-reply-handler.log")
JEEVESUI_URL = "http://localhost:6001"
OPTIONS_FILE = Path("/Users/printer/atlas/memory/bambu-last-options.json")
LAST_REPLY_FILE = Path("/Users/printer/atlas/memory/bambu-last-reply.txt")
VAULT = Path.home() / "Library/CloudStorage/Dropbox/Obsidian/Tony's Vault"
PRINT_LOG = VAULT / "Bambu" / "Print Log.md"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    LOG_FILE.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")


def read_last_options() -> dict | None:
    if not OPTIONS_FILE.exists():
        return None
    try:
        return json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Failed to read options file: {e}")
        return None


def log_to_jeevesui(spool_id: str, user_name: str, filename: str, grams: float) -> bool:
    """Record print job to JeevesUI API."""
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


INCOMING_MSG_FILE = Path("/Users/printer/atlas/memory/last_incoming_message.txt")


def get_last_telegram_message_line() -> str | None:
    """Read the last incoming message written by JeevesAtlas."""
    if not INCOMING_MSG_FILE.exists():
        return None
    text = INCOMING_MSG_FILE.read_text(encoding="utf-8").strip()
    return text if text else None


def parse_reply(text: str) -> tuple[int | None, str | None, float | None]:
    """Parse 'spool_number, grams, name' → (choice, user_name, grams). Prefer comma-separated."""
    t = text.strip()
    parts = [p.strip() for p in t.split(",")]

    choice = None
    grams = None
    user_name = None

    if len(parts) >= 3:
        # "6, 39.25g, Tony"
        try:
            choice = int(parts[0])
        except ValueError:
            pass
        g_str = re.sub(r"\s*g\s*$", "", parts[1], flags=re.I).strip()
        try:
            grams = float(g_str)
        except ValueError:
            pass
        if parts[2].lower() in ("tony", "jacob"):
            user_name = parts[2].capitalize()
    else:
        # Fallback: find first number (choice), grams (with g), name (Tony/Jacob)
        m_num = re.search(r"^(\d+)", t)
        choice = int(m_num.group(1)) if m_num else None
        m_g = re.search(r"(\d+\.?\d*)\s*g", t, re.I)
        if m_g:
            grams = float(m_g.group(1))
        m_user = re.search(r"\b(Tony|Jacob)\b", t, re.I)
        if m_user:
            user_name = m_user.group(1).capitalize()

    return choice, user_name, grams


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

    choice, user_name, grams = parse_reply(last_line)

    # If prefilled values exist (from slice_info), use them as defaults for missing fields
    if choice is None and options_doc.get("prefilled_spool_n") is not None:
        choice = options_doc["prefilled_spool_n"]
        log(f"Using prefilled spool choice: {choice}")
    if grams is None and options_doc.get("prefilled_grams") is not None:
        grams = options_doc["prefilled_grams"]
        log(f"Using prefilled grams: {grams}")

    # Still require all three after prefill fallback
    if choice is None:
        log("Reply missing spool number and no prefill available")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0
    if grams is None:
        log("Reply missing grams and no prefill available")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0
    if not user_name:
        log("Reply missing who (Tony or Jacob)")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0

    spool_id, spool_label = map_choice_to_spool(options_doc, choice)
    if spool_id is None:
        log(f"Choice {choice} not in options list")
        LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
        return 0

    filename = options_doc.get("print_name", "(unknown)")
    if log_to_jeevesui(spool_id, user_name, filename, float(grams)):
        append_print_log(filename, spool_label or "(unknown)", float(grams))
        log(f"Logged {grams}g to spool {spool_id} (user: {user_name})")
        OPTIONS_FILE.unlink(missing_ok=True)

    LAST_REPLY_FILE.write_text(last_line, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
