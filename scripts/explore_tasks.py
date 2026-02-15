#!/usr/bin/env python3
"""
Explore LegalKanban tasks table for user 1
"""
import os
import sys
import psycopg2
from urllib.parse import urlparse
from datetime import datetime

def main():
    # Get database URL from environment (set via envchain)
    db_url = os.getenv("LEGALKANBAN")
    if not db_url:
        print("ERROR: LEGALKANBAN environment variable not set")
        sys.exit(1)

    # Parse the URL
    result = urlparse(db_url)

    try:
        # Connect to database
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        cur = conn.cursor()

        # Get distinct statuses
        cur.execute("SELECT DISTINCT status FROM tasks ORDER BY status;")
        statuses = cur.fetchall()
        print("=== TASK STATUSES ===")
        for status in statuses:
            print(f"  - {status[0]}")
        print()

        # Get distinct priorities
        cur.execute("SELECT DISTINCT priority FROM tasks ORDER BY priority;")
        priorities = cur.fetchall()
        print("=== TASK PRIORITIES ===")
        for priority in priorities:
            print(f"  - {priority[0]}")
        print()

        # Get tasks for user 1 (assignee_id = 1)
        cur.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE assignee_id = 1;
        """)
        count = cur.fetchone()[0]
        print(f"=== TASKS FOR USER 1 (assignee_id=1) ===")
        print(f"Total tasks: {count}\n")

        # Get incomplete tasks for user 1
        cur.execute("""
            SELECT COUNT(*) FROM tasks
            WHERE assignee_id = 1 AND completed = false;
        """)
        incomplete_count = cur.fetchone()[0]
        print(f"Incomplete tasks: {incomplete_count}\n")

        # Get sample tasks for user 1
        cur.execute("""
            SELECT id, title, description, status, priority, due_date, completed, created_at, case_id
            FROM tasks
            WHERE assignee_id = 1 AND completed = false
            ORDER BY due_date NULLS LAST, created_at DESC
            LIMIT 10;
        """)
        tasks = cur.fetchall()

        print("=== SAMPLE INCOMPLETE TASKS ===")
        for task in tasks:
            task_id, title, desc, status, priority, due_date, completed, created_at, case_id = task
            print(f"\nTask #{task_id}")
            print(f"  Title: {title}")
            print(f"  Description: {desc[:100] if desc else 'None'}...")
            print(f"  Status: {status}")
            print(f"  Priority: {priority}")
            print(f"  Due: {due_date if due_date else 'No due date'}")
            print(f"  Case ID: {case_id if case_id else 'None'}")
            print(f"  Created: {created_at}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
