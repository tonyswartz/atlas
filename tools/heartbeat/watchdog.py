#!/usr/bin/env python3
"""
Watchdog — post-cron error checker.

Scans today's cron log files for error/traceback lines.
If any are found, sends a Telegram alert so nothing silently fails.

Run by cron a few minutes after each major job (e.g. 6:05 AM after daily_brief).
Usage: python3 tools/heartbeat/watchdog.py
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = REPO_ROOT / "logs"

# Prefer env (envchain); fall back to .env when run by launchd/cron without shell profile
_DOT_ENV = REPO_ROOT / ".env"
if _DOT_ENV.exists():
    for line in _DOT_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_ID", "")

# Log files to check, in order of priority
LOG_FILES = [
    "daily_brief.log",
    "kanban-runner.log",
    "research_brief.log",
    "local_news.log",
    "wa_dui_bill_tracker.log",
]

# Patterns that indicate an error (case-insensitive)
ERROR_PATTERNS = [
    "traceback",
    "exception",
    "errno",
    "could not",
]

# Patterns to ignore (false positives in brief output)
IGNORE_PATTERNS = [
    "calendar error:",      # Part of brief format when calendar fails
    "weather error:",       # Part of brief format when weather fails
    "weather unavailable",  # Expected fallback message
    "• calendar error:",    # Formatted list item
    "• weather error:",     # Formatted list item
    "  →",                  # Case law holdings (contain legal terms like "exception", "error")
]


def _scan_log(path: Path) -> list[str]:
    """Return lines from today's log that match any error pattern."""
    if not path.exists():
        return []
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    hits = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            lower = line.lower()
            # Skip lines matching ignore patterns (false positives)
            if any(pat.lower() in lower for pat in IGNORE_PATTERNS):
                continue
            # Check for error patterns
            if any(pat in lower for pat in ERROR_PATTERNS):
                hits.append(line.strip())
    except OSError:
        pass
    return hits


def _send_telegram(text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    if not BOT_TOKEN or not CHAT_ID:
        print("WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_ID not set — cannot alert", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": int(CHAT_ID), "text": text, "parse_mode": "Markdown"}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        return False


def main():
    now = datetime.now(TZ)
    findings = {}  # filename -> [error lines]

    for name in LOG_FILES:
        hits = _scan_log(LOGS_DIR / name)
        if hits:
            findings[name] = hits

    if not findings:
        print(f"[{now:%H:%M}] Watchdog: all logs clean.")
        return

    # Build alert message
    lines = [f"⚠️ *Watchdog alert — {now:%b %d %H:%M}*\n"]
    for fname, errors in findings.items():
        lines.append(f"*{fname}:*")
        # Cap per-file to 3 lines so the alert stays readable
        for err in errors[:3]:
            lines.append(f"  • {err[:200]}")
        if len(errors) > 3:
            lines.append(f"  … and {len(errors) - 3} more")
        lines.append("")

    alert = "\n".join(lines)
    print(f"[{now:%H:%M}] Watchdog: {sum(len(v) for v in findings.values())} error(s) in {len(findings)} log(s). Alerting.")
    _send_telegram(alert)


if __name__ == "__main__":
    main()
