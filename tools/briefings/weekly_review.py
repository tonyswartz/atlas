#!/usr/bin/env python3
"""
Friday Weekly Review

Looks back Mon–Sun: journal stats, fitness, mood trend, kanban health.
Surfaces nudges only when something's actually worth flagging.
Sends to Telegram at 5pm Friday (cron). Also runnable via /run weekly_review.
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Import journal and health tools
try:
    from tools.briefings.journal_backup import backup_week
    from tools.briefings.journal_recap import generate_recap
    from tools.briefings.health_stats import get_week_health_stats, format_health_summary
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools.briefings.journal_backup import backup_week
    from tools.briefings.journal_recap import generate_recap
    from tools.briefings.health_stats import get_week_health_stats, format_health_summary

# Load .env when run by cron
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TZ = ZoneInfo("America/Los_Angeles")
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
KANBAN_FILE     = OBSIDIAN_VAULT / "Tony Kanban.md"
REMINDERS_FILE  = OBSIDIAN_VAULT / "Tony Reminders.md"
JOURNALS_DIR    = OBSIDIAN_VAULT / "Journals"
BRIEFS_DIR      = OBSIDIAN_VAULT / "Research" / "Briefs"

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = "8241581699"

# Single-entry cycling miles above this are likely import artifacts (cumulative totals)
CYCLING_MILES_SANITY_CAP = 100


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
def _find_journal_csv() -> Path | None:
    """Most recent journal CSV by mtime."""
    if not JOURNALS_DIR.exists():
        return None
    csvs = sorted(JOURNALS_DIR.glob("journal-entries-*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    return csvs[0] if csvs else None


def _parse_journal_range(csv_path: Path, start: datetime, end: datetime) -> list[dict]:
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


def _week_stats(rows: list[dict]) -> dict:
    """Aggregate journal rows into weekly stats. Dedupes by date (first entry wins)."""
    by_date: dict[str, dict] = {}
    for row in rows:
        d = row["Date"].strip()
        if d not in by_date:
            by_date[d] = row

    moods, fitness, cycling_days, cycling_miles, strength = [], 0, 0, 0.0, 0

    for d, row in by_date.items():
        try:
            m = int(row.get("Mood Rating", "0").strip())
            if m > 0:
                moods.append(m)
        except (ValueError, AttributeError):
            pass

        if row.get("Fitness Goal", "").strip().lower() == "true":
            fitness += 1
        if row.get("Did Cycle", "").strip().lower() == "true":
            cycling_days += 1
            try:
                mi = float(row.get("Cycling Miles", "0").strip())
                if mi <= CYCLING_MILES_SANITY_CAP:
                    cycling_miles += mi
            except (ValueError, AttributeError):
                pass
        if row.get("Strength Goal", "").strip().lower() == "true":
            strength += 1

    return {
        "days":          len(by_date),
        "dates":         set(by_date.keys()),
        "mood_avg":      round(sum(moods) / len(moods), 1) if moods else 0,
        "fitness_days":  fitness,
        "cycling_days":  cycling_days,
        "cycling_miles": round(cycling_miles, 1),
        "strength_days": strength,
    }


# ---------------------------------------------------------------------------
# Kanban
# ---------------------------------------------------------------------------
def _get_kanban() -> dict[str, list[str]]:
    """Parse kanban into {todo, in_progress, done}. Tolerant of different heading styles."""
    out: dict[str, list[str]] = {"todo": [], "in_progress": [], "done": []}
    if not KANBAN_FILE.exists():
        return out

    section_aliases = {
        "things to do": "todo", "to-do": "todo", "todo": "todo",
        "in progress": "in_progress", "in-progress": "in_progress",
        "done": "done", "completed": "done",
    }
    current: str | None = None

    for line in KANBAN_FILE.read_text().splitlines():
        stripped = line.strip()
        # Detect section headers: ## Heading  or  [Heading]
        candidate = stripped.lower().strip("#[]").strip()
        if candidate in section_aliases:
            current = section_aliases[candidate]
            continue
        # Task lines
        if current and stripped.startswith("- "):
            task = stripped[2:].strip()
            # Strip checkbox markers [ ] [x]
            task = task.lstrip("[]xX ").strip()
            if task:
                out[current].append(task)

    return out


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------
def _get_next_week_reminders() -> list[str]:
    """Items currently in 'Later This Week' — these will roll into next week."""
    if not REMINDERS_FILE.exists():
        return []
    items, current = [], None
    for line in REMINDERS_FILE.read_text().splitlines():
        stripped = line.strip()
        if stripped.lower() == "[later this week]":
            current = True
        elif stripped.startswith("["):
            current = False
        elif current and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item and not item.lower().startswith("[x]"):
                items.append(item)
    return items


# ---------------------------------------------------------------------------
# Nudges
# ---------------------------------------------------------------------------
def _compute_nudges(this: dict, prev: dict, kanban: dict) -> list[str]:
    """Return nudge strings. Only include ones that actually have something to say."""
    now = datetime.now(TZ)
    nudges: list[str] = []

    # --- Journal gaps ---
    # Expected: Mon through min(today, Sun). Don't flag today before 6pm.
    mon = (now - timedelta(days=now.weekday())).date()
    expected = set()
    for i in range(7):
        d = mon + timedelta(days=i)
        if d > now.date():
            break
        if d == now.date() and now.hour < 18:
            break  # today's entry might still come
        expected.add(d.isoformat())
    missing = expected - this["dates"]
    if missing and this["days"] > 0:
        # Only flag gaps when there ARE some entries — zero entries is its own message
        nudges.append(f"Journaling: {len(missing)} day{'s' if len(missing) > 1 else ''} missing this week")

    # The rest only make sense if we actually have journal data this week
    if this["days"] > 0:
        # --- Mood dip (only flag if meaningfully lower) ---
        if this["mood_avg"] and prev["mood_avg"] and (this["mood_avg"] - prev["mood_avg"]) <= -0.5:
            nudges.append(f"Mood: {prev['mood_avg']} → {this['mood_avg']} (down from last week)")

        # --- Fitness (only flag if less than half the days actually logged) ---
        if this["days"] >= 3 and this["fitness_days"] < this["days"] * 0.5:
            nudges.append(f"Fitness goal: {this['fitness_days']}/{this['days']} days")

        # --- Cycling gap ---
        if this["days"] >= 3 and this["cycling_days"] == 0:
            nudges.append("No cycling logged this week")

        # --- Strength gap ---
        if this["days"] >= 3 and this["strength_days"] == 0:
            nudges.append("No strength training this week")

    # --- Kanban stall ---
    if kanban["todo"]:
        nudges.append(f"Kanban: {len(kanban['todo'])} item{'s' if len(kanban['todo']) > 1 else ''} in To-Do")

    return nudges


# ---------------------------------------------------------------------------
# Format + send
# ---------------------------------------------------------------------------
def _format_review() -> str:
    now = datetime.now(TZ)
    mon = now - timedelta(days=now.weekday())
    sun = mon + timedelta(days=6)
    prev_mon = mon - timedelta(days=7)
    prev_sun = mon - timedelta(days=1)

    csv_path = _find_journal_csv()
    this = _week_stats(_parse_journal_range(csv_path, mon, sun)) if csv_path else {"days": 0, "dates": set(), "mood_avg": 0, "fitness_days": 0, "cycling_days": 0, "cycling_miles": 0.0, "strength_days": 0}
    prev = _week_stats(_parse_journal_range(csv_path, prev_mon, prev_sun)) if csv_path else {"days": 0, "dates": set(), "mood_avg": 0, "fitness_days": 0, "cycling_days": 0, "cycling_miles": 0.0, "strength_days": 0}
    kanban   = _get_kanban()
    upcoming = _get_next_week_reminders()

    date_range = f"{mon.strftime('%b %d')} – {sun.strftime('%b %d')}"
    lines: list[str] = []
    lines.append(f"📋 *Week in Review — {date_range}*\n")

    # --- Journal Recap (AI summary) ---
    try:
        recap = generate_recap(mon)
        if recap and "No entries" not in recap:
            lines.append(recap)
            lines.append("")
    except Exception as e:
        print(f"Failed to generate journal recap: {e}", file=sys.stderr)

    # --- Stats ---
    if this["days"] > 0:
        mood_line = f"• Mood: {this['mood_avg']}/5"
        if prev["mood_avg"]:
            mood_line += f" (was {prev['mood_avg']})"
        lines.append("*This week:*")
        lines.append(f"• Journal: {this['days']}/7 days")
        lines.append(mood_line)
        lines.append(f"• Fitness: {this['fitness_days']}/{this['days']} days")
        lines.append(f"• Cycling: {this['cycling_days']} days, {this['cycling_miles']} mi")
        lines.append(f"• Strength: {this['strength_days']}/{this['days']} days")
        lines.append("")
    else:
        lines.append("*No journal entries found this week.*\n")

    # --- Health Stats (Oura + Cycling) ---
    try:
        health_stats = get_week_health_stats(mon, sun)
        health_summary = format_health_summary(health_stats)
        if health_summary.strip():
            lines.append(health_summary)
    except Exception as e:
        print(f"Failed to fetch health stats: {e}", file=sys.stderr)

    # --- Nudges ---
    nudges = _compute_nudges(this, prev, kanban)
    if nudges:
        lines.append("*Worth noticing:*")
        for n in nudges:
            lines.append(f"• {n}")
        lines.append("")

    # --- Kanban snapshot ---
    if any(kanban.values()):
        lines.append("*Kanban:*")
        for task in kanban.get("in_progress", []):
            lines.append(f"• 🔄 {task}")
        for task in kanban.get("todo", []):
            lines.append(f"• ⬜ {task}")
        for task in kanban.get("done", []):
            lines.append(f"• ✓ {task}")
        lines.append("")

    # --- Next week ---
    if upcoming:
        lines.append("*Next week:*")
        for r in upcoming:
            lines.append(f"• {r}")

    return "\n".join(lines)


def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("No Telegram token configured", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        return False


def _save_to_obsidian(text: str):
    """Save to Research/Briefs/weekly-review-YYYY-MM-DD.md"""
    try:
        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(TZ).strftime("%Y-%m-%d")
        out = BRIEFS_DIR / f"weekly-review-{date_str}.md"
        out.write_text(f"---\ndate: \"{date_str}\"\ntype: weekly-review\n---\n\n{text}\n")
    except Exception as e:
        print(f"Could not save to Obsidian: {e}", file=sys.stderr)


def main():
    print(f"[{datetime.now()}] Running weekly review…")

    # Backup week's journal entries
    try:
        backup_path = backup_week()
        if backup_path:
            print(f"✓ Journal backup: {backup_path.name}")
    except Exception as e:
        print(f"Warning: Journal backup failed: {e}", file=sys.stderr)

    review = _format_review()
    print(review)
    _save_to_obsidian(review)
    _send_telegram(review)
    print(f"[{datetime.now()}] Done")


if __name__ == "__main__":
    main()
