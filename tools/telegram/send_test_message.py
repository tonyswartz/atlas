#!/usr/bin/env python3
"""Send a test message to the bot."""

import json
import urllib.request
import urllib.parse
import os
import sys

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set")
    sys.exit(1)

CHAT_ID = "8241581699"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

def send_message(text):
    """Send message to Telegram."""
    url = f"{BASE_URL}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode())
        if result.get("ok"):
            print(f"✓ Sent: {text}")
        else:
            print(f"❌ Failed: {result}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./run_with_envchain.sh python3 tools/telegram/send_test_message.py 'Your message'")
        sys.exit(1)

    send_message(" ".join(sys.argv[1:]))
