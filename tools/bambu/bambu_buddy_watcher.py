#!/usr/bin/env python3
"""BambuBuddy integration for print completion tracking.

Goals:
- Query BambuBuddy's SQLite database for completed prints
- Track which prints have been logged to JeevesUI (avoid duplicates)
- Write pending prompt entries for new completions
- Works with ALL print types: BambuStudio, Handy app, SD card

Why BambuBuddy instead of FTP:
- FTP only sees BambuStudio prints (misses Handy app)
- BambuBuddy tracks everything in real-time
- Has filament data, timestamps, print names already

State Tracking:
- data/bambu_buddy_last_id.txt: stores the highest print archive ID we've processed
- Only process prints with ID > last_processed_id
- This ensures we never duplicate prompts, even if the script is restarted
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

BAMBU_BUDDY_DB = Path.home() / "apps/bambuddy/bambuddy.db"
STATE_FILE = Path("/Users/printer/atlas/data/bambu_buddy_last_id.txt")
PROMPT_FILE = Path("/Users/printer/atlas/memory/bambu-pending-prompts.md")
LOG_PATH = Path("/Users/printer/atlas/logs/bambu-buddy-watcher.log")

STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    LOG_PATH.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")


def load_last_processed_id() -> int:
    """Load the highest print archive ID we've already processed."""
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip())
        except ValueError:
            return 0
    return 0


def save_last_processed_id(print_id: int) -> None:
    """Save the highest print archive ID we've processed."""
    STATE_FILE.write_text(str(print_id), encoding="utf-8")


def get_new_completed_prints(last_id: int) -> list[dict]:
    """Query BambuBuddy for completed prints with ID > last_id."""
    if not BAMBU_BUDDY_DB.exists():
        log(f"BambuBuddy database not found at {BAMBU_BUDDY_DB}")
        return []

    try:
        conn = sqlite3.connect(str(BAMBU_BUDDY_DB))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query for completed prints newer than our last processed ID
        query = """
            SELECT
                id,
                filename,
                print_name,
                filament_used_grams,
                filament_type,
                filament_color,
                status,
                completed_at,
                extra_data
            FROM print_archives
            WHERE status = 'completed' AND id > ?
            ORDER BY id ASC
        """

        cursor.execute(query, (last_id,))
        rows = cursor.fetchall()
        conn.close()

        prints = []
        for row in rows:
            # Parse extra_data JSON for additional context
            extra = {}
            if row["extra_data"]:
                try:
                    extra = json.loads(row["extra_data"])
                except json.JSONDecodeError:
                    pass

            # Get print name: prefer print_name, fallback to subtask name, fallback to filename
            name = row["print_name"] or extra.get("original_subtask") or row["filename"]

            prints.append({
                "id": row["id"],
                "name": name,
                "filename": row["filename"],
                "filament_grams": row["filament_used_grams"],
                "filament_type": row["filament_type"],
                "filament_color": row["filament_color"],
                "completed_at": row["completed_at"],
                "is_handy_app": row["filename"] == "/data/Metadata/plate_1.gcode",
            })

        return prints

    except sqlite3.Error as e:
        log(f"SQLite error querying BambuBuddy: {e}")
        return []


def write_pending_prompt(print_data: dict) -> None:
    """Write a pending prompt entry for a completed print."""
    # Format timestamp
    try:
        dt = datetime.fromisoformat(print_data["completed_at"].replace("Z", "+00:00"))
        ts = dt.strftime("%y-%m-%d %H:%M")
    except Exception:
        ts = datetime.now().strftime("%y-%m-%d %H:%M")

    # Build print name with source indicator
    name = print_data["name"]
    if print_data["is_handy_app"]:
        name = f"{name} (Handy app)"

    # Initialize prompt file if needed
    if not PROMPT_FILE.exists():
        PROMPT_FILE.write_text("# Bambu Pending Prompts\n\n", encoding="utf-8")

    existing = PROMPT_FILE.read_text(encoding="utf-8").strip()
    if existing == "(see attached image)":
        PROMPT_FILE.write_text("# Bambu Pending Prompts\n\n", encoding="utf-8")

    # Build YAML-style prompt block
    parts = [
        "---",
        f'timestamp: "{ts}"',
        f'print_name: "{name}"',
        f'bambu_buddy_id: {print_data["id"]}',
    ]

    if print_data["filename"]:
        parts.append(f'source_file: "{print_data["filename"]}"')

    if print_data["filament_grams"]:
        parts.append(f'filament_grams: {print_data["filament_grams"]}')

    if print_data["filament_type"]:
        parts.append(f'filament_type: "{print_data["filament_type"]}"')

    if print_data["filament_color"]:
        parts.append(f'filament_color: "{print_data["filament_color"]}"')

    parts.append("status: pending")
    parts.append("target: jeevesui")
    parts.append("---")

    # Append to file
    base = PROMPT_FILE.read_text(encoding="utf-8")
    if base and not base.endswith("\n"):
        base += "\n"
    PROMPT_FILE.write_text(base + "\n".join(parts) + "\n", encoding="utf-8")

    log(f"Queued prompt for: {name} (BambuBuddy ID {print_data['id']})")


def main() -> int:
    last_id = load_last_processed_id()
    log(f"Checking for new prints (last processed ID: {last_id})")

    new_prints = get_new_completed_prints(last_id)

    if not new_prints:
        log("No new completed prints")
        return 0

    log(f"Found {len(new_prints)} new completed print(s)")

    # Process each new print
    highest_id = last_id
    for print_data in new_prints:
        write_pending_prompt(print_data)
        highest_id = max(highest_id, print_data["id"])

    # Save the highest ID we've now processed
    save_last_processed_id(highest_id)
    log(f"Processed through ID {highest_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
