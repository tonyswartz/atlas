#!/usr/bin/env python3
"""
Monthly Fitness Review

Comprehensive month-over-month and quarterly trend analysis.
Runs on the 1st of each month at 8am via cron.

Tracks:
- Baseline health metrics (HRV, RHR, readiness, sleep)
- Training volume and consistency
- Performance trends
- Goal achievement
- 3-month trajectory analysis
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from calendar import monthrange

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
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
BRIEFS_DIR = OBSIDIAN_VAULT / "Research" / "Briefs"


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
    """Send message to Telegram."""
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


def get_month_metrics(conn, user_id: int, year: int, month: int) -> dict:
    """Get all metrics for a specific month."""
    cursor = conn.cursor()

    # Get month boundaries
    first_day = datetime(year, month, 1, tzinfo=TZ).date()
    last_day = datetime(year, month, monthrange(year, month)[1], tzinfo=TZ).date()

    metrics = {}

    # Oura baselines
    cursor.execute("""
        SELECT
            AVG(readiness_score) as avg_readiness,
            AVG(sleep_score) as avg_sleep_score,
            AVG(average_hrv) as avg_hrv,
            AVG(resting_heart_rate) as avg_rhr,
            AVG(total_sleep_duration) as avg_sleep_duration,
            SUM(steps) as total_steps,
            COUNT(*) as data_days
        FROM oura_scores
        WHERE user_id = %s
          AND date >= %s
          AND date <= %s
    """, (user_id, first_day, last_day))

    oura_row = cursor.fetchone()
    if oura_row and oura_row[6]:  # Has data
        metrics['readiness'] = round(oura_row[0], 1) if oura_row[0] else None
        metrics['sleep_score'] = round(oura_row[1], 1) if oura_row[1] else None
        metrics['hrv'] = round(oura_row[2], 1) if oura_row[2] else None
        metrics['rhr'] = round(oura_row[3], 1) if oura_row[3] else None
        metrics['sleep_hrs'] = round(oura_row[4] / 3600, 1) if oura_row[4] else None
        metrics['total_steps'] = int(oura_row[5]) if oura_row[5] else 0
        metrics['data_days'] = oura_row[6]

    # Cycling stats
    cursor.execute("""
        SELECT
            COUNT(*) as rides,
            SUM(distance) as total_miles,
            AVG(distance) as avg_miles,
            MAX(distance) as longest_ride
        FROM cycling_workouts
        WHERE user_id = %s
          AND date >= %s
          AND date <= %s
    """, (user_id, first_day, last_day))

    cycling_row = cursor.fetchone()
    if cycling_row and cycling_row[0]:
        metrics['rides'] = int(cycling_row[0])
        metrics['cycling_miles'] = round(float(cycling_row[1]), 1) if cycling_row[1] else 0
        metrics['avg_ride_distance'] = round(float(cycling_row[2]), 1) if cycling_row[2] else 0
        metrics['longest_ride'] = round(float(cycling_row[3]), 1) if cycling_row[3] else 0

    # Strength workouts
    cursor.execute("""
        SELECT COUNT(*) FROM strength_workouts
        WHERE user_id = %s
          AND date >= %s
          AND date <= %s
    """, (user_id, first_day, last_day))

    metrics['strength_workouts'] = cursor.fetchone()[0]

    # Workout days (any activity)
    cursor.execute("""
        SELECT COUNT(DISTINCT date) FROM (
            SELECT date FROM cycling_workouts WHERE user_id = %s AND date >= %s AND date <= %s
            UNION
            SELECT date FROM strength_workouts WHERE user_id = %s AND date >= %s AND date <= %s
        ) workouts
    """, (user_id, first_day, last_day, user_id, first_day, last_day))

    metrics['workout_days'] = cursor.fetchone()[0]

    # Sleep quality (nights with <6hrs)
    cursor.execute("""
        SELECT COUNT(*) FROM oura_scores
        WHERE user_id = %s
          AND date >= %s
          AND date <= %s
          AND total_sleep_duration < 21600
    """, (user_id, first_day, last_day))

    metrics['short_sleep_nights'] = cursor.fetchone()[0]

    cursor.close()
    return metrics


def format_review(this_month: dict, last_month: dict, three_months_ago: dict,
                  month_name: str, last_month_name: str) -> str:
    """Format the monthly review message."""
    lines = []
    lines.append(f"📊 *Monthly Fitness Review — {month_name}*\n")

    # --- Baseline Health Metrics ---
    if this_month.get('hrv') and last_month.get('hrv'):
        lines.append("*📈 Health Baselines*")

        # HRV
        hrv_diff = this_month['hrv'] - last_month['hrv']
        hrv_pct = round(hrv_diff / last_month['hrv'] * 100)
        hrv_arrow = "↑" if hrv_diff > 0 else "↓"
        lines.append(f"• HRV: {this_month['hrv']}ms ({hrv_arrow}{abs(hrv_pct)}% vs {last_month_name})")

        # 3-month trend
        if three_months_ago.get('hrv'):
            trend_diff = this_month['hrv'] - three_months_ago['hrv']
            if abs(trend_diff) >= 2:
                trend_arrow = "📈" if trend_diff > 0 else "📉"
                lines.append(f"  {trend_arrow} 3-month trend: {trend_diff:+.1f}ms")

        # RHR
        if this_month.get('rhr') and last_month.get('rhr'):
            rhr_diff = this_month['rhr'] - last_month['rhr']
            rhr_arrow = "↓" if rhr_diff < 0 else "↑"  # Lower is better
            lines.append(f"• Resting HR: {this_month['rhr']} bpm ({rhr_arrow}{abs(round(rhr_diff))} vs {last_month_name})")

        # Readiness
        if this_month.get('readiness') and last_month.get('readiness'):
            ready_diff = this_month['readiness'] - last_month['readiness']
            ready_arrow = "↑" if ready_diff > 0 else "↓"
            lines.append(f"• Readiness: {this_month['readiness']} avg ({ready_arrow}{abs(round(ready_diff))} vs {last_month_name})")

        # Sleep
        if this_month.get('sleep_hrs') and last_month.get('sleep_hrs'):
            sleep_diff = this_month['sleep_hrs'] - last_month['sleep_hrs']
            sleep_arrow = "↑" if sleep_diff > 0 else "↓"
            lines.append(f"• Sleep: {this_month['sleep_hrs']}hrs avg ({sleep_arrow}{abs(round(sleep_diff, 1))}hrs vs {last_month_name})")

            # Short sleep nights
            short_this = this_month.get('short_sleep_nights', 0)
            short_last = last_month.get('short_sleep_nights', 0)
            if short_this or short_last:
                lines.append(f"  • <6hrs nights: {short_this} (was {short_last})")

        lines.append("")

    # --- Training Volume ---
    if this_month.get('rides'):
        lines.append("*🚴 Training Volume*")

        # Cycling
        this_miles = this_month.get('cycling_miles', 0)
        last_miles = last_month.get('cycling_miles', 0)
        miles_diff = this_miles - last_miles
        miles_pct = round(miles_diff / last_miles * 100) if last_miles else 0
        miles_arrow = "↑" if miles_diff > 0 else "↓"

        this_rides = this_month.get('rides', 0)
        last_rides = last_month.get('rides', 0)

        lines.append(f"• Cycling: {this_miles}mi ({this_rides} rides)")
        lines.append(f"  {miles_arrow} {abs(miles_pct)}% vs {last_month_name} ({last_miles}mi, {last_rides} rides)")

        # Avg ride distance
        this_avg = this_month.get('avg_ride_distance', 0)
        last_avg = last_month.get('avg_ride_distance', 0)
        if this_avg and last_avg:
            avg_diff = this_avg - last_avg
            if abs(avg_diff) >= 0.5:
                avg_arrow = "↑" if avg_diff > 0 else "↓"
                lines.append(f"  • Avg ride: {this_avg}mi ({avg_arrow}{abs(round(avg_diff, 1))}mi)")

        # Longest ride
        longest = this_month.get('longest_ride', 0)
        if longest:
            lines.append(f"  • Longest: {longest}mi")

        # 3-month cycling trend
        if three_months_ago.get('cycling_miles'):
            three_miles = three_months_ago['cycling_miles']
            trend_diff = this_miles - three_miles
            if abs(trend_diff) >= 10:
                trend_pct = round(trend_diff / three_miles * 100)
                trend_arrow = "📈" if trend_diff > 0 else "📉"
                lines.append(f"  {trend_arrow} 3-month: {trend_pct:+d}% ({three_miles}mi → {this_miles}mi)")

        lines.append("")

    # --- Strength Training ---
    if this_month.get('strength_workouts') or last_month.get('strength_workouts'):
        this_strength = this_month.get('strength_workouts', 0)
        last_strength = last_month.get('strength_workouts', 0)

        lines.append(f"*💪 Strength*")
        lines.append(f"• {this_strength} workouts (vs {last_strength} in {last_month_name})")

        strength_diff = this_strength - last_strength
        if strength_diff != 0:
            strength_pct = round(strength_diff / last_strength * 100) if last_strength else 100
            strength_arrow = "↑" if strength_diff > 0 else "↓"
            lines.append(f"  {strength_arrow} {abs(strength_pct)}% vs last month")

        lines.append("")

    # --- Consistency ---
    if this_month.get('workout_days'):
        lines.append("*📅 Consistency*")

        this_days = this_month.get('workout_days', 0)
        last_days = last_month.get('workout_days', 0)

        lines.append(f"• Workout days: {this_days} (vs {last_days} in {last_month_name})")

        # 3-month consistency trend
        if three_months_ago.get('workout_days'):
            three_days = three_months_ago['workout_days']
            if this_days >= three_days + 3:
                lines.append(f"  📈 Building consistency: {three_days} → {this_days} workout days")
            elif this_days <= three_days - 3:
                lines.append(f"  📉 Consistency down: {three_days} → {this_days} workout days")

        lines.append("")

    # --- Activity (Steps) ---
    if this_month.get('total_steps') and last_month.get('total_steps'):
        this_steps = this_month['total_steps']
        last_steps = last_month['total_steps']
        steps_diff = this_steps - last_steps
        steps_pct = round(steps_diff / last_steps * 100)

        # Daily average
        this_days_count = this_month.get('data_days', 30)
        last_days_count = last_month.get('data_days', 30)
        this_daily_avg = round(this_steps / this_days_count)
        last_daily_avg = round(last_steps / last_days_count)

        lines.append("*👟 Activity*")
        lines.append(f"• Steps: {this_steps:,} total ({this_daily_avg:,}/day avg)")

        daily_diff = this_daily_avg - last_daily_avg
        if abs(daily_diff) >= 500:
            daily_arrow = "↑" if daily_diff > 0 else "↓"
            lines.append(f"  {daily_arrow} {abs(daily_diff):,}/day vs {last_month_name} ({last_daily_avg:,}/day)")

        lines.append("")

    return "\n".join(lines)


def save_to_obsidian(text: str, month_name: str):
    """Save monthly review to Obsidian."""
    try:
        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(TZ).strftime("%Y-%m")
        out = BRIEFS_DIR / f"monthly-fitness-{date_str}.md"
        out.write_text(f"---\ndate: \"{date_str}\"\ntype: monthly-fitness-review\n---\n\n{text}\n")
        print(f"✓ Saved to {out.name}")
    except Exception as e:
        print(f"Could not save to Obsidian: {e}", file=sys.stderr)


def main():
    """Generate and send monthly fitness review."""
    print(f"[{datetime.now()}] Running monthly fitness review...")

    conn = _connect_db()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        # Get user ID
        cursor.execute("SELECT id FROM users WHERE email = %s", (MINDSETLOG_USER_EMAIL,))
        user_row = cursor.fetchone()
        if not user_row:
            print("User not found")
            return

        user_id = user_row[0]
        cursor.close()

        # Get current date and calculate month boundaries
        today = datetime.now(TZ)

        # This month (just completed)
        if today.day == 1:
            # On the 1st, review the previous month
            last_month_date = today - timedelta(days=1)
            this_year = last_month_date.year
            this_month = last_month_date.month
        else:
            # Testing: review current month so far
            this_year = today.year
            this_month = today.month

        # Last month
        last_month_date = datetime(this_year, this_month, 1, tzinfo=TZ) - timedelta(days=1)
        last_year = last_month_date.year
        last_month = last_month_date.month

        # Three months ago
        three_months_date = datetime(last_year, last_month, 1, tzinfo=TZ) - timedelta(days=1)
        three_months_date = datetime(three_months_date.year, three_months_date.month, 1, tzinfo=TZ) - timedelta(days=1)
        three_year = three_months_date.year
        three_month = three_months_date.month

        # Get metrics
        this_month_metrics = get_month_metrics(conn, user_id, this_year, this_month)
        last_month_metrics = get_month_metrics(conn, user_id, last_year, last_month)
        three_months_metrics = get_month_metrics(conn, user_id, three_year, three_month)

        conn.close()

        # Format month names
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        this_month_name = month_names[this_month - 1]
        last_month_name = month_names[last_month - 1]

        # Generate review
        review = format_review(
            this_month_metrics,
            last_month_metrics,
            three_months_metrics,
            this_month_name,
            last_month_name
        )

        print(review)
        save_to_obsidian(review, this_month_name)
        _send_telegram(review)
        print(f"[{datetime.now()}] Done")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
