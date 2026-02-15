#!/usr/bin/env python3
"""
Inter-Agent Messaging System

Enables agents to send messages to each other for cross-domain coordination.
Inspired by OpenClaw's sessions_send pattern but simplified for local use.

Usage:
    from agents.messaging import AgentMessenger

    # Send message
    messenger = AgentMessenger("bambu")
    messenger.send("telegram", {
        "event": "low_filament",
        "spool_id": 5,
        "remaining_grams": 87,
        "action": "create_reminder"
    })

    # Receive messages
    messenger = AgentMessenger("telegram")
    messages = messenger.receive()
    for msg in messages:
        print(f"From {msg['from']}: {msg['message']}")
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any


class AgentMessenger:
    """Message passing system for inter-agent communication"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.inbox_dir = Path(__file__).parent.parent / "data" / "agent_inbox"
        self.inbox_file = self.inbox_dir / f"{agent_name}.json"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, to_agent: str, message: dict, priority: str = "normal") -> bool:
        """
        Send message to another agent's inbox.

        Args:
            to_agent: Target agent name (telegram, bambu, legalkanban, briefings, system)
            message: Message payload (dict)
            priority: Message priority (low, normal, high, urgent)

        Returns:
            True if message sent successfully
        """
        if to_agent not in ["telegram", "bambu", "legalkanban", "briefings", "system"]:
            raise ValueError(f"Unknown agent: {to_agent}")

        if priority not in ["low", "normal", "high", "urgent"]:
            priority = "normal"

        target_inbox = self.inbox_dir / f"{to_agent}.json"

        # Load existing messages
        messages = []
        if target_inbox.exists():
            try:
                messages = json.loads(target_inbox.read_text())
            except json.JSONDecodeError:
                messages = []

        # Append new message
        messages.append({
            "id": self._generate_message_id(),
            "from": self.agent_name,
            "to": to_agent,
            "timestamp": datetime.now().isoformat(),
            "priority": priority,
            "message": message,
            "read": False
        })

        # Write back
        target_inbox.write_text(json.dumps(messages, indent=2))
        return True

    def receive(self, mark_as_read: bool = True, filter_priority: Optional[str] = None) -> list[dict]:
        """
        Read messages from inbox.

        Args:
            mark_as_read: If True, marks messages as read
            filter_priority: Only return messages with this priority

        Returns:
            List of message dicts
        """
        if not self.inbox_file.exists():
            return []

        try:
            messages = json.loads(self.inbox_file.read_text())
        except json.JSONDecodeError:
            return []

        # Filter by priority if specified
        if filter_priority:
            messages = [m for m in messages if m.get("priority") == filter_priority]

        # Mark as read
        if mark_as_read and messages:
            all_messages = json.loads(self.inbox_file.read_text())
            for msg in all_messages:
                if any(m["id"] == msg["id"] for m in messages):
                    msg["read"] = True
            self.inbox_file.write_text(json.dumps(all_messages, indent=2))

        return messages

    def clear_read_messages(self) -> int:
        """
        Remove messages marked as read.

        Returns:
            Number of messages removed
        """
        if not self.inbox_file.exists():
            return 0

        try:
            messages = json.loads(self.inbox_file.read_text())
        except json.JSONDecodeError:
            return 0

        unread = [m for m in messages if not m.get("read", False)]
        removed = len(messages) - len(unread)

        if unread:
            self.inbox_file.write_text(json.dumps(unread, indent=2))
        else:
            self.inbox_file.unlink()

        return removed

    def has_messages(self, unread_only: bool = True) -> bool:
        """Check if agent has pending messages"""
        if not self.inbox_file.exists():
            return False

        try:
            messages = json.loads(self.inbox_file.read_text())
        except json.JSONDecodeError:
            return False

        if unread_only:
            return any(not m.get("read", False) for m in messages)

        return len(messages) > 0

    def count_messages(self, unread_only: bool = True) -> int:
        """Count messages in inbox"""
        if not self.inbox_file.exists():
            return 0

        try:
            messages = json.loads(self.inbox_file.read_text())
        except json.JSONDecodeError:
            return 0

        if unread_only:
            return sum(1 for m in messages if not m.get("read", False))

        return len(messages)

    def _generate_message_id(self) -> str:
        """Generate unique message ID"""
        import hashlib
        content = f"{self.agent_name}_{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]


def send_message(from_agent: str, to_agent: str, message: dict, priority: str = "normal") -> bool:
    """
    Convenience function for sending messages.

    Usage:
        send_message("bambu", "telegram", {
            "event": "print_complete",
            "filename": "bracket.gcode"
        })
    """
    messenger = AgentMessenger(from_agent)
    return messenger.send(to_agent, message, priority)


def receive_messages(agent: str, mark_as_read: bool = True) -> list[dict]:
    """
    Convenience function for receiving messages.

    Usage:
        messages = receive_messages("telegram")
        for msg in messages:
            process_message(msg)
    """
    messenger = AgentMessenger(agent)
    return messenger.receive(mark_as_read)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent messaging CLI")
    parser.add_argument("--send", action="store_true", help="Send a message")
    parser.add_argument("--receive", action="store_true", help="Receive messages")
    parser.add_argument("--from", dest="from_agent", help="Sender agent")
    parser.add_argument("--to", dest="to_agent", help="Recipient agent")
    parser.add_argument("--message", help="Message content (JSON)")
    parser.add_argument("--priority", default="normal", help="Message priority")
    parser.add_argument("--clear", action="store_true", help="Clear read messages")
    parser.add_argument("--status", action="store_true", help="Show inbox status")

    args = parser.parse_args()

    if args.send:
        if not args.from_agent or not args.to_agent or not args.message:
            print("Error: --send requires --from, --to, and --message")
            exit(1)

        message = json.loads(args.message)
        success = send_message(args.from_agent, args.to_agent, message, args.priority)
        print(f"✅ Message sent from {args.from_agent} to {args.to_agent}")

    elif args.receive:
        if not args.from_agent:
            print("Error: --receive requires --from")
            exit(1)

        messages = receive_messages(args.from_agent)
        print(f"📬 {len(messages)} message(s) for {args.from_agent}:")
        for msg in messages:
            print(f"  From: {msg['from']} ({msg['timestamp']})")
            print(f"  Priority: {msg['priority']}")
            print(f"  Message: {json.dumps(msg['message'], indent=4)}")
            print()

    elif args.clear:
        if not args.from_agent:
            print("Error: --clear requires --from")
            exit(1)

        messenger = AgentMessenger(args.from_agent)
        removed = messenger.clear_read_messages()
        print(f"🗑️  Cleared {removed} read message(s)")

    elif args.status:
        print("Agent Inbox Status:")
        print("═" * 60)
        for agent in ["telegram", "bambu", "legalkanban", "briefings", "system"]:
            messenger = AgentMessenger(agent)
            unread = messenger.count_messages(unread_only=True)
            total = messenger.count_messages(unread_only=False)
            status = "📬" if unread > 0 else "✓"
            print(f"  {status} {agent:15} {unread} unread / {total} total")

    else:
        parser.print_help()
