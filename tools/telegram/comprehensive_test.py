#!/usr/bin/env python3
"""Comprehensive bot test - send queries and check sessions.json for responses."""

import json
import time
import urllib.request
import urllib.parse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not set")
    sys.exit(1)

CHAT_ID = "8241581699"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Comprehensive test cases
TEST_CASES = [
    {
        "name": "Simple greeting",
        "query": "Hi",
        "expected": ["greeting", "hello", "hey", "hi"],
        "max_wait": 10
    },
    {
        "name": "Memory query",
        "query": "What do you know about me?",
        "expected": ["memory", "know", "nelson", "dui", "case"],
        "max_wait": 20
    },
    {
        "name": "Reminders query",
        "query": "What reminders do I have?",
        "expected": ["reminder"],
        "max_wait": 20
    },
    {
        "name": "Priority question",
        "query": "What should I focus on this week?",
        "expected": ["nelson", "case", "focus", "priority"],
        "max_wait": 20
    },
    {
        "name": "Current work context",
        "query": "What am I working on?",
        "expected": ["nelson", "work", "case"],
        "max_wait": 20
    },
    {
        "name": "Add reminder",
        "query": "Remind me to test the bot tomorrow",
        "expected": ["remind", "added", "tomorrow"],
        "max_wait": 15
    },
    {
        "name": "Simple question",
        "query": "How's the weather?",
        "expected": [],  # May fail gracefully
        "max_wait": 15
    }
]

def send_message(text):
    """Send message to Telegram."""
    url = f"{BASE_URL}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            return result.get("ok", False)
    except Exception as e:
        print(f"  ❌ Failed to send: {e}")
        return False

def get_last_response():
    """Read last response from sessions.json."""
    try:
        sessions = json.loads(Path("data/sessions.json").read_text())
        messages = sessions.get(CHAT_ID, {}).get("messages", [])

        # Find last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
        return None
    except Exception as e:
        print(f"  ⚠️  Error reading session: {e}")
        return None

def wait_for_response(initial_response, max_wait=20):
    """Wait for bot to respond (sessions.json to update)."""
    start_time = time.time()

    while time.time() - start_time < max_wait:
        time.sleep(2)
        current_response = get_last_response()

        if current_response and current_response != initial_response:
            return current_response

    return None

def check_response(response, expected_keywords):
    """Check if response contains expected keywords."""
    if not response:
        return False, "No response"

    if not expected_keywords:
        return True, "Response received (no keyword check)"

    response_lower = response.lower()
    matches = [kw for kw in expected_keywords if kw.lower() in response_lower]

    if matches:
        return True, f"Matched: {', '.join(matches)}"
    else:
        return False, f"Missing expected keywords: {', '.join(expected_keywords)}"

def run_tests():
    """Run all test cases."""
    print("=" * 70)
    print("COMPREHENSIVE BOT TEST SUITE")
    print("=" * 70)
    print()

    results = []

    for i, test in enumerate(TEST_CASES, 1):
        print(f"[{i}/{len(TEST_CASES)}] {test['name']}")
        print(f"  Query: \"{test['query']}\"")

        # Get initial state
        initial_response = get_last_response()

        # Send message
        if not send_message(test['query']):
            results.append({
                "name": test['name'],
                "status": "FAIL",
                "reason": "Failed to send message"
            })
            print(f"  ❌ FAIL: Failed to send\n")
            continue

        print(f"  ✓ Sent")

        # Wait for response
        response = wait_for_response(initial_response, test['max_wait'])

        if not response:
            results.append({
                "name": test['name'],
                "status": "TIMEOUT",
                "reason": f"No response within {test['max_wait']}s"
            })
            print(f"  ⏱️  TIMEOUT: No response within {test['max_wait']}s\n")
            continue

        # Check response
        passed, details = check_response(response, test['expected'])

        if passed:
            results.append({
                "name": test['name'],
                "status": "PASS",
                "reason": details,
                "response": response[:100] + "..." if len(response) > 100 else response
            })
            print(f"  ✅ PASS: {details}")
            print(f"  Response: {response[:80]}...\n")
        else:
            results.append({
                "name": test['name'],
                "status": "FAIL",
                "reason": details,
                "response": response[:100] + "..." if len(response) > 100 else response
            })
            print(f"  ❌ FAIL: {details}")
            print(f"  Response: {response[:80]}...\n")

        # Wait between tests
        time.sleep(3)

    # Summary
    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    timeout = sum(1 for r in results if r["status"] == "TIMEOUT")

    for result in results:
        status_icon = {
            "PASS": "✅",
            "FAIL": "❌",
            "TIMEOUT": "⏱️ "
        }.get(result["status"], "?")

        print(f"{status_icon} {result['name']}: {result['status']}")
        if result['status'] != "PASS":
            print(f"   Reason: {result['reason']}")

    print()
    print(f"Results: {passed} passed, {failed} failed, {timeout} timeout")
    print(f"Success rate: {100 * passed // len(results)}%")
    print()

    return results

if __name__ == "__main__":
    run_tests()
