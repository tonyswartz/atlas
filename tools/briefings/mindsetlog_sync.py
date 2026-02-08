#!/usr/bin/env python3
"""
MindsetLog Journal Sync

Pulls journal entries from MindsetLog API and updates the Obsidian CSV.
Runs daily to keep journal data fresh for backups and recaps.
"""

import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# Config
TZ = ZoneInfo("America/Los_Angeles")
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
JOURNALS_DIR = OBSIDIAN_VAULT / "Journals"

# MindsetLog API settings
MINDSETLOG_URL = os.environ.get("MINDSETLOG_URL", "http://localhost:5000")
MINDSETLOG_EMAIL = os.environ.get("MINDSETLOG_EMAIL", "")
MINDSETLOG_PASSWORD = os.environ.get("MINDSETLOG_PASSWORD", "")


def _login() -> str | None:
    """Login to MindsetLog and return session cookie."""
    if not MINDSETLOG_EMAIL or not MINDSETLOG_PASSWORD:
        print("Error: MINDSETLOG_EMAIL and MINDSETLOG_PASSWORD required in .env", file=sys.stderr)
        return None

    url = f"{MINDSETLOG_URL}/api/auth/login"
    payload = json.dumps({
        "email": MINDSETLOG_EMAIL,
        "password": MINDSETLOG_PASSWORD
    }).encode()

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Extract session cookie from response
            cookies = resp.getheader('Set-Cookie')
            if cookies:
                # Parse session cookie (format: "connect.sid=xxx; Path=/; ...")
                session = cookies.split(';')[0]
                return session
            return None
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        return None


def _fetch_entries(session_cookie: str, start_date: str, end_date: str) -> str | None:
    """Fetch journal entries CSV from MindsetLog API."""
    url = f"{MINDSETLOG_URL}/api/export/journal-entries-csv?startDate={start_date}&endDate={end_date}"

    try:
        req = urllib.request.Request(
            url,
            headers={"Cookie": session_cookie}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        print(f"Failed to fetch entries: {e}", file=sys.stderr)
        return None


def sync_recent_entries(days_back: int = 14) -> bool:
    """
    Sync recent journal entries from MindsetLog to Obsidian.

    Args:
        days_back: Number of days to sync (default 14)

    Returns:
        True if sync successful, False otherwise
    """
    print(f"[{datetime.now()}] Starting MindsetLog sync (last {days_back} days)...")

    # Login
    session = _login()
    if not session:
        return False

    # Calculate date range
    now = datetime.now(TZ)
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")

    print(f"Fetching entries from {start_date} to {end_date}...")

    # Fetch entries
    csv_content = _fetch_entries(session, start_date, end_date)
    if not csv_content:
        return False

    # Parse CSV content
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        print("No entries found")
        return True

    # Find or create main CSV file
    JOURNALS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = now.strftime("%Y-%m-%d")

    # Look for existing journal CSV
    existing_csvs = sorted(JOURNALS_DIR.glob("journal-entries-*.csv"),
                          key=lambda p: p.stat().st_mtime, reverse=True)

    if existing_csvs:
        # Update existing CSV (merge new entries)
        main_csv = existing_csvs[0]
        print(f"Updating existing file: {main_csv.name}")

        # Read existing entries
        existing_rows = {}
        try:
            with open(main_csv, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    key = f"{row['Date']}_{row['Time']}"
                    existing_rows[key] = row
        except Exception as e:
            print(f"Error reading existing CSV: {e}", file=sys.stderr)
            return False

        # Parse new entries
        new_reader = csv.DictReader(lines)
        new_count = 0
        updated_count = 0

        for row in new_reader:
            key = f"{row['Date']}_{row['Time']}"
            if key in existing_rows:
                # Update existing entry
                existing_rows[key] = row
                updated_count += 1
            else:
                # Add new entry
                existing_rows[key] = row
                new_count += 1

        # Write back merged data
        try:
            with open(main_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                # Sort by date and time
                sorted_rows = sorted(existing_rows.values(),
                                   key=lambda r: (r['Date'], r['Time']))
                writer.writerows(sorted_rows)

            print(f"✓ Synced: {new_count} new, {updated_count} updated")
            return True

        except Exception as e:
            print(f"Error writing CSV: {e}", file=sys.stderr)
            return False

    else:
        # Create new CSV file
        filename = f"journal-entries-{start_date}-to-{today_str}.csv"
        csv_path = JOURNALS_DIR / filename
        print(f"Creating new file: {filename}")

        try:
            csv_path.write_text(csv_content)
            entry_count = len(lines) - 1  # Subtract header
            print(f"✓ Created with {entry_count} entries")
            return True
        except Exception as e:
            print(f"Error creating CSV: {e}", file=sys.stderr)
            return False


def main():
    """Sync recent entries from MindsetLog."""
    success = sync_recent_entries(days_back=14)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
