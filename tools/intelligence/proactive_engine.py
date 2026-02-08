#!/usr/bin/env python3
"""
Proactive intelligence engine - surfaces insights and suggestions automatically.

Analyzes patterns, detects opportunities for automation, and provides
context-aware nudges without being asked.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TZ = ZoneInfo("America/Los_Angeles")

sys.path.insert(0, str(REPO_ROOT / "tools" / "memory"))
from conversation_tracker import detect_patterns, get_corrections_summary


def generate_proactive_suggestions() -> List[Dict]:
    """
    Generate proactive suggestions based on patterns, context, and time.

    Returns:
        List of suggestions with priority and reasoning
    """
    suggestions = []
    now = datetime.now(TZ)

    # 1. Pattern-based suggestions
    patterns = detect_patterns()
    for pattern in patterns:
        if pattern['confidence'] > 0.6:
            suggestions.append({
                'type': 'pattern',
                'priority': 'medium',
                'suggestion': f"Heads up: {pattern['description']}",
                'reasoning': f"Detected pattern with {pattern['confidence']:.0%} confidence",
                'actionable': False
            })

    # 2. Time-based context awareness
    if now.hour < 12:
        suggestions.append({
            'type': 'temporal',
            'priority': 'low',
            'suggestion': "Morning - good time to review priorities",
            'reasoning': "Morning context",
            'actionable': True,
            'action': 'Show kanban + reminders'
        })

    # 3. Learning from corrections
    corrections = get_corrections_summary()
    if corrections['total'] > 0:
        recent_patterns = corrections.get('patterns', [])
        if recent_patterns:
            suggestions.append({
                'type': 'learning',
                'priority': 'high',
                'suggestion': f"Applying lessons from {corrections['total']} previous corrections",
                'reasoning': f"Patterns learned: {', '.join(recent_patterns[:3])}",
                'actionable': False
            })

    # 4. Deadline proximity alerts (from calendar/kanban integration)
    # TODO: Implement when calendar API is available

    # 5. Inactivity nudges (journal, fitness, etc.)
    # TODO: Implement by analyzing last activity timestamps

    return sorted(suggestions, key=lambda x: {'high': 0, 'medium': 1, 'low': 2}[x['priority']])


def check_context_triggers() -> Dict:
    """
    Check for context-specific triggers that warrant proactive action.

    Returns:
        Dict with triggered contexts and recommended actions
    """
    triggers = {
        'calendar_proximity': [],  # Meetings starting soon
        'deadline_proximity': [],  # Tasks/deadlines approaching
        'pattern_deviation': [],   # User behaving differently than usual
        'learning_opportunity': [],  # Repeated corrections on same topic
    }

    now = datetime.now(TZ)

    # Check for calendar proximity (30 min before meeting)
    # TODO: Implement when calendar tool is integrated

    # Check for pattern deviations
    patterns = detect_patterns()
    # TODO: Compare current behavior to patterns

    return triggers


def format_proactive_brief() -> str:
    """
    Format proactive suggestions into a brief for display.

    Returns:
        Formatted markdown string
    """
    suggestions = generate_proactive_suggestions()

    if not suggestions:
        return ""

    lines = ["**Proactive Insights:**\n"]

    high_priority = [s for s in suggestions if s['priority'] == 'high']
    if high_priority:
        lines.append("*High Priority:*")
        for s in high_priority:
            lines.append(f"• {s['suggestion']}")
        lines.append("")

    medium_priority = [s for s in suggestions if s['priority'] == 'medium']
    if medium_priority:
        lines.append("*For your awareness:*")
        for s in medium_priority[:3]:  # Limit to 3
            lines.append(f"• {s['suggestion']}")

    return "\n".join(lines)


def detect_intent_from_partial(text: str) -> Dict:
    """
    Predict user intent from partial or incomplete requests.

    Args:
        text: Partial user message

    Returns:
        Dict with predicted intent and confidence
    """
    text_lower = text.lower()

    intents = []

    # Intent: Setting up automation
    if any(word in text_lower for word in ['automate', 'script', 'monitor', 'watch', 'track']):
        intents.append({
            'intent': 'automation_setup',
            'confidence': 0.8,
            'suggested_clarification': "What should trigger the automation?"
        })

    # Intent: Retrieving information
    if any(word in text_lower for word in ['what', 'when', 'where', 'who', 'how']):
        intents.append({
            'intent': 'information_retrieval',
            'confidence': 0.7,
            'suggested_clarification': "Should I search memory or the web?"
        })

    # Intent: Task management
    if any(word in text_lower for word in ['add task', 'remind me', 'todo', 'priority']):
        intents.append({
            'intent': 'task_management',
            'confidence': 0.9,
            'suggested_clarification': "When should this be done?"
        })

    # Intent: Status check
    if any(word in text_lower for word in ['status', 'how is', 'what\'s the', 'update on']):
        intents.append({
            'intent': 'status_check',
            'confidence': 0.8,
            'suggested_clarification': "Which system or project?"
        })

    if not intents:
        return {
            'intent': 'unclear',
            'confidence': 0.0,
            'suggested_clarification': "Can you provide more context?"
        }

    # Return highest confidence intent
    return max(intents, key=lambda x: x['confidence'])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Proactive intelligence engine")
    parser.add_argument("--action", choices=["suggestions", "brief", "intent", "triggers"], required=True)
    parser.add_argument("--text", help="Text for intent detection")

    args = parser.parse_args()

    if args.action == "suggestions":
        suggestions = generate_proactive_suggestions()
        print(json.dumps({"success": True, "suggestions": suggestions}, indent=2))

    elif args.action == "brief":
        brief = format_proactive_brief()
        print(json.dumps({"success": True, "brief": brief}))

    elif args.action == "intent":
        if not args.text:
            print("ERROR: --text required for intent detection", file=sys.stderr)
            sys.exit(1)
        intent = detect_intent_from_partial(args.text)
        print(json.dumps({"success": True, "intent": intent}, indent=2))

    elif args.action == "triggers":
        triggers = check_context_triggers()
        print(json.dumps({"success": True, "triggers": triggers}, indent=2))
