#!/usr/bin/env python3
"""
Sync LegalKanban tasks (user 1) to Tony Tasks.md

Runs daily to keep LegalKanban tasks synchronized with the local task system.
"""
import os
import sys
import psycopg2
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

# Constants
VAULT_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
TASKS_FILE = VAULT_PATH / "Tony Tasks.md"
USER_ID = 1


def fetch_tasks():
    """Fetch incomplete tasks for user 1 from LegalKanban. Only tasks in open cases (or with no case) are included."""
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

        # Fetch incomplete tasks for user 1; only open cases (or no case). Uses cases.id, title, closed only.
        cur.execute("""
            SELECT
                t.id,
                t.title,
                t.description,
                t.status,
                t.priority,
                t.due_date,
                t.case_id,
                t.created_at,
                c.title AS case_title
            FROM tasks t
            LEFT JOIN cases c ON c.id = t.case_id
            WHERE t.assignee_id = %s AND t.completed = false
              AND (t.case_id IS NULL OR (c.closed IS NULL OR c.closed = false))
            ORDER BY
                CASE t.priority
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                ELSE 4
                END,
                t.due_date NULLS LAST,
                t.created_at DESC;
        """, (USER_ID,))

        tasks = cur.fetchall()
        cur.close()
        conn.close()

        return tasks

    except Exception as e:
        print(f"ERROR fetching tasks: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _case_display_name(case_title, case_id):
    """Use case title; first part before ' - ' (e.g. 'Nelson - 5A...' → 'Nelson'); fallback Case #id."""
    if case_title and str(case_title).strip():
        t = str(case_title).strip()
        if " - " in t:
            return t.split(" - ")[0].strip()
        return t[:40] + ("…" if len(t) > 40 else "")
    return None


def format_task(task):
    """Format a task as a markdown checkbox item. Case display from title (id, title, closed only on cases)."""
    task_id, title, desc, status, priority, due_date, case_id, created_at, case_title = task

    # Build the task line
    parts = [f"- [ ] {title}"]

    # Add priority indicator
    if priority == 'high':
        parts.append("🔴")
    elif priority == 'medium':
        parts.append("🟡")

    # Add case reference: from case title (client name often first part before ' - ')
    if case_id:
        display = _case_display_name(case_title, case_id)
        if display:
            parts.append(f"({display})")
        else:
            parts.append(f"(Case #{case_id})")

    # Add due date if applicable
    if due_date:
        if isinstance(due_date, datetime):
            due_str = due_date.strftime("%Y-%m-%d")
        else:
            due_str = str(due_date)
        parts.append(f"📅 {due_str}")

    # Add task ID for tracking
    parts.append(f"[LK-{task_id}]")

    return " ".join(parts)


def sync_tasks():
    """Sync LegalKanban tasks to Tony Tasks.md."""
    # Fetch tasks
    tasks = fetch_tasks()
    print(f"Fetched {len(tasks)} incomplete tasks from LegalKanban")

    if not tasks:
        print("No tasks to sync")
        return

    # Read current tasks file
    if not TASKS_FILE.exists():
        print(f"ERROR: Tasks file not found: {TASKS_FILE}")
        sys.exit(1)

    with open(TASKS_FILE, 'r') as f:
        content = f.read()

    # Find or create LegalKanban section
    lk_marker_start = "## LegalKanban Tasks"
    lk_marker_end = "## "  # Next section marker

    # Format new tasks
    task_lines = [format_task(task) for task in tasks]
    new_section = f"{lk_marker_start}\n" + "\n".join(task_lines) + "\n\n"

    # Check if section exists
    if lk_marker_start in content:
        # Replace existing section
        start_idx = content.index(lk_marker_start)

        # Find end of section (next ## or end of file)
        remaining = content[start_idx + len(lk_marker_start):]
        next_section = remaining.find("\n## ")

        if next_section != -1:
            # There's another section after this
            end_idx = start_idx + len(lk_marker_start) + next_section + 1
            new_content = content[:start_idx] + new_section + content[end_idx:]
        else:
            # This is the last section
            new_content = content[:start_idx] + new_section
    else:
        # Add new section at the end
        new_content = content.rstrip() + "\n\n" + new_section

    # Write updated content
    with open(TASKS_FILE, 'w') as f:
        f.write(new_content)

    print(f"✓ Synced {len(tasks)} tasks to {TASKS_FILE}")
    print("\nSummary by priority:")

    high_count = sum(1 for t in tasks if t[4] == 'high')
    medium_count = sum(1 for t in tasks if t[4] == 'medium')
    low_count = sum(1 for t in tasks if t[4] == 'low')

    if high_count > 0:
        print(f"  🔴 High: {high_count}")
    if medium_count > 0:
        print(f"  🟡 Medium: {medium_count}")
    if low_count > 0:
        print(f"  Low: {low_count}")


if __name__ == "__main__":
    sync_tasks()
