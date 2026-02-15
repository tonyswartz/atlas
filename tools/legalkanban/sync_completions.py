#!/usr/bin/env python3
"""
Sync completed tasks from Tony Tasks.md back to LegalKanban

Runs periodically to mark tasks as completed in LegalKanban when checked off locally.
"""
import os
import re
import sys
import psycopg2
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

# Constants
VAULT_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
TASKS_FILE = VAULT_PATH / "Tony Tasks.md"


def extract_completed_task_ids(content):
    """Extract LegalKanban task IDs from completed tasks."""
    # Pattern: - [x] ... [LK-123]
    pattern = r'- \[x\].*?\[LK-(\d+)\]'
    matches = re.findall(pattern, content, re.IGNORECASE)
    return [int(task_id) for task_id in matches]


def mark_tasks_complete(task_ids):
    """Mark tasks as completed in LegalKanban database."""
    if not task_ids:
        print("No tasks to mark complete")
        return

    db_url = os.getenv("LEGALKANBAN")
    if not db_url:
        print("ERROR: LEGALKANBAN environment variable not set")
        sys.exit(1)

    result = urlparse(db_url)

    try:
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        cur = conn.cursor()

        # Mark tasks as completed
        now = datetime.now()
        cur.execute("""
            UPDATE tasks
            SET completed = true, completed_at = %s, updated_at = %s
            WHERE id = ANY(%s) AND completed = false
            RETURNING id, title;
        """, (now, now, task_ids))

        updated_tasks = cur.fetchall()
        conn.commit()

        if updated_tasks:
            print(f"✓ Marked {len(updated_tasks)} tasks as complete in LegalKanban:")
            for task_id, title in updated_tasks:
                print(f"  - #{task_id}: {title}")
        else:
            print("No tasks needed updating (already marked complete or not found)")

        cur.close()
        conn.close()

        return len(updated_tasks)

    except Exception as e:
        print(f"ERROR marking tasks complete: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def clean_completed_tasks():
    """Remove completed LegalKanban tasks from Tony Tasks.md."""
    if not TASKS_FILE.exists():
        print(f"ERROR: Tasks file not found: {TASKS_FILE}")
        sys.exit(1)

    with open(TASKS_FILE, 'r') as f:
        lines = f.readlines()

    # Filter out completed LegalKanban tasks
    new_lines = []
    removed_count = 0

    for line in lines:
        # Check if this is a completed LegalKanban task
        if re.search(r'- \[x\].*?\[LK-\d+\]', line, re.IGNORECASE):
            removed_count += 1
            continue  # Skip this line
        new_lines.append(line)

    # Write back
    with open(TASKS_FILE, 'w') as f:
        f.writelines(new_lines)

    if removed_count > 0:
        print(f"✓ Removed {removed_count} completed tasks from {TASKS_FILE}")

    return removed_count


def sync_completions():
    """Sync completed tasks from local to LegalKanban."""
    # Read tasks file
    if not TASKS_FILE.exists():
        print(f"ERROR: Tasks file not found: {TASKS_FILE}")
        sys.exit(1)

    with open(TASKS_FILE, 'r') as f:
        content = f.read()

    # Extract completed task IDs
    completed_ids = extract_completed_task_ids(content)

    if not completed_ids:
        print("No completed LegalKanban tasks found")
        return

    print(f"Found {len(completed_ids)} completed LegalKanban tasks")

    # Mark tasks complete in database
    updated_count = mark_tasks_complete(completed_ids)

    # Clean up completed tasks from local file
    if updated_count > 0:
        clean_completed_tasks()


if __name__ == "__main__":
    sync_completions()
