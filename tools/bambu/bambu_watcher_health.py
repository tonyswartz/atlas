#!/usr/bin/env python3
"""Health check for Bambu watcher.

The watcher runs via cron every 5 minutes (not a daemon). This script checks that
it has run recently (state file updated) and sends a Telegram alert if not.

Run on a schedule (e.g. every 30 min): add to crontab
   */30 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/bambu/bambu_watcher_health.py

Alerts are throttled: at most one notification per 2 hours for the same outage.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

STATE_FILE = Path("/Users/printer/atlas/data/bambu_last_state.json")
STALE_MINUTES = 20  # Consider watcher dead if no update in this long
THROTTLE_MINUTES = 120  # Don't re-alert for same outage within this long
LAST_ALERT_FILE = Path("/Users/printer/atlas/data/bambu_watcher_last_alert.txt")
TELEGRAM_TARGET = "8241581699"


def send_telegram(message: str) -> bool:
    cmd = [
        "clawdbot",
        "message",
        "send",
        "--channel", "telegram",
        "--target", TELEGRAM_TARGET,
        "--message", message,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return result.returncode == 0


def main() -> int:
    now = datetime.now()
    stale_threshold = now - timedelta(minutes=STALE_MINUTES)
    throttle_threshold = now - timedelta(minutes=THROTTLE_MINUTES)

    if not STATE_FILE.exists():
        # Never run or state was deleted
        if LAST_ALERT_FILE.exists():
            try:
                last_alert = datetime.fromisoformat(LAST_ALERT_FILE.read_text().strip())
                if last_alert > throttle_threshold:
                    return 0  # Already alerted recently
            except Exception:
                pass
        msg = (
            "⚠️ Bambu watcher health: no state file found. "
            "Watcher may never have run. Check cron and bambu_watcher_wrapper.sh."
        )
        if send_telegram(msg):
            LAST_ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
            LAST_ALERT_FILE.write_text(now.isoformat(), encoding="utf-8")
        return 1

    state_mtime = datetime.fromtimestamp(STATE_FILE.stat().st_mtime)
    if state_mtime >= stale_threshold:
        return 0  # Healthy

    # Stale: watcher hasn't run in STALE_MINUTES
    if LAST_ALERT_FILE.exists():
        try:
            last_alert = datetime.fromisoformat(LAST_ALERT_FILE.read_text().strip())
            if last_alert > throttle_threshold:
                return 1  # Already alerted, don't spam
        except Exception:
            pass

    last_seen = "unknown"
    try:
        data = STATE_FILE.read_text(encoding="utf-8")
        if "last_seen_at" in data:
            import json
            last_seen = json.loads(data).get("last_seen_at", last_seen)
    except Exception:
        pass

    msg = (
        f"⚠️ Bambu watcher hasn’t run in {STALE_MINUTES}+ minutes. "
        f"Last seen: {last_seen}. "
        "Check cron (every 5 min), machine awake, and bambu_watcher.log."
    )
    if send_telegram(msg):
        LAST_ALERT_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_ALERT_FILE.write_text(now.isoformat(), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
