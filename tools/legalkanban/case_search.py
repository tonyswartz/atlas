#!/usr/bin/env python3
"""
Search open cases in LegalKanban by name (e.g. last name).

Usage:
  python case_search.py "Nelson"
  python case_search.py "Smith" --json

Output: JSON list of matching open cases { id, name }. Prefers client_name for name.
"""
import os
import sys
import json
import argparse
import psycopg2
from urllib.parse import urlparse

# Use only id, title, closed (column-level grants). Name from title (client often before ' - ').
NAME_COLUMNS = ["title"]
CLOSED_BOOL_COLUMN = "closed"


def get_connection():
    db_url = os.getenv("LEGALKANBAN")
    if not db_url:
        return None, "LEGALKANBAN environment variable not set"
    try:
        result = urlparse(db_url)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port,
        )
        return conn, None
    except Exception as e:
        return None, str(e)


def get_cases_columns(conn):
    """Return (id_col, name_col, closed_col or None). Prefer client_name for display."""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cases'
        ORDER BY ordinal_position;
    """)
    rows = cur.fetchall()
    cur.close()
    if not rows:
        return None, None, None
    cols = {r[0]: r[1] for r in rows}
    id_col = "id" if "id" in cols else None
    name_col = "title" if "title" in cols and cols["title"] in ("character varying", "text", "varchar") else None
    if not name_col:
        for c in NAME_COLUMNS:
            if c in cols and cols[c] in ("character varying", "text", "varchar"):
                name_col = c
                break
    closed_col = CLOSED_BOOL_COLUMN if CLOSED_BOOL_COLUMN in cols and cols[CLOSED_BOOL_COLUMN] == "boolean" else None
    return id_col, name_col, closed_col


def search_cases(query: str, json_output: bool = False):
    if not query or not query.strip():
        out = {"success": False, "error": "Search query is required.", "cases": []}
        if json_output:
            print(json.dumps(out, indent=2))
        return out

    conn, err = get_connection()
    if err:
        out = {"success": False, "error": err, "cases": []}
        if json_output:
            print(json.dumps(out, indent=2))
        return out

    try:
        cur = conn.cursor()
        id_col, name_col, closed_col = get_cases_columns(conn)
        if not id_col or not name_col:
            out = {"success": False, "error": "Could not find cases table or name column.", "cases": []}
            if json_output:
                print(json.dumps(out, indent=2))
            return out

        pattern = f"%{query.strip()}%"
        if closed_col:
            sql = f"""
                SELECT {id_col}, {name_col}
                FROM cases
                WHERE ({name_col} ILIKE %s)
                  AND ({closed_col} IS NULL OR {closed_col} = false)
                ORDER BY {name_col}
                LIMIT 20;
            """
            cur.execute(sql, (pattern,))
        else:
            sql = f"SELECT {id_col}, {name_col} FROM cases WHERE {name_col} ILIKE %s ORDER BY {name_col} LIMIT 20;"
            cur.execute(sql, (pattern,))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        cases = [{"id": r[0], "name": (r[1] or "").strip()} for r in rows]
        out = {"success": True, "cases": cases}
        if json_output:
            print(json.dumps(out, indent=2))
        return out
    except Exception as e:
        if conn:
            conn.close()
        out = {"success": False, "error": str(e), "cases": []}
        if json_output:
            print(json.dumps(out, indent=2))
        return out


def main():
    parser = argparse.ArgumentParser(description="Search open LegalKanban cases by name")
    parser.add_argument("query", nargs="?", default="", help="Search string (e.g. last name)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()
    query = args.query.strip() if args.query else ""
    result = search_cases(query, json_output=True)
    if not result["success"]:
        sys.exit(1)
    if not args.json:
        for c in result["cases"]:
            print(f"  #{c['id']}: {c['name']}")


if __name__ == "__main__":
    main()
