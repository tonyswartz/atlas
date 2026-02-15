#!/usr/bin/env python3
"""Test bot responses with various query types."""

import time
import json
import urllib.request
import urllib.parse
import os
from pathlib import Path

# Load config
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Get token from environment
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set in environment")
    print("Run with: ./scripts/run_with_envchain.sh python3 tools/telegram/test_bot.py")
    sys.exit(1)

CHAT_ID = "8241581699"  # Tony's chat ID
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Test queries categorized by type
TEST_QUERIES = {
    "Simple greetings": [
        "Hi",
        "How are you?",
    ],
    "Memory queries": [
        "What do you know about me?",
        "What's on my to-do list?",
    ],
    "Tool-requiring queries": [
        "What's the weather?",
        "What reminders do I have?",
    ],
    "Clarification-prone queries": [
        "What should I focus on?",
        "What's my priority this week?",
    ],
}


def send_message(text):
    """Send message to Telegram."""
    url = f"{BASE_URL}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode())


def get_updates(offset=None, timeout=30):
    """Get updates from Telegram."""
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": timeout}
    if offset:
        params["offset"] = offset

    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")

    with urllib.request.urlopen(req, timeout=timeout + 5) as response:
        return json.loads(response.read().decode())


def wait_for_response(last_update_id, max_wait=60):
    """Wait for bot response, return (response_text, new_update_id) or (None, last_update_id)."""
    start_time = time.time()
    offset = last_update_id + 1 if last_update_id else None

    while time.time() - start_time < max_wait:
        result = get_updates(offset=offset, timeout=10)

        if result.get("ok") and result.get("result"):
            for update in result["result"]:
                update_id = update["update_id"]
                offset = update_id + 1

                # Check if it's a message from the bot (not from us)
                if "message" in update:
                    msg = update["message"]
                    if msg.get("from", {}).get("is_bot"):
                        return (msg.get("text", ""), update_id)

        time.sleep(2)

    return (None, last_update_id or 0)


def run_test(category, query, last_update_id):
    """Run a single test query."""
    print(f"\n{'='*60}")
    print(f"Category: {category}")
    print(f"Query: {query}")
    print(f"{'='*60}")

    # Send query
    send_result = send_message(query)
    if not send_result.get("ok"):
        print(f"❌ Failed to send: {send_result}")
        return last_update_id, False

    print(f"✓ Sent at {time.strftime('%H:%M:%S')}")

    # Wait for response
    print("Waiting for response...")
    response_text, new_update_id = wait_for_response(last_update_id, max_wait=60)

    if response_text is None:
        print("❌ TIMEOUT - No response within 60 seconds")
        return new_update_id, False

    print(f"✓ Response received at {time.strftime('%H:%M:%S')}:")
    print(f"  {response_text[:200]}...")  # First 200 chars

    # Check for deflection phrases
    deflections = [
        "could you specify",
        "could you clarify",
        "could you provide more",
        "to better understand",
        "which aspects are you interested in",
        "what specifically would you like",
        "can you provide more context",
        "i need more information",
        "please specify",
    ]

    response_lower = response_text.lower()
    is_deflection = any(phrase in response_lower for phrase in deflections)

    if is_deflection:
        print("⚠️  WARNING: Response contains deflection phrase")
        return new_update_id, False

    print("✓ Response looks good (no deflection detected)")
    return new_update_id, True


def main():
    """Run all tests."""
    print("Bot Response Test Suite")
    print("=" * 60)

    # Get current update ID
    result = get_updates(timeout=1)
    last_update_id = 0
    if result.get("ok") and result.get("result"):
        updates = result["result"]
        if updates:
            last_update_id = max(u["update_id"] for u in updates)

    print(f"Starting with update_id: {last_update_id}")
    print("\nWaiting 5 seconds for bot to be ready...")
    time.sleep(5)

    results = []

    for category, queries in TEST_QUERIES.items():
        for query in queries:
            last_update_id, success = run_test(category, query, last_update_id)
            results.append((category, query, success))

            # Wait between tests
            print("\nWaiting 10 seconds before next test...")
            time.sleep(10)

    # Summary
    print("\n\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, _, success in results if success)
    total = len(results)

    for category, query, success in results:
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status} | {category}: {query}")

    print(f"\n{passed}/{total} tests passed ({100*passed//total}%)")


if __name__ == "__main__":
    main()
