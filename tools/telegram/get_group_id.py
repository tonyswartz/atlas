#!/usr/bin/env python3
"""Quick script to find group chat IDs - run and send a message in the target group"""

import json
import sys
from pathlib import Path

# Check recent group message files
memory_dir = Path("/Users/printer/atlas/memory")
group_files = sorted(memory_dir.glob("group_*_last_message.txt"), key=lambda x: x.stat().st_mtime, reverse=True)

print("Recent group activity:")
print()

for f in group_files[:10]:
    # Extract chat_id from filename: group_-1234567890_last_message.txt
    parts = f.stem.split("_")
    if len(parts) >= 2:
        chat_id = parts[1]
        try:
            content = f.read_text(encoding="utf-8").strip()[:100]
            mtime = f.stat().st_mtime

            print(f"Chat ID: {chat_id}")
            print(f"  Last message: {content}")
            print(f"  Modified: {Path(f).stat().st_mtime}")
            print()
        except Exception as e:
            print(f"Chat ID: {chat_id} (error reading: {e})")
            print()

print("\nTo find your code group:")
print("1. Send any message in the code group")
print("2. Run this script again")
print("3. Look for the newest entry above")
