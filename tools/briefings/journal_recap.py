#!/usr/bin/env python3
"""
Weekly Journal Recap

Generates an AI summary of the past week's journal entries.
Highlights key themes, notable moments, and patterns.
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Load .env when run by cron
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# Config
TZ = ZoneInfo("America/Los_Angeles")
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
JOURNALS_DIR = OBSIDIAN_VAULT / "Journals"
MINIMAX_API_KEY = os.environ.get("MINIMAX", "")
MINIMAX_BASE_URL = "https://api.minimax.io/v1"
MINIMAX_MODEL = "MiniMax-M2.1"


def _find_journal_csv() -> Path | None:
    """Most recent journal CSV by mtime."""
    if not JOURNALS_DIR.exists():
        return None
    csvs = sorted(JOURNALS_DIR.glob("journal-entries-*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def _parse_week_entries(csv_path: Path, start: datetime, end: datetime) -> list[dict]:
    """Return rows with Date in [start.date(), end.date()] inclusive."""
    rows = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    d = datetime.strptime(row["Date"].strip(), "%Y-%m-%d").date()
                    if start.date() <= d <= end.date():
                        rows.append(row)
                except (KeyError, ValueError):
                    continue
    except Exception as e:
        print(f"Journal parse error: {e}", file=sys.stderr)
    return rows


def _call_minimax(prompt: str, system_prompt: str = "") -> str:
    """Call MiniMax API with the given prompt."""
    if not MINIMAX_API_KEY:
        return "AI recap unavailable (no API key)"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MINIMAX_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 800,
    }

    url = f"{MINIMAX_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            # Strip <think> tags that MiniMax includes
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            return content
    except Exception as e:
        print(f"MiniMax API error: {e}", file=sys.stderr)
        return "AI recap unavailable (API error)"


def generate_recap(week_start: datetime = None) -> str:
    """
    Generate an AI-powered recap of the week's journal entries.

    Args:
        week_start: Monday of the week to recap (defaults to current week)

    Returns:
        Markdown-formatted recap string
    """
    now = datetime.now(TZ)

    # Default to current week's Monday
    if week_start is None:
        week_start = now - timedelta(days=now.weekday())

    week_end = week_start + timedelta(days=6)
    date_range = f"{week_start.strftime('%b %d')} – {week_end.strftime('%b %d')}"

    csv_path = _find_journal_csv()
    if not csv_path:
        return f"*Journal Recap ({date_range}):* No journal data found."

    entries = _parse_week_entries(csv_path, week_start, week_end)

    if not entries:
        return f"*Journal Recap ({date_range}):* No entries this week."

    # Dedupe by date (first entry wins)
    by_date = {}
    for row in entries:
        d = row["Date"].strip()
        if d not in by_date:
            by_date[d] = row

    # Build journal text for AI
    journal_text = []
    for date, row in sorted(by_date.items()):
        entry_text = row.get("Entry Text", "").strip()
        if entry_text:
            mood = row.get("Mood Rating", "?")
            journal_text.append(f"**{date}** (Mood: {mood}/5): {entry_text}")

    if not journal_text:
        return f"*Journal Recap ({date_range}):* {len(by_date)} entries, but no text content."

    # Generate AI recap
    system_prompt = """You are a thoughtful assistant helping someone reflect on their week.
Provide a concise, supportive summary (3-5 sentences) highlighting:
1. Key themes or patterns across the week
2. Notable moments (positive or challenging)
3. Overall trajectory (improvement, consistency, challenges)

Be warm, specific, and actionable. Focus on what matters most."""

    user_prompt = f"""Here are my journal entries from {date_range}:

{chr(10).join(journal_text)}

Please provide a brief, supportive recap of my week based on these entries."""

    recap = _call_minimax(user_prompt, system_prompt)

    return f"*Journal Recap ({date_range}):*\n{recap}"


def main():
    """Generate and print recap for current week."""
    recap = generate_recap()
    print(recap)


if __name__ == "__main__":
    main()
