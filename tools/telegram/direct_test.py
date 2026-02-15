#!/usr/bin/env python3
"""Direct test of bot conversation handling - bypasses Telegram API."""

import asyncio
import json
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from conversation import handle_message

async def test_conversation():
    """Test conversation and session persistence."""
    user_id = 8241581699

    print("=" * 70)
    print("DIRECT BOT TEST - Session Persistence")
    print("=" * 70)
    print()

    # Read initial state
    sessions_file = Path("data/sessions.json")
    if sessions_file.exists():
        initial_state = json.loads(sessions_file.read_text())
        initial_messages = initial_state.get(str(user_id), {}).get("messages", [])
        print(f"Initial session messages: {len(initial_messages)}")
    else:
        print("No sessions.json found")
        initial_messages = []

    print()
    print("Sending test message: 'What's 2+2?'")
    print()

    # Send a simple test message
    try:
        response = await handle_message("What's 2+2?", user_id)
        print(f"✓ Got response: {response[:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    print()

    # Check if session was saved
    if sessions_file.exists():
        final_state = json.loads(sessions_file.read_text())
        final_messages = final_state.get(str(user_id), {}).get("messages", [])
        print(f"Final session messages: {len(final_messages)}")

        if len(final_messages) > len(initial_messages):
            print(f"✅ SUCCESS: Session saved {len(final_messages) - len(initial_messages)} new messages")
            print()
            print("Last 3 messages in session:")
            for msg in final_messages[-3:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:60]
                print(f"  - {role}: {content}...")
        else:
            print(f"❌ FAIL: No new messages saved (expected at least 2: user + assistant)")
            print()
            print("Session contents:")
            print(json.dumps(final_state, indent=2))
    else:
        print("❌ FAIL: sessions.json not created")

if __name__ == "__main__":
    asyncio.run(test_conversation())
