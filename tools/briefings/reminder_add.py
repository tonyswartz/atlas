#!/usr/bin/env python3
"""
Add a reminder to Tony Reminders.md.

Parses due/recurrence from a trailing [...] or plain text:
  Recurring: weekly <day>, daily, monthly
  Relative: tomorrow, in N days, in N weeks, next <weekday>, <weekday>
  Specific: 2/15, Feb 15, 26-02-15, 15th
  Other: next week, today (default)

Usage:
  From Telegram: /reminder get mail [weekly thu]
  CLI: python3 reminder_add.py "task" "schedule"
"""

import calendar
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
REMINDERS_FILE = VAULT / "Tony Reminders.md"
SECTION_HEADERS = ["[Shopping]", "[Today]", "[Later This Week]", "[Later This Month]", "[Later Later]"]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Abbreviations and full names → full name for parsing, and short label (Sun, Mon, ...)
_DAY_ALIASES: dict[str, tuple[str, str]] = {
    "sun": ("sunday", "Sun"), "sunday": ("sunday", "Sun"),
    "mon": ("monday", "Mon"), "monday": ("monday", "Mon"),
    "tue": ("tuesday", "Tue"), "tues": ("tuesday", "Tue"), "tuesday": ("tuesday", "Tue"),
    "wed": ("wednesday", "Wed"), "wednesday": ("wednesday", "Wed"),
    "thu": ("thursday", "Thu"), "thur": ("thursday", "Thu"), "thurs": ("thursday", "Thu"), "thursday": ("thursday", "Thu"),
    "fri": ("friday", "Fri"), "friday": ("friday", "Fri"),
    "sat": ("saturday", "Sat"), "saturday": ("saturday", "Sat"),
}
# Match recurring lines: (weekly Sun), (daily), (monthly) + [YY-MM-DD]
RECURRING_LINE_RE = re.compile(
    r"^-\s+(\[x\]\s+)?(.+?)\s+\(((?:weekly\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))|daily|monthly)\)\s+\[(\d{2}-\d{2}-\d{2})\]\s*$",
    re.IGNORECASE,
)


def _today() -> datetime:
    return datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)


def _next_weekday(weekday_name: str, from_dt: datetime | None = None) -> datetime:
    """weekday_name lower; 0=Monday ... 6=Sunday. Return next occurrence (or today if it's that day)."""
    from_dt = from_dt or _today()
    try:
        want = WEEKDAYS.index(weekday_name.lower())
    except ValueError:
        want = 0
    # Python weekday: Mon=0 .. Sun=6
    days_ahead = (want - from_dt.weekday()) % 7
    if days_ahead == 0:
        pass
    target = from_dt + timedelta(days=days_ahead)
    return target.replace(hour=0, minute=0, second=0, microsecond=0)


_MONTH_NAMES: dict[str, int] = {ab: i for i, ab in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
for _ab, _full in [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")]:
    _MONTH_NAMES[_full] = _MONTH_NAMES[_ab]


def _parse_specific_date(s: str) -> datetime | None:
    """Try to parse a specific date. Returns datetime at midnight in TZ or None."""
    s = s.strip().lower()
    now = _today()
    # YY-MM-DD or YYYY-MM-DD
    for fmt in ("%y-%m-%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    # M/D, M/D/YY, M/D/YYYY (allow 1 or 2 digit month/day)
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", s)
    if m:
        mo, d, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(yr) if yr else now.year
        if yr and len(yr) == 2:
            year = 2000 + int(yr) if int(yr) < 50 else 1900 + int(yr)
        if not yr and (mo, d) < (now.month, now.day):
            year = now.year + 1
        try:
            return now.replace(year=year, month=mo, day=d, hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            pass
    # Month name: feb 15, feb 15 2026, february 15
    m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{1,2})(?:\s+(\d{2,4}))?$", s)
    if m:
        mon_name, day, yr = m.group(1)[:3].lower(), int(m.group(2)), m.group(3)
        mon = _MONTH_NAMES.get(mon_name)
        if mon is None:
            pass
        else:
            year = int(yr) if yr else now.year
            if yr:
                year = 2000 + int(yr) if len(yr) == 2 and int(yr) < 50 else (1900 + int(yr) if len(yr) == 2 else int(yr))
            if not yr and (mon, day) < (now.month, now.day):
                year = now.year + 1
            try:
                return now.replace(year=year, month=mon, day=day, hour=0, minute=0, second=0, microsecond=0)
            except ValueError:
                pass
    # Ordinal: 15th (day of current or next month)
    m = re.match(r"^(\d{1,2})(?:st|nd|rd|th)?\s*$", s)
    if m:
        day = int(m.group(1))
        try:
            cand = now.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
            if cand.date() < now.date():
                if now.month == 12:
                    cand = cand.replace(year=now.year + 1, month=1)
                else:
                    cand = cand.replace(month=now.month + 1)
            return cand
        except ValueError:
            pass
    return None


def parse_schedule(schedule_raw: str) -> dict:
    """
    Parse schedule string. Return:
      section: "[Today]" | "[Later This Week]" | "[Later This Month]"
      due: date (datetime at midnight)
      date_str: "YY-MM-DD"
      recurring_label: e.g. "weekly Thu" or None
    """
    s = (schedule_raw or "").strip().lower()
    now = _today()
    recurring_label = None

    # Weekly <weekday> or weekly every <weekday> (full or abbrev: sun, mon, thursday, etc.)
    m = re.match(r"(?:weekly\s+)?(?:every\s+)?(sun|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s*$", s)
    if m:
        key = m.group(1).lower()
        day_full, short = _DAY_ALIASES.get(key, ("sunday", "Sun"))
        due = _next_weekday(day_full, now)
        recurring_label = f"weekly {short}"
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"), recurring_label=recurring_label)

    # Daily (next occurrence tomorrow so it doesn't roll immediately)
    if s in ("daily", "every day"):
        due = now + timedelta(days=1)
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"), recurring_label="daily")

    # Monthly (same day next month)
    if s in ("monthly", "every month"):
        try:
            if now.month == 12:
                due = now.replace(year=now.year + 1, month=1, day=min(now.day, 31), hour=0, minute=0, second=0, microsecond=0)
            else:
                next_m = now.month + 1
                max_d = calendar.monthrange(now.year, next_m)[1]
                due = now.replace(month=next_m, day=min(now.day, max_d), hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            due = now + timedelta(days=28)
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"), recurring_label="monthly")

    # Tomorrow
    if s in ("tomorrow", "tom"):
        due = now + timedelta(days=1)
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"))

    # Next <weekday> or just <weekday> (full or abbrev)
    m = re.match(r"(?:next\s+)?(sun|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s*$", s)
    if m:
        key = m.group(1).lower()
        day_full = _DAY_ALIASES.get(key, ("sunday",))[0]
        due = _next_weekday(day_full, now)
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"))

    # Relative: in N days, in N weeks
    m = re.match(r"in\s+(\d+)\s+(day|week)s?\s*$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "day":
            due = now + timedelta(days=n)
        else:
            due = now + timedelta(weeks=n)
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"))

    # Specific date: 2/15, feb 15, 26-02-15, 15th
    due_dt = _parse_specific_date(s)
    if due_dt is not None:
        return _section_and_date(due_dt, now, date_str=due_dt.strftime("%y-%m-%d"))

    # Next week (vague)
    if s in ("next week", "later this week"):
        due = now + timedelta(days=7)  # same day next week
        return _section_and_date(due, now, date_str=due.strftime("%y-%m-%d"))

    # Default: today
    return _section_and_date(now, now, date_str=now.strftime("%y-%m-%d"))


def _section_and_date(
    due: datetime, now: datetime,
    date_str: str,
    recurring_label: str | None = None,
) -> dict:
    if due.date() == now.date():
        section = "[Today]"
    elif (due - now).days <= 7:
        section = "[Later This Week]"
    else:
        section = "[Later This Month]"
    return {
        "section": section,
        "due": due,
        "date_str": date_str,
        "recurring_label": recurring_label,
    }


def parse_reminders_content(content: str) -> dict[str, list[str]]:
    """Parse Tony Reminders.md into sections; each value is list of raw lines."""
    sections: dict[str, list[str]] = {h: [] for h in SECTION_HEADERS}
    current: str | None = None
    for raw in content.splitlines():
        line = raw.rstrip()
        if line.strip() in sections:
            current = line.strip()
            continue
        if current and line.strip().startswith("- "):
            sections[current].append(raw)
    return sections


def add_reminder(task: str, schedule_raw: str) -> str:
    """
    Add one reminder line to Tony Reminders.md. Returns a human-readable result message.
    """
    task = (task or "").strip()
    if not task:
        return "Reminder task cannot be empty."

    if not REMINDERS_FILE.exists():
        return f"Reminders file not found: {REMINDERS_FILE}"

    parsed = parse_schedule(schedule_raw)
    section = parsed["section"]
    date_str = parsed["date_str"]
    recurring = parsed.get("recurring_label")

    if recurring:
        line = f"- {task} ({recurring}) [{date_str}]"
    else:
        line = f"- {task} [{date_str}]"

    content = REMINDERS_FILE.read_text(encoding="utf-8")
    sections = parse_reminders_content(content)

    sections[section].append(line)

    lines_out: list[str] = []
    for header in SECTION_HEADERS:
        lines_out.append(header)
        for item in sections.get(header, []):
            lines_out.append(item)
        if not sections.get(header):
            lines_out.append("- ")
        lines_out.append("")
    out = "\n".join(lines_out).rstrip() + "\n"
    REMINDERS_FILE.write_text(out, encoding="utf-8")

    return f"Added to {section}: {line}"


def roll_recurring_reminders() -> int:
    """
    Find recurring reminders (weekly ...) whose date has passed; mark them [x]
    and add the next occurrence. Returns number of reminders rolled forward.
    """
    if not REMINDERS_FILE.exists():
        return 0
    today = _today().date()
    content = REMINDERS_FILE.read_text(encoding="utf-8")
    sections = parse_reminders_content(content)
    rolled = 0
    for header in SECTION_HEADERS:
        new_items: list[str] = []
        for raw in sections.get(header, []):
            line = raw.rstrip()
            m = RECURRING_LINE_RE.match(line)
            if not m:
                new_items.append(raw)
                continue
            already_done, task, recur_label, date_str = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
            if already_done:
                new_items.append(raw)
                continue
            try:
                due = datetime.strptime(date_str, "%y-%m-%d").date()
            except ValueError:
                new_items.append(raw)
                continue
            if due > today:
                new_items.append(raw)
                continue
            # Mark this occurrence done and add next
            new_items.append(line.replace("- " + task, "- [x] " + task, 1))
            due_dt = datetime.strptime(date_str, "%y-%m-%d").replace(tzinfo=TZ)
            if recur_label.lower() == "daily":
                next_dt = due_dt + timedelta(days=1)
            elif recur_label.lower() == "monthly":
                if due_dt.month == 12:
                    next_dt = due_dt.replace(year=due_dt.year + 1, month=1, day=min(due_dt.day, 31))
                else:
                    max_d = calendar.monthrange(due_dt.year, due_dt.month + 1)[1]
                    next_dt = due_dt.replace(month=due_dt.month + 1, day=min(due_dt.day, max_d))
            else:
                next_dt = due_dt + timedelta(days=7)  # weekly
            next_str = next_dt.strftime("%y-%m-%d")
            next_line = f"- {task} ({recur_label}) [{next_str}]"
            # Place next occurrence in the right section
            next_date = next_dt.date()
            if next_date == today:
                target = "[Today]"
            elif (next_date - today).days <= 7:
                target = "[Later This Week]"
            else:
                target = "[Later This Month]"
            if target == header:
                new_items.append(next_line)
            else:
                sections[target].append(next_line)
            rolled += 1
        sections[header] = new_items
    if rolled:
        lines_out: list[str] = []
        for header in SECTION_HEADERS:
            lines_out.append(header)
            for item in sections.get(header, []):
                lines_out.append(item)
            if not sections.get(header):
                lines_out.append("- ")
            lines_out.append("")
        out = "\n".join(lines_out).rstrip() + "\n"
        REMINDERS_FILE.write_text(out, encoding="utf-8")
    return rolled


# Optional date tag in reminder lines: [YY-MM-DD]
_DATE_TAG_RE = re.compile(r"\[(\d{2}-\d{2}-\d{2})\]")


def _normalize_for_match(s: str) -> str:
    """Strip and remove markdown bold so 'Garbage/Recycling**' matches 'Garbage/Recycling'."""
    return re.sub(r"\*+", "", s.strip()).strip()


def mark_reminders_done(patterns: list[str]) -> dict:
    """
    Mark reminder lines as done ([x]) when they match any of the given patterns.
    Each pattern is matched as substring; if it contains [YY-MM-DD], the line must
    also contain that date. Returns {success, marked_count, message}.
    """
    if not REMINDERS_FILE.exists():
        return {"success": False, "marked_count": 0, "message": f"Reminders file not found: {REMINDERS_FILE}"}
    if not patterns:
        return {"success": True, "marked_count": 0, "message": "No items to mark done."}

    content = REMINDERS_FILE.read_text(encoding="utf-8")
    sections = parse_reminders_content(content)
    marked = 0
    # Build (text_part, date_tag or None) for each pattern
    parsed_patterns: list[tuple[str, str | None]] = []
    for p in patterns:
        p = (p or "").strip()
        if not p:
            continue
        date_tag = None
        m = _DATE_TAG_RE.search(p)
        if m:
            date_tag = m.group(1)
        text_part = _normalize_for_match(_DATE_TAG_RE.sub(" ", p))
        if text_part:
            parsed_patterns.append((text_part, date_tag))

    for header in SECTION_HEADERS:
        new_items: list[str] = []
        for raw in sections.get(header, []):
            line = raw.rstrip()
            if not line.startswith("- "):
                new_items.append(raw)
                continue
            if line.startswith("- [x]"):
                new_items.append(raw)
                continue
            # Line is "- task ..." — check if it matches any pattern
            matched = False
            for text_part, date_tag in parsed_patterns:
                if text_part not in _normalize_for_match(line):
                    continue
                if date_tag is not None and date_tag not in line:
                    continue
                matched = True
                break
            if not matched:
                new_items.append(raw)
                continue
            # Replace "- " at start with "- [x] "
            new_line = "- [x] " + line[2:]
            new_items.append(new_line)
            marked += 1
        sections[header] = new_items

    if marked:
        lines_out = []
        for h in SECTION_HEADERS:
            lines_out.append(h)
            for item in sections.get(h, []):
                lines_out.append(item)
            if not sections.get(h):
                lines_out.append("- ")
            lines_out.append("")
        REMINDERS_FILE.write_text(("\n".join(lines_out)).rstrip() + "\n", encoding="utf-8")

    return {
        "success": True,
        "marked_count": marked,
        "message": f"Marked {marked} reminder(s) as done." if marked else "No matching reminders found.",
    }


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--roll":
        n = roll_recurring_reminders()
        print(f"Rolled {n} recurring reminder(s).")
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "--mark-done":
        import json
        items = sys.argv[2:]
        result = mark_reminders_done(items)
        print(json.dumps(result))
        sys.exit(0 if result["success"] else 1)
    if len(sys.argv) < 2:
        print("Usage: reminder_add.py <task> [schedule]  |  reminder_add.py --roll  |  reminder_add.py --mark-done <item> ...")
        print("  task: reminder text")
        print("  schedule: e.g. 'weekly every thursday', 'tomorrow', 'monday', or leave empty for today")
        print("  --roll: advance past-due recurring (weekly) reminders to next occurrence.")
        print("  --mark-done: mark matching reminder lines as done (e.g. 'Bins to curb', 'Garbage/Recycling [26-02-03]').")
        sys.exit(1)
    task = sys.argv[1]
    schedule = sys.argv[2] if len(sys.argv) > 2 else ""
    msg = add_reminder(task, schedule)
    print(msg)


if __name__ == "__main__":
    main()
