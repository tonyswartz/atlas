#!/usr/bin/env python3
"""
Conversation tracker - maintains context across multi-turn interactions.

Tracks conversation flow, user corrections, patterns, and intent to improve
context retention and learning.
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_DB = REPO_ROOT / "data" / "memory.db"
TZ = ZoneInfo("America/Los_Angeles")


def init_conversation_tables():
    """Initialize conversation tracking tables if they don't exist."""
    conn = sqlite3.connect(MEMORY_DB)

    # Conversation turns table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_message TEXT,
            assistant_message TEXT,
            tools_called TEXT,
            context_used TEXT,
            session_id TEXT
        )
    """)

    # User corrections table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            original_response TEXT,
            correction TEXT,
            context TEXT,
            learned_pattern TEXT
        )
    """)

    # Conversation patterns table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT,
            pattern_description TEXT,
            frequency INTEGER DEFAULT 1,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            confidence REAL DEFAULT 1.0
        )
    """)

    conn.commit()
    conn.close()


def log_conversation_turn(
    user_message: str,
    assistant_message: str,
    tools_called: List[str] = None,
    context_used: List[str] = None,
    session_id: str = None
) -> int:
    """
    Log a conversation turn.

    Returns:
        Turn ID
    """
    init_conversation_tables()
    conn = sqlite3.connect(MEMORY_DB)

    cursor = conn.execute(
        """
        INSERT INTO conversation_turns
        (user_message, assistant_message, tools_called, context_used, session_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_message,
            assistant_message,
            json.dumps(tools_called or []),
            json.dumps(context_used or []),
            session_id or "default"
        )
    )

    turn_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return turn_id


def log_correction(
    original_response: str,
    correction: str,
    context: Dict = None,
    learned_pattern: str = None
):
    """Log when user corrects the assistant."""
    init_conversation_tables()
    conn = sqlite3.connect(MEMORY_DB)

    conn.execute(
        """
        INSERT INTO user_corrections
        (original_response, correction, context, learned_pattern)
        VALUES (?, ?, ?, ?)
        """,
        (
            original_response,
            correction,
            json.dumps(context or {}),
            learned_pattern
        )
    )

    conn.commit()
    conn.close()


def get_recent_conversation(hours: int = 24, limit: int = 20) -> List[Dict]:
    """Get recent conversation turns for context."""
    init_conversation_tables()
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row

    cutoff = (datetime.now(TZ) - timedelta(hours=hours)).isoformat()

    cursor = conn.execute(
        """
        SELECT * FROM conversation_turns
        WHERE timestamp > ?
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        (cutoff, limit)
    )

    turns = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Parse JSON fields
    for turn in turns:
        turn['tools_called'] = json.loads(turn.get('tools_called') or '[]')
        turn['context_used'] = json.loads(turn.get('context_used') or '[]')

    return list(reversed(turns))  # Return chronological order


def detect_patterns() -> List[Dict]:
    """
    Detect conversation patterns from history.

    Returns:
        List of detected patterns with confidence scores
    """
    init_conversation_tables()
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row

    patterns = []

    # Pattern 1: Time-based requests (e.g., "every Monday at 9am user asks about...")
    cursor = conn.execute("""
        SELECT
            strftime('%w', timestamp) as day_of_week,
            strftime('%H', timestamp) as hour,
            user_message,
            COUNT(*) as frequency
        FROM conversation_turns
        WHERE timestamp > datetime('now', '-30 days')
        GROUP BY day_of_week, hour, user_message
        HAVING frequency >= 3
        ORDER BY frequency DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        day = day_names[int(row['day_of_week'])]
        hour = int(row['hour'])

        patterns.append({
            'type': 'temporal',
            'description': f"User often asks '{row['user_message'][:50]}...' on {day}s around {hour}:00",
            'frequency': row['frequency'],
            'confidence': min(1.0, row['frequency'] / 10)
        })

    # Pattern 2: Tool usage patterns
    cursor = conn.execute("""
        SELECT
            tools_called,
            COUNT(*) as frequency
        FROM conversation_turns
        WHERE tools_called != '[]'
        AND timestamp > datetime('now', '-30 days')
        GROUP BY tools_called
        HAVING frequency >= 5
        ORDER BY frequency DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        tools = json.loads(row['tools_called'])
        if tools:
            patterns.append({
                'type': 'tool_sequence',
                'description': f"Common tool sequence: {' → '.join(tools[:3])}",
                'frequency': row['frequency'],
                'confidence': min(1.0, row['frequency'] / 20)
            })

    conn.close()
    return patterns


def get_corrections_summary() -> Dict:
    """Get summary of user corrections to learn from."""
    init_conversation_tables()
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT * FROM user_corrections
        ORDER BY timestamp DESC
        LIMIT 50
    """)

    corrections = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {
        'total': len(corrections),
        'recent': corrections[:10],
        'patterns': _extract_correction_patterns(corrections)
    }


def _extract_correction_patterns(corrections: List[Dict]) -> List[str]:
    """Extract learned patterns from corrections."""
    patterns = []

    # Simple pattern extraction - look for repeated correction types
    correction_texts = [c.get('learned_pattern') for c in corrections if c.get('learned_pattern')]

    # Count occurrences
    from collections import Counter
    pattern_counts = Counter(correction_texts)

    for pattern, count in pattern_counts.most_common(10):
        if count >= 2:
            patterns.append(f"{pattern} (corrected {count} times)")

    return patterns


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Conversation tracking")
    parser.add_argument("--action", choices=["log", "recent", "patterns", "corrections"], required=True)
    parser.add_argument("--user-message", help="User message for log action")
    parser.add_argument("--assistant-message", help="Assistant message for log action")
    parser.add_argument("--hours", type=int, default=24, help="Hours of history to fetch")
    parser.add_argument("--limit", type=int, default=20, help="Max turns to return")

    args = parser.parse_args()

    if args.action == "log":
        if not args.user_message or not args.assistant_message:
            print("ERROR: --user-message and --assistant-message required for log", file=sys.stderr)
            sys.exit(1)
        turn_id = log_conversation_turn(args.user_message, args.assistant_message)
        print(json.dumps({"success": True, "turn_id": turn_id}))

    elif args.action == "recent":
        turns = get_recent_conversation(args.hours, args.limit)
        print(json.dumps({"success": True, "turns": turns}, indent=2))

    elif args.action == "patterns":
        patterns = detect_patterns()
        print(json.dumps({"success": True, "patterns": patterns}, indent=2))

    elif args.action == "corrections":
        summary = get_corrections_summary()
        print(json.dumps({"success": True, "corrections": summary}, indent=2))
