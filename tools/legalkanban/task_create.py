#!/usr/bin/env python3
"""
Create a task in LegalKanban or local task system

Usage:
  python task_create.py --title "Task title" --system legalkanban --case-id 123 --priority high --due-date 2026-02-15
  python task_create.py --title "Buy groceries" --system local
"""
import os
import sys
import argparse
import json
import psycopg2
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path

# Constants
VAULT_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
TASKS_FILE = VAULT_PATH / "Tony Tasks.md"
USER_ID = 1


def create_legalkanban_task(title, case_id=None, priority='medium', due_date=None, description=''):
    """Create a task in LegalKanban database."""
    db_url = os.getenv("LEGALKANBAN")
    if not db_url:
        return {"success": False, "error": "LEGALKANBAN environment variable not set"}

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

        # Parse due_date if string
        if due_date and isinstance(due_date, str):
            try:
                due_date = datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                return {"success": False, "error": f"Invalid due date format: {due_date}. Use YYYY-MM-DD"}

        # Insert task
        cur.execute("""
            INSERT INTO tasks (
                title,
                description,
                assignee_id,
                case_id,
                priority,
                status,
                due_date,
                completed,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            title,
            description,
            USER_ID,
            case_id,
            priority.lower(),
            'todo',
            due_date,
            False,
            datetime.now(),
            datetime.now()
        ))

        task_id = cur.fetchone()[0]
        conn.commit()

        # Resolve case display name (id, title only). Use title; client name often first part before ' - '
        case_name = None
        if case_id:
            try:
                cur.execute("SELECT title FROM cases WHERE id = %s", (case_id,))
                row = cur.fetchone()
                if row and row[0]:
                    ctitle = (row[0] or "").strip()
                    case_name = ctitle.split(" - ")[0].strip() if " - " in ctitle else ctitle[:40]
            except Exception:
                pass

        cur.close()
        conn.close()

        out = {
            "success": True,
            "task_id": task_id,
            "system": "legalkanban",
            "title": title,
            "case_id": case_id,
            "priority": priority,
            "due_date": due_date.strftime('%Y-%m-%d') if due_date else None
        }
        if case_name:
            out["case_name"] = case_name
        return out

    except Exception as e:
        return {"success": False, "error": str(e)}


def create_local_task(title, priority='medium', due_date=None):
    """Create a task in local Tony Tasks.md."""
    try:
        if not TASKS_FILE.exists():
            return {"success": False, "error": f"Tasks file not found: {TASKS_FILE}"}

        # Read current file
        with open(TASKS_FILE, 'r') as f:
            content = f.read()

        # Format task line
        task_line = f"- [ ] {title}"

        # Add priority indicator
        if priority == 'high':
            task_line += " 🔴"
        elif priority == 'medium':
            task_line += " 🟡"

        # Add due date if provided
        if due_date:
            if isinstance(due_date, str):
                task_line += f" 📅 {due_date}"
            else:
                task_line += f" 📅 {due_date.strftime('%Y-%m-%d')}"

        # Find "Things to Do" section or create it
        if "## Things to Do" in content:
            # Add to existing section
            lines = content.split('\n')
            new_lines = []
            added = False

            for i, line in enumerate(lines):
                new_lines.append(line)
                if line.strip() == "## Things to Do" and not added:
                    # Add task after the header
                    new_lines.append(task_line)
                    added = True

            content = '\n'.join(new_lines)
        else:
            # Add new section at the top
            content = f"## Things to Do\n{task_line}\n\n" + content

        # Write back
        with open(TASKS_FILE, 'w') as f:
            f.write(content)

        return {
            "success": True,
            "system": "local",
            "title": title,
            "priority": priority,
            "due_date": due_date if isinstance(due_date, str) else (due_date.strftime('%Y-%m-%d') if due_date else None)
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description='Create a task in LegalKanban or local system')
    parser.add_argument('--title', required=True, help='Task title')
    parser.add_argument('--system', required=True, choices=['legalkanban', 'local'],
                        help='Where to create the task')
    parser.add_argument('--case-id', type=int, help='Case ID (LegalKanban only)')
    parser.add_argument('--priority', choices=['high', 'medium', 'low'], default='medium',
                        help='Task priority')
    parser.add_argument('--due-date', help='Due date (YYYY-MM-DD)')
    parser.add_argument('--description', default='', help='Task description (LegalKanban only)')
    parser.add_argument('--json', action='store_true', help='Output JSON')

    args = parser.parse_args()

    if args.system == 'legalkanban':
        result = create_legalkanban_task(
            title=args.title,
            case_id=args.case_id,
            priority=args.priority,
            due_date=args.due_date,
            description=args.description
        )
    else:
        result = create_local_task(
            title=args.title,
            priority=args.priority,
            due_date=args.due_date
        )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result['success']:
            print(f"✓ Task created in {result['system']}")
            print(f"  Title: {result['title']}")
            if result.get('case_name'):
                print(f"  Case: {result['case_name']}")
            elif result.get('case_id'):
                print(f"  Case: #{result['case_id']}")
            print(f"  Priority: {result['priority']}")
            if result.get('due_date'):
                print(f"  Due: {result['due_date']}")
            if 'task_id' in result:
                print(f"  Task ID: {result['task_id']}")
        else:
            print(f"✗ Failed to create task: {result['error']}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
