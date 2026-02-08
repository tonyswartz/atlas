#!/usr/bin/env python3
"""
Wellness Coach - Autonomous Health & Fitness Advisor

Provides proactive, context-aware recommendations based on Oura, cycling, and strength data.
Runs daily to surface insights, celebrate achievements, and guide recovery/training.

Features:
- Recovery-aware scheduling (readiness-based recommendations)
- Performance celebration (PRs, streaks, milestones)
- Pattern intelligence (correlations between metrics)
- Adaptive goal tracking (weekly/monthly progress)
- Contextual workout suggestions
- Sleep optimization insights
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
STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "wellness_coach_state.json"


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


def _load_state() -> dict:
    """Load previous state (last celebrations, etc)."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load state: {e}", file=sys.stderr)
    return {
        "last_pr_celebration": {},
        "last_streak_length": 0,
        "monthly_miles_last_alert": None
    }


def _save_state(state: dict):
    """Save state for next run."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save state: {e}", file=sys.stderr)


def get_todays_recommendation(conn, user_id: int, today: datetime.date) -> str | None:
    """
    Recovery-aware recommendation for today based on yesterday's metrics.
    Note: Oura data may lag, so we use yesterday's readiness/sleep.
    """
    cursor = conn.cursor()
    yesterday = today - timedelta(days=1)

    # Get yesterday's readiness and sleep
    cursor.execute("""
        SELECT readiness_score, sleep_score, total_sleep_duration, average_hrv
        FROM oura_scores
        WHERE user_id = %s AND date = %s
    """, (user_id, yesterday))

    oura_row = cursor.fetchone()
    if not oura_row:
        cursor.close()
        return None

    readiness, sleep_score, sleep_duration, hrv = oura_row
    sleep_hrs = round(sleep_duration / 3600, 1) if sleep_duration else 0

    # Get last 7 days of workout intensity (cycling + strength)
    cursor.execute("""
        SELECT date FROM cycling_workouts
        WHERE user_id = %s AND date >= %s
        UNION
        SELECT date FROM strength_workouts
        WHERE user_id = %s AND date >= %s
        ORDER BY date DESC
    """, (user_id, today - timedelta(days=7), user_id, today - timedelta(days=7)))

    recent_workouts = [row[0].date() if isinstance(row[0], datetime) else row[0] for row in cursor.fetchall()]
    workouts_last_3_days = len([d for d in recent_workouts if d >= today - timedelta(days=3)])

    # Check when last strength workout was
    cursor.execute("""
        SELECT MAX(date) FROM strength_workouts
        WHERE user_id = %s AND date < %s
    """, (user_id, today))

    last_strength = cursor.fetchone()[0]
    days_since_strength = (today - last_strength).days if last_strength else 999

    cursor.close()

    # Generate recommendation
    if not readiness or not sleep_score:
        return None

    # High readiness, good sleep, no recent strength → strength day
    if readiness >= 75 and sleep_hrs >= 7 and days_since_strength >= 3:
        return f"💪 *Ready for Strength*\nReadiness {int(readiness)} (yesterday), {sleep_hrs}hrs sleep → Good day for that workout ({days_since_strength} days since last)"

    # Low readiness or poor sleep → recovery
    elif readiness < 60 or (sleep_hrs > 0 and sleep_hrs < 6.5):
        if readiness < 60:
            status = f"Readiness {int(readiness)}"
        elif sleep_hrs < 6.5:
            status = f"{sleep_hrs}hrs sleep"
        else:
            status = f"Readiness {int(readiness)}"
        return f"🧘 *Recovery Day*\n{status} (yesterday) → Easy ride or rest recommended"

    # 3+ hard workouts in 3 days → recovery nudge
    elif workouts_last_3_days >= 3:
        return f"⚡ *Active Recovery*\n{workouts_last_3_days} workouts in 3 days → Light activity or rest today"

    # Good readiness, ready to train
    elif readiness >= 70:
        return f"✅ *Good to Train*\nReadiness {int(readiness)} (yesterday) → Normal workout intensity"

    return None


def check_achievements(conn, user_id: int, today: datetime.date, state: dict) -> list[str]:
    """Check for PRs, streaks, and milestones worth celebrating."""
    cursor = conn.cursor()
    achievements = []

    # --- Cycling PRs (last 7 days) ---
    cursor.execute("""
        SELECT date, distance, duration
        FROM cycling_workouts
        WHERE user_id = %s
          AND date >= %s
        ORDER BY date DESC
    """, (user_id, today - timedelta(days=7)))

    recent_rides = cursor.fetchall()

    if recent_rides:
        # Check for distance PR
        latest_date, latest_distance, latest_duration = recent_rides[0]
        # Ensure date is a date object, not datetime
        if isinstance(latest_date, datetime):
            latest_date = latest_date.date()

        # Get previous best
        cursor.execute("""
            SELECT MAX(distance) as best_distance
            FROM cycling_workouts
            WHERE user_id = %s AND date < %s
        """, (user_id, latest_date))

        prev_best = cursor.fetchone()[0]

        # New PR if current ride > previous best AND we haven't celebrated this one yet
        if prev_best and latest_distance > prev_best:
            last_pr_date = state["last_pr_celebration"].get("cycling_distance")
            if last_pr_date != str(latest_date):
                gain_pct = round((latest_distance - prev_best) / prev_best * 100)
                achievements.append(f"🚴 *New Distance PR!*\n{latest_distance}mi (was {prev_best}mi, +{gain_pct}%)")
                state["last_pr_celebration"]["cycling_distance"] = str(latest_date)

    # --- Workout Streak ---
    # Count consecutive days with any workout (cycling or strength)
    cursor.execute("""
        SELECT DISTINCT date FROM (
            SELECT date FROM cycling_workouts WHERE user_id = %s
            UNION
            SELECT date FROM strength_workouts WHERE user_id = %s
        ) workouts
        WHERE date <= %s
        ORDER BY date DESC
    """, (user_id, user_id, today - timedelta(days=1)))  # Use yesterday since today might not have data yet

    workout_dates = [row[0].date() if isinstance(row[0], datetime) else row[0] for row in cursor.fetchall()]

    # Calculate current streak
    streak = 0
    check_date = today - timedelta(days=1)
    for workout_date in workout_dates:
        if workout_date == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif workout_date < check_date:
            break

    # Celebrate streaks at 3, 5, 7, 10, 14, 21, 30 days
    milestones = [3, 5, 7, 10, 14, 21, 30]
    if streak in milestones and streak > state.get("last_streak_length", 0):
        achievements.append(f"🔥 *{streak}-Day Streak!*\nConsecutive workout days")
        state["last_streak_length"] = streak

    # --- Monthly Mileage Milestones ---
    month_start = today.replace(day=1)
    cursor.execute("""
        SELECT SUM(distance) as total_miles, COUNT(*) as ride_count
        FROM cycling_workouts
        WHERE user_id = %s
          AND date >= %s
          AND date < %s
    """, (user_id, month_start, today))

    month_row = cursor.fetchone()
    if month_row and month_row[0]:
        monthly_miles = round(month_row[0], 1)
        ride_count = month_row[1]

        # Celebrate 100, 150, 200, 250, 300 mile months
        milestones = [100, 150, 200, 250, 300]
        for milestone in milestones:
            if monthly_miles >= milestone:
                last_alert = state.get("monthly_miles_last_alert", {}).get(str(today.month))
                if last_alert != milestone:
                    achievements.append(f"🎯 *{milestone}mi Month!*\n{monthly_miles}mi total ({ride_count} rides this month)")
                    if "monthly_miles_last_alert" not in state:
                        state["monthly_miles_last_alert"] = {}
                    state["monthly_miles_last_alert"][str(today.month)] = milestone
                    break  # Only celebrate highest milestone

    cursor.close()
    return achievements


def detect_long_term_trends(conn, user_id: int, today: datetime.date) -> list[str]:
    """Detect longer-term trends (weeks/months/quarters) worth flagging."""
    cursor = conn.cursor()
    trends = []

    # Compare this week vs 3 weeks ago
    this_week_start = today - timedelta(days=7)
    three_weeks_ago = today - timedelta(days=28)

    # Steps trend
    cursor.execute("""
        SELECT
            AVG(CASE WHEN date >= %s THEN steps END) as recent_steps,
            AVG(CASE WHEN date >= %s AND date < %s THEN steps END) as old_steps
        FROM oura_scores
        WHERE user_id = %s
          AND date >= %s
    """, (this_week_start, three_weeks_ago, three_weeks_ago + timedelta(days=7), user_id, three_weeks_ago))

    steps_row = cursor.fetchone()
    if steps_row and steps_row[0] and steps_row[1]:
        recent_avg = round(steps_row[0])
        old_avg = round(steps_row[1])
        diff = recent_avg - old_avg
        pct_change = round(diff / old_avg * 100)

        if abs(pct_change) >= 20:  # 20%+ change
            if pct_change < 0:
                trends.append(f"📉 *Steps Declining*\n{recent_avg:,}/day this week (down {abs(pct_change)}% from {old_avg:,}/day 3 weeks ago)")
            else:
                trends.append(f"📈 *Steps Rising*\n{recent_avg:,}/day this week (up {pct_change}% from {old_avg:,}/day 3 weeks ago)")

    # HRV trend (month-over-month)
    this_month_start = today - timedelta(days=30)
    last_month_start = today - timedelta(days=60)
    last_month_end = this_month_start

    cursor.execute("""
        SELECT
            AVG(CASE WHEN date >= %s THEN average_hrv END) as recent_hrv,
            AVG(CASE WHEN date >= %s AND date < %s THEN average_hrv END) as old_hrv
        FROM oura_scores
        WHERE user_id = %s
          AND date >= %s
    """, (this_month_start, last_month_start, last_month_end, user_id, last_month_start))

    hrv_row = cursor.fetchone()
    if hrv_row and hrv_row[0] and hrv_row[1]:
        recent_hrv = round(hrv_row[0], 1)
        old_hrv = round(hrv_row[1], 1)
        diff = recent_hrv - old_hrv
        pct_change = round(diff / old_hrv * 100)

        if abs(diff) >= 3:  # 3ms+ change is significant
            if diff > 0:
                trends.append(f"📈 *HRV Improving*\n{recent_hrv}ms avg last 30 days (up {pct_change}% from {old_hrv}ms previous month)")
            else:
                trends.append(f"📉 *HRV Declining*\n{recent_hrv}ms avg last 30 days (down {abs(pct_change)}% from {old_hrv}ms previous month)")

    # Resting HR trend
    cursor.execute("""
        SELECT
            AVG(CASE WHEN date >= %s THEN resting_heart_rate END) as recent_rhr,
            AVG(CASE WHEN date >= %s AND date < %s THEN resting_heart_rate END) as old_rhr
        FROM oura_scores
        WHERE user_id = %s
          AND date >= %s
    """, (this_month_start, last_month_start, last_month_end, user_id, last_month_start))

    rhr_row = cursor.fetchone()
    if rhr_row and rhr_row[0] and rhr_row[1]:
        recent_rhr = round(rhr_row[0], 1)
        old_rhr = round(rhr_row[1], 1)
        diff = recent_rhr - old_rhr

        if abs(diff) >= 3:  # 3bpm+ change
            if diff < 0:  # Lower is better
                trends.append(f"📈 *Resting HR Improving*\n{recent_rhr} bpm avg (down {abs(round(diff))} from {old_rhr} bpm last month)")
            else:
                trends.append(f"📉 *Resting HR Elevated*\n{recent_rhr} bpm avg (up {round(diff)} from {old_rhr} bpm last month)")

    # Workout frequency trend
    cursor.execute("""
        SELECT
            COUNT(DISTINCT CASE WHEN date >= %s THEN date END) as recent_workouts,
            COUNT(DISTINCT CASE WHEN date >= %s AND date < %s THEN date END) as old_workouts
        FROM (
            SELECT date FROM cycling_workouts WHERE user_id = %s AND date >= %s
            UNION
            SELECT date FROM strength_workouts WHERE user_id = %s AND date >= %s
        ) workouts
    """, (this_week_start, three_weeks_ago, three_weeks_ago + timedelta(days=7),
          user_id, three_weeks_ago, user_id, three_weeks_ago))

    workout_row = cursor.fetchone()
    if workout_row and workout_row[0] is not None and workout_row[1]:
        recent_days = workout_row[0]
        old_days = workout_row[1]
        diff = recent_days - old_days

        if abs(diff) >= 2:  # 2+ day change per week
            if diff < 0:
                trends.append(f"⚠️ *Training Frequency Down*\n{recent_days} workout days this week (was {old_days}/week 3 weeks ago)")
            else:
                trends.append(f"💪 *Training Ramping Up*\n{recent_days} workout days this week (was {old_days}/week 3 weeks ago)")

    cursor.close()
    return trends


def detect_patterns(conn, user_id: int, today: datetime.date) -> list[str]:
    """Detect correlations between sleep, recovery, and performance."""
    cursor = conn.cursor()
    insights = []

    # Need at least 14 days of data for meaningful patterns
    start_date = today - timedelta(days=30)

    # Get Oura data with workout flags
    cursor.execute("""
        SELECT
            o.date,
            o.readiness_score,
            o.sleep_score,
            o.total_sleep_duration,
            o.average_hrv,
            o.resting_heart_rate,
            je.alcohol_consumed,
            CASE WHEN c.date IS NOT NULL THEN 1 ELSE 0 END as did_cycle,
            CASE WHEN s.date IS NOT NULL THEN 1 ELSE 0 END as did_strength
        FROM oura_scores o
        LEFT JOIN journal_entries je ON o.user_id = je.user_id AND o.date = je.date
        LEFT JOIN cycling_workouts c ON o.user_id = c.user_id AND o.date = c.date
        LEFT JOIN strength_workouts s ON o.user_id = s.user_id AND o.date = s.date
        WHERE o.user_id = %s
          AND o.date >= %s
          AND o.date < %s
        ORDER BY o.date DESC
    """, (user_id, start_date, today))

    rows = cursor.fetchall()

    if len(rows) < 14:
        cursor.close()
        return insights

    # Analyze sleep duration vs readiness
    sleep_good = []  # readiness when sleep >= 7.5hrs
    sleep_poor = []  # readiness when sleep < 6.5hrs

    alcohol_nights = []  # sleep duration on alcohol nights
    sober_nights = []    # sleep duration on sober nights

    strength_days = []   # readiness day after strength workout
    rest_days = []       # readiness on rest days

    for row in rows:
        date, readiness, sleep_score, sleep_dur, hrv, rhr, alcohol, cycled, strength = row

        if sleep_dur and readiness:
            sleep_hrs = sleep_dur / 3600

            if sleep_hrs >= 7.5:
                sleep_good.append(readiness)
            elif sleep_hrs < 6.5:
                sleep_poor.append(readiness)

        if sleep_dur is not None and alcohol is not None:
            sleep_hrs = sleep_dur / 3600
            if alcohol:
                alcohol_nights.append(sleep_hrs)
            else:
                sober_nights.append(sleep_hrs)

    # Check for next-day readiness after strength workouts
    for i in range(len(rows) - 1):
        curr = rows[i]
        prev = rows[i + 1]

        if curr[1] is not None:  # has readiness
            if prev[8]:  # previous day had strength workout
                strength_days.append(curr[1])
            elif not prev[7] and not prev[8]:  # previous day was rest
                rest_days.append(curr[1])

    # Generate insights if patterns are clear (need 5+ data points)

    # Sleep → Readiness correlation
    if len(sleep_good) >= 5 and len(sleep_poor) >= 5:
        avg_good = sum(sleep_good) / len(sleep_good)
        avg_poor = sum(sleep_poor) / len(sleep_poor)
        diff = avg_good - avg_poor

        if diff >= 10:
            insights.append(f"💡 *Sleep → Readiness*\n7.5+ hrs sleep = {int(avg_good)} readiness avg (vs {int(avg_poor)} on <6.5hrs)")

    # Alcohol → Sleep impact
    if len(alcohol_nights) >= 3 and len(sober_nights) >= 10:
        avg_alcohol = sum(alcohol_nights) / len(alcohol_nights)
        avg_sober = sum(sober_nights) / len(sober_nights)
        diff_hrs = avg_sober - avg_alcohol

        if diff_hrs >= 0.5:
            insights.append(f"🍷 *Alcohol Impact*\n{round(avg_alcohol, 1)}hrs avg sleep on drinking nights (vs {round(avg_sober, 1)}hrs sober)")

    # Strength → Recovery boost
    if len(strength_days) >= 5 and len(rest_days) >= 5:
        avg_strength = sum(strength_days) / len(strength_days)
        avg_rest = sum(rest_days) / len(rest_days)
        diff = avg_strength - avg_rest

        if diff >= 5:
            insights.append(f"💪 *Strength Boost*\nReadiness day-after strength: {int(avg_strength)} avg (vs {int(avg_rest)} after rest)")

    cursor.close()
    return insights


def check_goal_progress(conn, user_id: int, today: datetime.date) -> list[str]:
    """Track weekly and monthly fitness goals."""
    cursor = conn.cursor()
    progress = []

    # --- Weekly Goals ---
    week_start = today - timedelta(days=today.weekday())

    # Cycling goal: 50mi/week
    cursor.execute("""
        SELECT SUM(distance) as total_miles, COUNT(*) as rides
        FROM cycling_workouts
        WHERE user_id = %s
          AND date >= %s
          AND date < %s
    """, (user_id, week_start, today))

    week_row = cursor.fetchone()
    if week_row and week_row[0]:
        weekly_miles = round(week_row[0], 1)
        rides = week_row[1]
        goal = 50

        days_into_week = (today - week_start).days + 1
        days_left = 7 - days_into_week

        if weekly_miles >= goal:
            progress.append(f"🎯 *Weekly Goal Met!*\n{weekly_miles}mi cycling (goal: {goal}mi)")
        elif days_into_week >= 3:  # Only show progress mid-week
            pace = weekly_miles / days_into_week * 7
            if pace >= goal * 0.9:  # On track
                progress.append(f"📊 *On Track*\n{weekly_miles}/{goal}mi ({rides} rides, {days_left} days left)")
            else:  # Behind pace
                needed = goal - weekly_miles
                progress.append(f"⚠️ *Behind Pace*\n{weekly_miles}/{goal}mi → {round(needed, 1)}mi needed in {days_left} days")

    # Strength goal: 2-3x/week
    cursor.execute("""
        SELECT COUNT(*) FROM strength_workouts
        WHERE user_id = %s
          AND date >= %s
          AND date < %s
    """, (user_id, week_start, today))

    strength_count = cursor.fetchone()[0]
    if strength_count >= 2:
        progress.append(f"💪 *Strength: {strength_count}/3 this week*")
    elif (today - week_start).days >= 3 and strength_count == 0:
        progress.append(f"⚠️ *No Strength Yet*\n0 workouts this week (goal: 2-3)")

    cursor.close()
    return progress


def get_workout_suggestion(conn, user_id: int, today: datetime.date) -> str | None:
    """Contextual workout suggestion based on recovery state and recent pattern."""
    cursor = conn.cursor()
    yesterday = today - timedelta(days=1)

    # Get yesterday's readiness
    cursor.execute("""
        SELECT readiness_score
        FROM oura_scores
        WHERE user_id = %s AND date = %s
    """, (user_id, yesterday))

    readiness_row = cursor.fetchone()
    if not readiness_row or not readiness_row[0]:
        cursor.close()
        return None

    readiness = readiness_row[0]

    # Get recent workout pattern (last 7 days)
    cursor.execute("""
        SELECT date, 'cycling' as type FROM cycling_workouts
        WHERE user_id = %s AND date >= %s
        UNION
        SELECT date, 'strength' as type FROM strength_workouts
        WHERE user_id = %s AND date >= %s
        ORDER BY date DESC
    """, (user_id, today - timedelta(days=7), user_id, today - timedelta(days=7)))

    recent = cursor.fetchall()

    # What happened yesterday?
    # Ensure dates are date objects for comparison
    yesterday_workouts = [r[1] for r in recent if (r[0].date() if isinstance(r[0], datetime) else r[0]) == yesterday]

    # Get weather (if available from daily_brief)
    # For now, skip weather integration

    cursor.close()

    # Generate suggestion
    if readiness >= 80:
        if 'cycling' in yesterday_workouts:
            return "💡 *Suggestion*\nHigh readiness + rode yesterday → Active recovery or strength"
        else:
            return "💡 *Suggestion*\nHigh readiness → Good day for a longer/harder ride"

    elif readiness < 65:
        return "💡 *Suggestion*\nLow readiness → 20-30min easy spin or rest"

    return None


def main():
    """Run wellness coach and send insights if any."""
    print(f"[{datetime.now()}] Running wellness coach...")

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

        today = datetime.now(TZ).date()
        state = _load_state()

        # Gather all insights
        sections = []

        # 1. Today's recommendation (recovery-aware)
        recommendation = get_todays_recommendation(conn, user_id, today)
        if recommendation:
            sections.append(recommendation)

        # 2. Achievements (PRs, streaks, milestones)
        achievements = check_achievements(conn, user_id, today, state)
        if achievements:
            sections.extend(achievements)

        # 3. Goal progress (only if notable)
        progress = check_goal_progress(conn, user_id, today)
        if progress:
            sections.extend(progress)

        # 4. Workout suggestion (only if we have a recommendation)
        suggestion = get_workout_suggestion(conn, user_id, today)
        if suggestion and not recommendation:  # Don't duplicate if we already have recommendation
            sections.append(suggestion)

        # 5. Long-term trends (Monday & Thursday)
        if today.weekday() in [0, 3]:  # Monday or Thursday
            trends = detect_long_term_trends(conn, user_id, today)
            if trends:
                # Limit to 2 most important trends per day
                sections.extend(trends[:2])

        # 6. Patterns (only show once per week - Friday)
        if today.weekday() == 4:  # Friday
            patterns = detect_patterns(conn, user_id, today)
            if patterns:
                sections.append("\n".join(patterns))

        conn.close()

        # Save state
        _save_state(state)

        # Send if we have anything
        if sections:
            message = "🏋️ *Wellness Coach*\n\n" + "\n\n".join(sections)
            print(message)
            _send_telegram(message)
            print(f"✓ Sent {len(sections)} insight(s)")
        else:
            print("No insights to share today")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
