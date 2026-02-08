#!/usr/bin/env python3
"""
MindsetLog Database Sync

Reads journal entries directly from MindsetLog's PostgreSQL database.
Most secure option - no OAuth, no API calls, no credentials.
"""

import csv
import json
import os
import sys
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
STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "mindsetlog_sync_state.json"

# PostgreSQL connection
# Supports either DATABASE_URL or individual connection parameters
DATABASE_URL = os.environ.get("MINDSETLOG_DB_URL", "")
POSTGRES_HOST = os.environ.get("MINDSETLOG_DB_HOST", "localhost")
POSTGRES_PORT = os.environ.get("MINDSETLOG_DB_PORT", "5432")
POSTGRES_DB = os.environ.get("MINDSETLOG_DB_NAME", "mindsetlog")
POSTGRES_USER = os.environ.get("MINDSETLOG_DB_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("MINDSETLOG_DB_PASSWORD", "")
MINDSETLOG_USER_EMAIL = os.environ.get("MINDSETLOG_EMAIL", "")


def _load_last_sync_time() -> datetime | None:
    """Load the timestamp of the last successful sync."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                timestamp_str = state.get("last_sync")
                if timestamp_str:
                    return datetime.fromisoformat(timestamp_str)
    except Exception as e:
        print(f"Warning: Could not load sync state: {e}", file=sys.stderr)
    return None


def _save_last_sync_time(timestamp: datetime):
    """Save the timestamp of the last successful sync."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump({
                "last_sync": timestamp.isoformat(),
                "last_sync_readable": timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save sync state: {e}", file=sys.stderr)


def _connect_db():
    """Connect to MindsetLog PostgreSQL database."""
    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
        return None

    try:
        # Prefer DATABASE_URL if available (simpler)
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
        else:
            # Fall back to individual connection parameters
            conn = psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD
            )
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}", file=sys.stderr)
        return None


def sync_recent_entries(days_back: int = 14, force_full: bool = False) -> bool:
    """
    Sync recent journal entries from MindsetLog database to Obsidian CSV.
    Uses incremental sync (only fetches new entries since last sync) unless force_full=True.

    Args:
        days_back: Number of days for full sync fallback (default 14)
        force_full: Force full sync instead of incremental (default False)

    Returns:
        True if sync successful, False otherwise
    """
    if not MINDSETLOG_USER_EMAIL:
        print("Error: MINDSETLOG_EMAIL required in .env", file=sys.stderr)
        return False

    conn = _connect_db()
    if not conn:
        return False

    try:
        cursor = conn.cursor()

        # Get user ID from email
        cursor.execute("SELECT id, timezone FROM users WHERE email = %s", (MINDSETLOG_USER_EMAIL,))
        user_row = cursor.fetchone()
        if not user_row:
            print(f"Error: User {MINDSETLOG_USER_EMAIL} not found in database", file=sys.stderr)
            return False

        user_id, user_timezone = user_row
        user_tz = ZoneInfo(user_timezone or "America/Los_Angeles")

        # Determine sync strategy
        now = datetime.now(user_tz)
        last_sync = _load_last_sync_time() if not force_full else None

        if last_sync:
            # Incremental sync - only fetch entries newer than last sync
            start_date = last_sync
            end_date = now
            print(f"[{datetime.now()}] Incremental sync: fetching entries since {start_date.strftime('%Y-%m-%d %H:%M:%S')}...")
        else:
            # Full sync - fetch last N days
            start_date = now - timedelta(days=days_back)
            end_date = now
            print(f"[{datetime.now()}] Full sync: fetching last {days_back} days...")

        print(f"Fetching entries for user ID {user_id} from {start_date.date()} to {end_date.date()}...")

        # Query journal entries
        query = """
            SELECT
                date,
                COALESCE(work_answer, '') || ' ' || COALESCE(family_answer, '') || ' ' || COALESCE(personal_answer, '') as entry_text,
                diet_goal,
                fitness_goal,
                water_goal,
                strength_goal,
                mood_rating,
                alcohol_consumed,
                did_cycle,
                cycling_miles
            FROM journal_entries
            WHERE user_id = %s
              AND date >= %s
              AND date <= %s
            ORDER BY date ASC
        """

        cursor.execute(query, (user_id, start_date, end_date))
        rows = cursor.fetchall()

        if not rows:
            print("No new entries found")
            cursor.close()
            conn.close()

            # Still save sync timestamp so we don't re-query the same range
            _save_last_sync_time(now)

            return True

        print(f"Found {len(rows)} entries")

        # Prepare CSV data
        csv_rows = []
        for row in rows:
            entry_date, entry_text, diet, fitness, water, strength, mood, alcohol, cycle, miles = row

            # Convert to user's timezone
            if entry_date.tzinfo is None:
                entry_date = entry_date.replace(tzinfo=ZoneInfo("UTC"))
            local_date = entry_date.astimezone(user_tz)

            csv_rows.append({
                'Date': local_date.strftime('%Y-%m-%d'),
                'Time': local_date.strftime('%H:%M:%S'),
                'Entry Text': entry_text.strip(),
                'Diet Goal': 'true' if diet else 'false',
                'Fitness Goal': 'true' if fitness else 'false',
                'Water Goal': 'true' if water else 'false',
                'Strength Goal': 'true' if strength else 'false',
                'Mood Rating': mood or '',
                'Alcohol Consumed': 'true' if alcohol else 'false',
                'Did Cycle': 'true' if cycle else 'false',
                'Cycling Miles': str(miles) if miles else '0'
            })

        cursor.close()
        conn.close()

        # Update or create CSV file
        JOURNALS_DIR.mkdir(parents=True, exist_ok=True)

        # Look for existing journal CSV
        existing_csvs = sorted(JOURNALS_DIR.glob("journal-entries-*.csv"),
                              key=lambda p: p.stat().st_mtime, reverse=True)

        fieldnames = ['Date', 'Time', 'Entry Text', 'Diet Goal', 'Fitness Goal', 'Water Goal',
                     'Strength Goal', 'Mood Rating', 'Alcohol Consumed', 'Did Cycle', 'Cycling Miles']

        if existing_csvs:
            # Update existing CSV
            main_csv = existing_csvs[0]
            print(f"Updating existing file: {main_csv.name}")

            # Read existing entries
            existing_rows = {}
            try:
                with open(main_csv, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        key = f"{row['Date']}_{row['Time']}"
                        existing_rows[key] = row
            except Exception as e:
                print(f"Error reading existing CSV: {e}", file=sys.stderr)
                return False

            # Merge new entries
            new_count = 0
            updated_count = 0

            for row in csv_rows:
                key = f"{row['Date']}_{row['Time']}"
                if key in existing_rows:
                    existing_rows[key] = row
                    updated_count += 1
                else:
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

                # Save sync timestamp for next incremental sync
                _save_last_sync_time(now)

                return True

            except Exception as e:
                print(f"Error writing CSV: {e}", file=sys.stderr)
                return False

        else:
            # Create new CSV file
            start_str = start_date.strftime("%Y-%m-%d")
            today_str = now.strftime("%Y-%m-%d")
            filename = f"journal-entries-{start_str}-to-{today_str}.csv"
            csv_path = JOURNALS_DIR / filename
            print(f"Creating new file: {filename}")

            try:
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(csv_rows)

                print(f"✓ Created with {len(csv_rows)} entries")

                # Save sync timestamp for next incremental sync
                _save_last_sync_time(now)

                return True
            except Exception as e:
                print(f"Error creating CSV: {e}", file=sys.stderr)
                return False

    except Exception as e:
        print(f"Sync error: {e}", file=sys.stderr)
        if conn:
            conn.close()
        return False


def main():
    """Sync recent entries from MindsetLog database."""
    success = sync_recent_entries(days_back=14)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
