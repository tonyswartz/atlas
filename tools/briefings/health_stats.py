#!/usr/bin/env python3
"""
Health Stats Fetcher

Pulls Oura and cycling data from MindsetLog database for weekly reviews.
"""

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
DATABASE_URL = os.environ.get("MINDSETLOG_DB_URL", "")
MINDSETLOG_USER_EMAIL = os.environ.get("MINDSETLOG_EMAIL", "")


def _connect_db():
    """Connect to MindsetLog PostgreSQL database."""
    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2 not installed", file=sys.stderr)
        return None

    try:
        if DATABASE_URL:
            return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"Database connection failed: {e}", file=sys.stderr)
        return None


def get_week_health_stats(start_date: datetime, end_date: datetime) -> dict:
    """
    Get health stats for a week from MindsetLog database.

    Returns dict with oura and cycling stats.
    """
    conn = _connect_db()
    if not conn:
        return {"oura": {}, "cycling": {}}

    try:
        cursor = conn.cursor()

        # Get user ID
        cursor.execute("SELECT id FROM users WHERE email = %s", (MINDSETLOG_USER_EMAIL,))
        user_row = cursor.fetchone()
        if not user_row:
            return {"oura": {}, "cycling": {}}

        user_id = user_row[0]

        # Get Oura stats for the week
        oura_query = """
            SELECT
                AVG(readiness_score) as avg_readiness,
                AVG(sleep_score) as avg_sleep_score,
                AVG(activity_score) as avg_activity,
                AVG(average_hrv) as avg_hrv,
                AVG(resting_heart_rate) as avg_rhr,
                SUM(steps) as total_steps,
                AVG(total_sleep_duration) as avg_sleep_duration,
                AVG(deep_sleep_duration) as avg_deep_sleep,
                AVG(rem_sleep_duration) as avg_rem_sleep
            FROM oura_scores
            WHERE user_id = %s
              AND date >= %s
              AND date <= %s
        """

        cursor.execute(oura_query, (user_id, start_date, end_date))
        oura_row = cursor.fetchone()

        oura_stats = {}
        if oura_row and oura_row[0]:  # Has data
            oura_stats = {
                "readiness": round(oura_row[0], 1) if oura_row[0] else None,
                "sleep_score": round(oura_row[1], 1) if oura_row[1] else None,
                "activity": round(oura_row[2], 1) if oura_row[2] else None,
                "hrv": round(oura_row[3], 1) if oura_row[3] else None,
                "rhr": round(oura_row[4], 1) if oura_row[4] else None,
                "steps": int(oura_row[5]) if oura_row[5] else 0,
                "sleep_hrs": round(oura_row[6] / 3600, 1) if oura_row[6] else None,  # seconds to hours
                "deep_sleep_hrs": round(oura_row[7] / 3600, 1) if oura_row[7] else None,
                "rem_sleep_hrs": round(oura_row[8] / 3600, 1) if oura_row[8] else None,
            }

        # Get cycling stats for the week
        cycling_query = """
            SELECT
                COUNT(*) as ride_count,
                SUM(distance) as total_miles,
                AVG(distance) as avg_miles,
                MAX(distance) as longest_ride,
                SUM(calories_burned) as total_calories
            FROM cycling_workouts
            WHERE user_id = %s
              AND date >= %s
              AND date <= %s
        """

        cursor.execute(cycling_query, (user_id, start_date, end_date))
        cycling_row = cursor.fetchone()

        cycling_stats = {}
        if cycling_row and cycling_row[0]:  # Has rides
            cycling_stats = {
                "rides": int(cycling_row[0]),
                "total_miles": round(float(cycling_row[1]), 1) if cycling_row[1] else 0,
                "avg_miles": round(float(cycling_row[2]), 1) if cycling_row[2] else 0,
                "longest_ride": round(float(cycling_row[3]), 1) if cycling_row[3] else 0,
                "calories": int(cycling_row[4]) if cycling_row[4] else 0,
            }

        cursor.close()
        conn.close()

        return {
            "oura": oura_stats,
            "cycling": cycling_stats
        }

    except Exception as e:
        print(f"Error fetching health stats: {e}", file=sys.stderr)
        if conn:
            conn.close()
        return {"oura": {}, "cycling": {}}


def format_health_summary(stats: dict) -> str:
    """Format health stats for weekly review."""
    lines = []

    oura = stats.get("oura", {})
    cycling = stats.get("cycling", {})

    if oura:
        lines.append("*Health (Oura):*")
        if oura.get("readiness"):
            lines.append(f"• Readiness: {oura['readiness']}/100")
        if oura.get("sleep_score"):
            sleep_hrs = oura.get('sleep_hrs')
            sleep_str = f" ({sleep_hrs}hrs avg)" if sleep_hrs else ""
            lines.append(f"• Sleep: {oura['sleep_score']}/100{sleep_str}")
        if oura.get("hrv"):
            lines.append(f"• HRV: {oura['hrv']}ms avg")
        if oura.get("rhr"):
            lines.append(f"• Resting HR: {oura['rhr']} bpm")
        if oura.get("steps"):
            lines.append(f"• Steps: {oura['steps']:,}")
        lines.append("")

    if cycling and cycling.get("rides", 0) > 0:
        lines.append("*Cycling:*")
        lines.append(f"• {cycling['rides']} rides, {cycling['total_miles']} mi total")
        lines.append(f"• Longest: {cycling['longest_ride']} mi")
        lines.append("")

    return "\n".join(lines)


def main():
    """Test with current week."""
    now = datetime.now(TZ)
    mon = now - timedelta(days=now.weekday())
    sun = mon + timedelta(days=6)

    stats = get_week_health_stats(mon, sun)
    summary = format_health_summary(stats)
    print(summary)


if __name__ == "__main__":
    main()
