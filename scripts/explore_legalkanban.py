#!/usr/bin/env python3
"""
Explore LegalKanban database structure
"""
import os
import sys
import psycopg2
from urllib.parse import urlparse

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

        # Get all tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cur.fetchall()

        print("=== TABLES ===")
        for table in tables:
            print(f"  - {table[0]}")
        print()

        # Look for task-related tables
        task_tables = [t[0] for t in tables if 'task' in t[0].lower() or 'todo' in t[0].lower()]

        if task_tables:
            print("=== TASK-RELATED TABLES ===")
            for table_name in task_tables:
                print(f"\n{table_name}:")

                # Get column info
                cur.execute(f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = '{table_name}'
                    ORDER BY ordinal_position;
                """)
                columns = cur.fetchall()

                print("  Columns:")
                for col in columns:
                    print(f"    - {col[0]} ({col[1]}, nullable: {col[2]})")

                # Get sample count
                cur.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cur.fetchone()[0]
                print(f"  Total rows: {count}")

                # Get sample for user 1 if user_id column exists
                col_names = [col[0] for col in columns]
                if 'user_id' in col_names:
                    cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE user_id = 1;")
                    user_count = cur.fetchone()[0]
                    print(f"  Rows for user_id=1: {user_count}")

                    if user_count > 0:
                        # Get sample rows
                        cur.execute(f"SELECT * FROM {table_name} WHERE user_id = 1 LIMIT 3;")
                        samples = cur.fetchall()
                        print(f"\n  Sample rows for user 1:")
                        for sample in samples:
                            print(f"    {sample}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
