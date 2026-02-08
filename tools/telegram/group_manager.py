#!/usr/bin/env python3
"""
Telegram group management.

Autodetects when the bot is added to new groups and stores their IDs and names.
Provides mapping from group names to chat IDs for routing messages.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GROUPS_FILE = REPO_ROOT / "data" / "telegram_groups.json"


def load_groups() -> Dict[str, Dict]:
    """
    Load known Telegram groups from disk.

    Returns:
        Dict mapping chat_id (str) to group info {name, title, type, first_seen}
    """
    if not GROUPS_FILE.exists():
        return {}

    try:
        return json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load groups file: %s", e)
        return {}


def save_groups(groups: Dict[str, Dict]) -> bool:
    """
    Save groups to disk.

    Args:
        groups: Dict mapping chat_id to group info

    Returns:
        True if successful, False otherwise
    """
    try:
        GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        GROUPS_FILE.write_text(json.dumps(groups, indent=2), encoding="utf-8")
        return True
    except OSError as e:
        logger.error("Failed to save groups file: %s", e)
        return False


def register_chat(chat_id: int, chat_type: str, title: Optional[str] = None, username: Optional[str] = None) -> bool:
    """
    Register a chat (group or supergroup) in the groups database.

    Args:
        chat_id: Telegram chat ID (negative for groups)
        chat_type: Chat type (private, group, supergroup, channel)
        title: Group title/name
        username: Optional username/handle

    Returns:
        True if this is a new group, False if already known
    """
    # Only track groups and supergroups, not private chats
    if chat_type not in ("group", "supergroup"):
        return False

    groups = load_groups()
    chat_id_str = str(chat_id)

    # Check if already registered
    if chat_id_str in groups:
        # Update title if changed
        if title and groups[chat_id_str].get("title") != title:
            groups[chat_id_str]["title"] = title
            save_groups(groups)
            logger.info("Updated group title: %s → %s", chat_id, title)
        return False

    # New group discovered
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Los_Angeles")

    groups[chat_id_str] = {
        "chat_id": chat_id,
        "title": title or "Unknown",
        "username": username,
        "type": chat_type,
        "first_seen": datetime.now(tz).isoformat()
    }

    save_groups(groups)
    logger.info("New group registered: %s (%s) - %s", chat_id, title, chat_type)
    return True


def get_group_by_name(name: str) -> Optional[Dict]:
    """
    Find a group by partial name match (case-insensitive).

    Args:
        name: Group name or partial name to search for

    Returns:
        Group info dict if found, None otherwise
    """
    groups = load_groups()
    name_lower = name.lower()

    # Try exact match first
    for group in groups.values():
        if group.get("title", "").lower() == name_lower:
            return group

    # Try partial match
    for group in groups.values():
        if name_lower in group.get("title", "").lower():
            return group

    return None


def get_group_id(name: str) -> Optional[str]:
    """
    Get chat ID for a group by name.

    Args:
        name: Group name or partial name

    Returns:
        Chat ID as string if found, None otherwise
    """
    group = get_group_by_name(name)
    return str(group["chat_id"]) if group else None


def list_groups() -> List[Dict]:
    """
    List all known groups.

    Returns:
        List of group info dicts
    """
    groups = load_groups()
    return sorted(groups.values(), key=lambda g: g.get("first_seen", ""))


def format_groups_list() -> str:
    """
    Format groups list for display to user or LLM.

    Returns:
        Formatted string listing all groups
    """
    groups = list_groups()
    if not groups:
        return "No groups registered yet."

    lines = ["Known Telegram groups:"]
    for g in groups:
        title = g.get("title", "Unknown")
        chat_id = g.get("chat_id", "?")
        chat_type = g.get("type", "?")
        lines.append(f"• {title} (ID: {chat_id}, type: {chat_type})")

    return "\n".join(lines)


if __name__ == "__main__":
    # CLI interface for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  group_manager.py list")
        print("  group_manager.py find <name>")
        print("  group_manager.py register <chat_id> <type> <title>")
        sys.exit(1)

    action = sys.argv[1]

    if action == "list":
        print(format_groups_list())

    elif action == "find":
        if len(sys.argv) < 3:
            print("ERROR: find requires name")
            sys.exit(1)
        name = sys.argv[2]
        group = get_group_by_name(name)
        if group:
            print(json.dumps(group, indent=2))
        else:
            print(f"No group found matching: {name}")
            sys.exit(1)

    elif action == "register":
        if len(sys.argv) < 5:
            print("ERROR: register requires chat_id, type, and title")
            sys.exit(1)
        chat_id = int(sys.argv[2])
        chat_type = sys.argv[3]
        title = sys.argv[4]
        is_new = register_chat(chat_id, chat_type, title)
        if is_new:
            print(f"Registered new group: {title} ({chat_id})")
        else:
            print(f"Group already registered: {title} ({chat_id})")

    else:
        print(f"ERROR: Unknown action: {action}")
        sys.exit(1)
