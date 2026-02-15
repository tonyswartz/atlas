#!/usr/bin/env python3
"""
Podcast Schedule Manager - Checks Schedule.md for upcoming episodes
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

PODCAST_CONFIGS = {
    "sololaw": {
        "path": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Solo Law Club"),
        "publish_day": "Friday",
        "name": "Solo Law Club"
    },
    "832weekends": {
        "path": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/832 Weekends"),
        "publish_day": "Friday",  # Assuming Friday, adjust if different
        "name": "832 Weekends"
    },
    "explore": {
        "path": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Explore with Tony"),
        "publish_day": "Friday",
        "name": "Explore with Tony"
    }
}


def get_next_publish_date(publish_day: str = "Friday") -> datetime:
    """Get the next publishing date (this week's Friday or next week's)"""
    today = datetime.now()
    days_ahead = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6
    }

    target_day = days_ahead[publish_day]
    current_day = today.weekday()

    # If it's already past the publish day this week, get next week's
    days_until = (target_day - current_day) % 7
    if days_until == 0 and today.hour >= 17:  # After 5pm on publish day
        days_until = 7

    next_date = today + timedelta(days=days_until)
    return next_date


def parse_schedule_entry(content: str, start_idx: int) -> Optional[Dict]:
    """Parse a single schedule entry from the markdown content"""
    # Find the date header
    date_pattern = r"##\s+(?:Friday,\s+)?([A-Za-z]+\s+\d+,\s+\d+)"
    date_match = re.search(date_pattern, content[start_idx:])
    if not date_match:
        return None

    # Parse the date
    date_str = date_match.group(1)
    try:
        episode_date = datetime.strptime(date_str, "%B %d, %Y")
    except ValueError:
        return None

    # Get the full entry (until next ## or end)
    entry_start = start_idx + date_match.start()
    next_entry = re.search(r"\n##\s+", content[entry_start + 10:])
    if next_entry:
        entry_end = entry_start + 10 + next_entry.start()
    else:
        entry_end = len(content)

    full_entry = content[entry_start:entry_end]

    # Extract components
    title_match = re.search(r"###?\s+(?:Episode:\s+)?(.+?)(?:\n|$)", full_entry)
    title = title_match.group(1).strip() if title_match else "Untitled"

    # Extract key discussion points (both markdown header and bold format)
    points_match = re.search(r"(?:###?\s+Key Discussion Points|Key Discussion Points:)(.+?)(?=###|Show Notes|\*\*Show Notes|\Z)", full_entry, re.DOTALL)
    key_points = []
    if points_match:
        points_text = points_match.group(1)
        key_points = [
            line.strip().lstrip('-•').strip()
            for line in points_text.split('\n')
            if line.strip() and (line.strip().startswith(('-', '•')) or
                               (not line.startswith('**') and not line.startswith('#') and len(line.strip()) > 10))
        ]
        # Remove empty strings and lines with just asterisks
        key_points = [p for p in key_points if p and not p.startswith('*')]

    # Extract show notes (both markdown header and bold format)
    notes_match = re.search(r"(?:###?\s+Show Notes|\*\*Show Notes:\*\*)(.+?)(?=---|##|\Z)", full_entry, re.DOTALL)
    show_notes = notes_match.group(1).strip() if notes_match else ""

    # Extract theme (for 832weekends)
    theme_match = re.search(r"\*\*Theme:\*\*\s+(.+?)(?:\n|$)", full_entry)
    theme = theme_match.group(1).strip() if theme_match else None

    return {
        "date": episode_date,
        "title": title,
        "key_points": key_points,
        "show_notes": show_notes,
        "theme": theme,
        "raw_entry": full_entry,
        "entry_start": entry_start,
        "entry_end": entry_end
    }


def get_scheduled_episode(podcast_id: str) -> Optional[Dict]:
    """Check if there's a scheduled episode for the upcoming publish date"""
    if podcast_id not in PODCAST_CONFIGS:
        raise ValueError(f"Unknown podcast ID: {podcast_id}")

    config = PODCAST_CONFIGS[podcast_id]
    schedule_file = config["path"] / "Schedule.md"

    if not schedule_file.exists():
        return None

    next_date = get_next_publish_date(config["publish_day"])

    # Read the schedule
    with open(schedule_file) as f:
        content = f.read()

    # Find all schedule entries
    current_pos = 0
    while True:
        entry = parse_schedule_entry(content, current_pos)
        if not entry:
            break

        # Check if this entry matches our target date (within 3 days tolerance)
        date_diff = abs((entry["date"] - next_date).days)
        if date_diff <= 3:
            return {
                **entry,
                "podcast_id": podcast_id,
                "podcast_name": config["name"],
                "schedule_file": str(schedule_file),
                "publish_date": next_date
            }

        current_pos = entry["entry_end"]

    return None


def remove_scheduled_episode(podcast_id: str, episode_date: datetime) -> bool:
    """Remove a scheduled episode from Schedule.md after publishing"""
    if podcast_id not in PODCAST_CONFIGS:
        raise ValueError(f"Unknown podcast ID: {podcast_id}")

    config = PODCAST_CONFIGS[podcast_id]
    schedule_file = config["path"] / "Schedule.md"

    if not schedule_file.exists():
        return False

    # Read the schedule
    with open(schedule_file) as f:
        content = f.read()

    # Find the entry to remove
    current_pos = 0
    while True:
        entry = parse_schedule_entry(content, current_pos)
        if not entry:
            break

        # Check if this is the entry to remove
        if abs((entry["date"] - episode_date).days) <= 1:
            # Remove this entry (including the separator line)
            before = content[:entry["entry_start"]]
            after = content[entry["entry_end"]:]

            # Clean up extra blank lines
            new_content = before.rstrip() + "\n\n" + after.lstrip()

            # Write back
            with open(schedule_file, 'w') as f:
                f.write(new_content)

            return True

        current_pos = entry["entry_end"]

    return False


def format_episode_idea(episode: Dict) -> str:
    """Format the scheduled episode as an episode idea for script generation"""
    lines = [f"**Episode Title:** {episode['title']}"]

    if episode.get('theme'):
        lines.append(f"**Theme:** {episode['theme']}")

    lines.append("\n**Key Discussion Points:**")
    for point in episode['key_points']:
        lines.append(f"- {point}")

    if episode['show_notes']:
        lines.append(f"\n**Show Notes:**\n{episode['show_notes']}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python schedule_manager.py <podcast_id> [--remove <date>]")
        print("Podcast IDs: sololaw, 832weekends, explore")
        sys.exit(1)

    podcast_id = sys.argv[1]

    if "--remove" in sys.argv:
        date_idx = sys.argv.index("--remove") + 1
        if date_idx < len(sys.argv):
            date_str = sys.argv[date_idx]
            episode_date = datetime.strptime(date_str, "%Y-%m-%d")
            success = remove_scheduled_episode(podcast_id, episode_date)
            print(f"✅ Removed entry for {date_str}" if success else "❌ Entry not found")
        else:
            print("Error: --remove requires a date (YYYY-MM-DD)")
    else:
        episode = get_scheduled_episode(podcast_id)

        if episode:
            print(f"📅 Scheduled Episode Found for {podcast_id}")
            print(f"Date: {episode['date'].strftime('%B %d, %Y')}")
            print(f"Title: {episode['title']}")
            if episode.get('theme'):
                print(f"Theme: {episode['theme']}")
            print(f"\nKey Points ({len(episode['key_points'])}):")
            for point in episode['key_points'][:3]:
                print(f"  • {point}")
            if len(episode['key_points']) > 3:
                print(f"  ... and {len(episode['key_points']) - 3} more")
            print("\n" + "="*60)
            print("\nFormatted Episode Idea:")
            print(format_episode_idea(episode))
        else:
            print(f"❌ No scheduled episode found for {podcast_id}")
            print(f"Next publish date: {get_next_publish_date(PODCAST_CONFIGS[podcast_id]['publish_day']).strftime('%B %d, %Y')}")
