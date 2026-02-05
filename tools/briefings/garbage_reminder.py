#!/usr/bin/env python3
"""
Set weekly garbage reminder in Tony Reminders.md.

Rules (from Clawdbot setup):
- 1st & 3rd Thursday of month: Garbage & Recycling
- 2nd & 4th Thursday: Garbage only

Run weekly (e.g. Monday) or on-demand. Ensures [Later This Week] contains
exactly one garbage line for the upcoming Thursday. Safe to run repeatedly.
"""

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
REMINDERS_FILE = OBSIDIAN_VAULT / "Tony Reminders.md"

# Section order and names must match what get_reminders() expects in daily_brief_enhanced
SECTION_HEADERS = ["[Shopping]", "[Today]", "[Later This Week]", "[Later This Month]", "[Later Later]"]


def next_thursday(from_dt: datetime | None = None) -> datetime:
    """Return the next Thursday (or today if it's Thursday) at midnight in TZ."""
    now = (from_dt or datetime.now(TZ)).replace(tzinfo=TZ)
    # If today is Thursday, use today; else next Thursday
    days_ahead = (3 - now.weekday()) % 7  # 3 = Thursday
    if days_ahead == 0 and now.hour >= 12:
        # After noon Thursday, point to next week
        days_ahead = 7
    elif days_ahead == 0:
        days_ahead = 0
    target = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    return target


def garbage_label_for_date(dt: datetime) -> str:
    """1st/3rd Thu -> Garbage/Recycling; 2nd/4th -> Garbage only."""
    day = dt.day
    week_of_month = (day - 1) // 7 + 1  # 1-based
    if week_of_month in (1, 3, 5):
        return "Garbage/Recycling"
    return "Garbage only"


def is_garbage_line(line: str) -> bool:
    """True if this line is a garbage/trash reminder we manage."""
    t = line.strip()
    if not t.startswith("- "):
        return False
    t = t[2:].strip()
    # Skip completed
    if t.lower().startswith("[x]"):
        return False
    return "🗑" in t or "garbage" in t.lower() or "recycling" in t.lower()


def parse_reminders(content: str) -> dict[str, list[str]]:
    """Parse Tony Reminders.md into sections; preserve raw lines per section (no strip of content)."""
    sections: dict[str, list[str]] = {
        "[Shopping]": [],
        "[Today]": [],
        "[Later This Week]": [],
        "[Later This Month]": [],
        "[Later Later]": [],
    }
    current: str | None = None
    for raw in content.splitlines():
        line = raw.rstrip()
        if line.strip() in sections:
            current = line.strip()
            continue
        if current and line.strip().startswith("- "):
            sections[current].append(raw)  # keep original for non-garbage
    return sections


def main() -> None:
    now = datetime.now(TZ)
    thu = next_thursday(now)
    label = garbage_label_for_date(thu)
    date_str = thu.strftime("%y-%m-%d")
    new_line = f"- 🗑️ Thu: {label} [{date_str}]"

    if not REMINDERS_FILE.exists():
        print(f"Reminders file not found: {REMINDERS_FILE}")
        return

    content = REMINDERS_FILE.read_text(encoding="utf-8")
    sections = parse_reminders(content)

    # In [Later This Week], drop any existing garbage lines and add the one we want
    later = sections["[Later This Week]"]
    kept = [ln for ln in later if not is_garbage_line(ln)]
    # If the exact line already exists, don't duplicate
    if not any(new_line in ln for ln in kept):
        kept.append(new_line)
    sections["[Later This Week]"] = kept

    # Rebuild file: same section order, one blank line between sections
    lines: list[str] = []
    for header in SECTION_HEADERS:
        lines.append(header)
        items = sections.get(header, [])
        for item in items:
            lines.append(item)
        if not items:
            lines.append("- ")
        lines.append("")
    out = "\n".join(lines).rstrip() + "\n"
    REMINDERS_FILE.write_text(out, encoding="utf-8")
    print(f"Set: {new_line}")


if __name__ == "__main__":
    main()
