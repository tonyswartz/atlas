#!/usr/bin/env python3
"""
Bidirectional sync between Tony Tasks.md and LegalKanban

Syncs:
  - Task completions: Tony Tasks → LegalKanban
  - Due date changes: Tony Tasks → LegalKanban
  - New/updated tasks: LegalKanban → Tony Tasks
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
USER_ID = 1


def parse_local_tasks(content):
    """Parse LegalKanban tasks from Tony Tasks.md."""
    # Pattern: - [x] Title ... 📅 YYYY-MM-DD [LK-123]
    # or:      - [ ] Title ... 📅 YYYY-MM-DD [LK-123]
    pattern = r'- \[([ x])\] (.+?) \[LK-(\d+)\]'

    tasks = {}
    for match in re.finditer(pattern, content):
        completed = match.group(1) == 'x'
        full_line = match.group(2)
        task_id = int(match.group(3))

        # Extract due date if present
        due_date = None
        date_match = re.search(r'📅 (\d{4}-\d{2}-\d{2})', full_line)
        if date_match:
            due_date = date_match.group(1)

        tasks[task_id] = {
            'id': task_id,
            'completed': completed,
            'due_date': due_date,
            'full_line': full_line
        }

    return tasks


def fetch_remote_tasks():
    """Fetch tasks from LegalKanban database."""
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

        cur.execute("""
            SELECT id, title, due_date, completed
            FROM tasks
            WHERE assignee_id = %s
            ORDER BY id;
        """, (USER_ID,))

        tasks = {}
        for row in cur.fetchall():
            task_id, title, due_date, completed = row
            tasks[task_id] = {
                'id': task_id,
                'title': title,
                'due_date': due_date.strftime('%Y-%m-%d') if due_date else None,
                'completed': completed
            }

        cur.close()
        conn.close()

        return tasks

    except Exception as e:
        print(f"ERROR fetching tasks: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def update_remote_task(task_id, updates):
    """Update a task in LegalKanban database."""
    db_url = os.getenv("LEGALKANBAN")
    if not db_url:
        return False

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

        # Build update query dynamically
        set_parts = []
        params = []

        if 'completed' in updates:
            set_parts.append("completed = %s")
            params.append(updates['completed'])
            if updates['completed']:
                set_parts.append("completed_at = %s")
                params.append(datetime.now())

        if 'due_date' in updates:
            set_parts.append("due_date = %s")
            # Convert string date to datetime
            if updates['due_date']:
                params.append(datetime.strptime(updates['due_date'], '%Y-%m-%d'))
            else:
                params.append(None)

        # Always update updated_at
        set_parts.append("updated_at = %s")
        params.append(datetime.now())

        # Add task_id at the end
        params.append(task_id)

        query = f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = %s RETURNING title;"

        cur.execute(query, params)
        result = cur.fetchone()
        conn.commit()

        cur.close()
        conn.close()

        return result is not None

    except Exception as e:
        print(f"ERROR updating task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


def sync_to_remote(local_tasks, remote_tasks):
    """Sync changes from local to remote (completions and due dates)."""
    changes = []

    for task_id, local_task in local_tasks.items():
        if task_id not in remote_tasks:
            continue

        remote_task = remote_tasks[task_id]
        updates = {}

        # Check completion status
        if local_task['completed'] and not remote_task['completed']:
            updates['completed'] = True

        # Check due date changes
        if local_task['due_date'] != remote_task['due_date']:
            updates['due_date'] = local_task['due_date']

        # Apply updates
        if updates:
            if update_remote_task(task_id, updates):
                change_desc = []
                if 'completed' in updates:
                    change_desc.append("marked complete")
                if 'due_date' in updates:
                    old = remote_task['due_date'] or 'none'
                    new = updates['due_date'] or 'none'
                    change_desc.append(f"due date {old} → {new}")

                changes.append({
                    'id': task_id,
                    'title': remote_task['title'],
                    'changes': ', '.join(change_desc)
                })

    return changes


def clean_completed_tasks():
    """Remove completed LegalKanban tasks from Tony Tasks.md."""
    if not TASKS_FILE.exists():
        return 0

    with open(TASKS_FILE, 'r') as f:
        lines = f.readlines()

    new_lines = []
    removed_count = 0

    for line in lines:
        if re.search(r'- \[x\].*?\[LK-\d+\]', line):
            removed_count += 1
            continue
        new_lines.append(line)

    with open(TASKS_FILE, 'w') as f:
        f.writelines(new_lines)

    return removed_count


def main():
    """Run bidirectional sync."""
    print("=== LegalKanban Bidirectional Sync ===\n")

    # Read local tasks
    if not TASKS_FILE.exists():
        print(f"ERROR: Tasks file not found: {TASKS_FILE}")
        sys.exit(1)

    with open(TASKS_FILE, 'r') as f:
        content = f.read()

    local_tasks = parse_local_tasks(content)
    print(f"Found {len(local_tasks)} LegalKanban tasks in local file")

    # Fetch remote tasks
    remote_tasks = fetch_remote_tasks()
    print(f"Found {len(remote_tasks)} total tasks in LegalKanban database\n")

    # Sync local changes to remote
    print("Syncing local changes to LegalKanban...")
    changes = sync_to_remote(local_tasks, remote_tasks)

    if changes:
        print(f"✓ Updated {len(changes)} tasks in LegalKanban:")
        for change in changes:
            print(f"  - #{change['id']}: {change['title']} ({change['changes']})")

        # Clean up completed tasks
        removed = clean_completed_tasks()
        if removed > 0:
            print(f"\n✓ Removed {removed} completed tasks from local file")
    else:
        print("  No changes to sync")

    print("\nSync complete!")


if __name__ == "__main__":
    main()
