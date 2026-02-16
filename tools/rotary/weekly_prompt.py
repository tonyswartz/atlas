#!/usr/bin/env python3
"""
Rotary Weekly Agenda Prompt

Sends weekly prompt to create Rotary meeting agenda via Telegram.
Scheduled to run Sundays at 5pm.

Usage:
    python tools/rotary/weekly_prompt.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

TZ = ZoneInfo("America/Los_Angeles")
TELEGRAM_CHAT_ID = "8241581699"  # Tony's personal chat


def send_telegram(message: str, chat_id: str = TELEGRAM_CHAT_ID) -> dict:
    """Send message to Telegram. Returns dict with success and message_id."""
    from tools.common.credentials import get_telegram_token
    import urllib.request

    token = get_telegram_token()
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found")
        return {"success": False, "message_id": None}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    # Retry logic (3 attempts with exponential backoff)
    import time
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                message_id = result.get("result", {}).get("message_id")
                print(f"✓ Sent Rotary prompt (message_id: {message_id})")
                return {"success": True, "message_id": message_id}
        except Exception as e:
            if attempt < 2:  # Don't sleep on last attempt
                sleep_time = 2 ** attempt  # 1s, 2s
                print(f"Retry {attempt + 1}/3 after {sleep_time}s: {e}")
                time.sleep(sleep_time)
            else:
                print(f"❌ Failed to send after 3 attempts: {e}")
                return {"success": False, "message_id": None}


def get_next_tuesday() -> str:
    """Get the date of next Tuesday in MM/DD format."""
    now = datetime.now(TZ)
    # Find next Tuesday (weekday 1)
    days_ahead = (1 - now.weekday()) % 7
    if days_ahead == 0:  # Today is Tuesday
        days_ahead = 7  # Get next Tuesday
    next_tuesday = now + timedelta(days=days_ahead)
    return next_tuesday.strftime("%-m/%-d")  # e.g., "2/18"


def main():
    """Send weekly Rotary agenda creation prompt."""
    meeting_date = get_next_tuesday()

    message = f"""📋 **Weekly Rotary Agenda Reminder**

It's time to create the agenda for Tuesday's meeting ({meeting_date}).

To create the agenda, type:
`/rotary`

This will walk you through:
• Member spotlight
• Guest speaker
• Announcements
• Other details

The agenda will be saved and auto-printed on Tuesday at 4pm."""

    result = send_telegram(message)

    if result["success"]:
        print(f"✓ Rotary weekly prompt sent for {meeting_date}")
        return 0
    else:
        print(f"✗ Failed to send Rotary prompt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
