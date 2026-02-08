#!/usr/bin/env python3
"""
Weekly Journal Backup

Backs up the past week's journal entries (Mon–Sun) to a dated file.
Runs every Friday via weekly_review.py integration.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Config
TZ = ZoneInfo("America/Los_Angeles")
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
JOURNALS_DIR = OBSIDIAN_VAULT / "Journals"
BACKUPS_DIR = JOURNALS_DIR / "Backups"


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
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                try:
                    d = datetime.strptime(row["Date"].strip(), "%Y-%m-%d").date()
                    if start.date() <= d <= end.date():
                        rows.append(row)
                except (KeyError, ValueError):
                    continue
            return rows, fieldnames
    except Exception as e:
        print(f"Journal parse error: {e}", file=sys.stderr)
        return [], []


def backup_week(week_start: datetime = None) -> Path | None:
    """
    Backup the week's journal entries to a dated CSV file.

    Args:
        week_start: Monday of the week to backup (defaults to current week)

    Returns:
        Path to the backup file, or None if backup failed
    """
    now = datetime.now(TZ)

    # Default to current week's Monday
    if week_start is None:
        week_start = now - timedelta(days=now.weekday())

    week_end = week_start + timedelta(days=6)

    csv_path = _find_journal_csv()
    if not csv_path:
        print("No journal CSV found", file=sys.stderr)
        return None

    entries, fieldnames = _parse_week_entries(csv_path, week_start, week_end)

    if not entries:
        print(f"No entries found for week {week_start.date()} to {week_end.date()}", file=sys.stderr)
        return None

    # Create backups directory
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate backup filename: journal-backup-YYYY-MM-DD.csv (Monday's date)
    backup_filename = f"journal-backup-{week_start.strftime('%Y-%m-%d')}.csv"
    backup_path = BACKUPS_DIR / backup_filename

    # Write backup CSV
    try:
        with open(backup_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(entries)

        print(f"✓ Backed up {len(entries)} entries to {backup_path.name}")
        return backup_path

    except Exception as e:
        print(f"Failed to write backup: {e}", file=sys.stderr)
        return None


def main():
    """Run weekly backup for current week."""
    backup_path = backup_week()
    if backup_path:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
