#!/usr/bin/env python3
"""
Proactive Health Monitor

Checks daily health metrics from MindsetLog (Oura data, cycling, workouts)
and sends Telegram alerts when anomalies or concerning patterns are detected.
"""

import json
import os
import sys
import urllib.request
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
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_ID", "8241581699")


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


def _send_telegram(text: str) -> bool:
    """Send alert to Telegram."""
    if not TELEGRAM_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }).encode()

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        return False


def check_health_anomalies() -> list[str]:
    """
    Check for health anomalies and return list of alerts.

    Checks:
    - HRV below 30-day average by >15%
    - Resting HR elevated (>10% above 30-day avg)
    - Sleep score declining 3+ nights
    - Readiness score low (<60) for 2+ days
    - No strength training in 7+ days (if usual pattern is 2-3x/week)
    - Sleep duration <6 hours for 2+ nights
    """
    conn = _connect_db()
    if not conn:
        return []

    alerts = []

    try:
        cursor = conn.cursor()

        # Get user ID
        cursor.execute("SELECT id FROM users WHERE email = %s", (MINDSETLOG_USER_EMAIL,))
        user_row = cursor.fetchone()
        if not user_row:
            return []

        user_id = user_row[0]
        now = datetime.now(TZ)
        today = now.date()

        # --- HRV Check ---
        cursor.execute("""
            SELECT
                AVG(average_hrv) as baseline_hrv,
                (SELECT average_hrv FROM oura_scores
                 WHERE user_id = %s AND date >= %s
                 ORDER BY date DESC LIMIT 1) as today_hrv
            FROM oura_scores
            WHERE user_id = %s
              AND date >= %s
              AND date < %s
        """, (user_id, today, user_id, today - timedelta(days=30), today))

        hrv_row = cursor.fetchone()
        if hrv_row and hrv_row[0] and hrv_row[1]:
            baseline, today_hrv = hrv_row
            if today_hrv < baseline * 0.85:  # 15% below baseline
                pct_diff = round((baseline - today_hrv) / baseline * 100)
                alerts.append(f"⚠️ *HRV Alert*: {int(today_hrv)}ms (−{pct_diff}% from 30-day avg of {int(baseline)}ms)")

        # --- Resting Heart Rate Check ---
        cursor.execute("""
            SELECT
                AVG(resting_heart_rate) as baseline_rhr,
                (SELECT resting_heart_rate FROM oura_scores
                 WHERE user_id = %s AND date >= %s
                 ORDER BY date DESC LIMIT 1) as today_rhr
            FROM oura_scores
            WHERE user_id = %s
              AND date >= %s
              AND date < %s
        """, (user_id, today, user_id, today - timedelta(days=30), today))

        rhr_row = cursor.fetchone()
        if rhr_row and rhr_row[0] and rhr_row[1]:
            baseline, today_rhr = rhr_row
            if today_rhr > baseline * 1.10:  # 10% above baseline
                pct_diff = round((today_rhr - baseline) / baseline * 100)
                alerts.append(f"⚠️ *Elevated Resting HR*: {int(today_rhr)} bpm (+{pct_diff}% from 30-day avg of {int(baseline)} bpm)")

        # --- Sleep Score Declining Check (3+ nights) ---
        cursor.execute("""
            SELECT date, sleep_score
            FROM oura_scores
            WHERE user_id = %s
              AND date >= %s
              AND sleep_score IS NOT NULL
            ORDER BY date DESC
            LIMIT 3
        """, (user_id, today - timedelta(days=3)))

        sleep_scores = cursor.fetchall()
        if len(sleep_scores) == 3:
            scores = [row[1] for row in sleep_scores]
            if scores[0] < scores[1] < scores[2]:  # Declining trend
                drop = scores[2] - scores[0]
                alerts.append(f"📉 *Sleep Declining*: {int(scores[0])}/100 (down {int(drop)} points over 3 nights)")

        # --- Low Readiness Check (2+ days) ---
        cursor.execute("""
            SELECT COUNT(*)
            FROM oura_scores
            WHERE user_id = %s
              AND date >= %s
              AND readiness_score < 60
        """, (user_id, today - timedelta(days=2)))

        low_readiness_count = cursor.fetchone()[0]
        if low_readiness_count >= 2:
            alerts.append(f"🔋 *Low Readiness*: Below 60 for {low_readiness_count} days")

        # --- Strength Training Gap Check ---
        cursor.execute("""
            SELECT
                MAX(date) as last_strength,
                COUNT(*) as count_last_30_days
            FROM strength_workouts
            WHERE user_id = %s
              AND date >= %s
        """, (user_id, today - timedelta(days=30)))

        strength_row = cursor.fetchone()
        if strength_row and strength_row[1] and strength_row[1] >= 6:  # If usually 2-3x/week (6+ in 30 days)
            last_strength = strength_row[0]
            if last_strength:
                days_since = (today - last_strength).days
                if days_since >= 7:
                    alerts.append(f"💪 *No Strength Training*: {days_since} days since last workout")

        # --- Short Sleep Check (2+ nights <6hrs) ---
        cursor.execute("""
            SELECT COUNT(*)
            FROM oura_scores
            WHERE user_id = %s
              AND date >= %s
              AND total_sleep_duration < 21600
        """, (user_id, today - timedelta(days=2)))  # 21600 seconds = 6 hours

        short_sleep_count = cursor.fetchone()[0]
        if short_sleep_count >= 2:
            alerts.append(f"😴 *Short Sleep*: Less than 6hrs for {short_sleep_count} nights")

        cursor.close()
        conn.close()

        return alerts

    except Exception as e:
        print(f"Error checking health anomalies: {e}", file=sys.stderr)
        if conn:
            conn.close()
        return []


def main():
    """Run health monitoring and send alerts if needed."""
    print(f"[{datetime.now()}] Running health monitor...")

    alerts = check_health_anomalies()

    if alerts:
        message = "🏥 *Health Alert*\n\n" + "\n\n".join(alerts)
        print(f"Sending {len(alerts)} alert(s) to Telegram")
        print(message)
        _send_telegram(message)
    else:
        print("No health anomalies detected")


if __name__ == "__main__":
    main()
