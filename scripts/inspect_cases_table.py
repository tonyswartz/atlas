#!/usr/bin/env python3
"""Print cases table schema and one sample row. Run with: envchain atlas python3 scripts/inspect_cases_table.py"""
import os
import sys
import psycopg2
from urllib.parse import urlparse

def main():
    db_url = os.getenv("LEGALKANBAN")
    if not db_url:
        print("LEGALKANBAN not set", file=sys.stderr)
        sys.exit(1)
    r = urlparse(db_url)
    conn = psycopg2.connect(
        database=r.path[1:], user=r.username, password=r.password,
        host=r.hostname, port=r.port
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cases'
        ORDER BY ordinal_position;
    """)
    print("=== cases table columns ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} (nullable={row[2]})")
    cur.execute("SELECT * FROM cases LIMIT 1")
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    print("\n=== Sample row (first case) ===")
    if row:
        for i, c in enumerate(cols):
            print(f"  {c} = {row[i]}")
    else:
        print("  (no rows)")
    conn.close()

if __name__ == "__main__":
    main()
