#!/usr/bin/env python3
"""
Agent Health Monitoring System

Tracks agent execution metrics, performance, and failures.
Enables proactive detection of issues before they cascade.

Usage:
    from agents.health import AgentHealthMonitor

    monitor = AgentHealthMonitor()

    # Record execution
    with monitor.track("telegram", "process_message"):
        # ... do work ...
        pass

    # Check health
    status = monitor.get_health("telegram")
    print(f"Status: {status['status']}, Success rate: {status['success_rate']}")

    # Dashboard
    monitor.show_dashboard()
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional
import time


class AgentHealthMonitor:
    """Track and monitor agent health metrics"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "agent_health.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                task TEXT NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                duration_seconds REAL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                context TEXT
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_time
            ON agent_executions(agent, start_time DESC)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                resolved BOOLEAN DEFAULT FALSE
            )
        """)

        conn.commit()
        conn.close()

    def record_execution(self, agent: str, task: str, duration: float,
                        success: bool, error: Optional[str] = None,
                        context: Optional[dict] = None):
        """
        Record agent execution.

        Args:
            agent: Agent name
            task: Task description
            duration: Execution time in seconds
            success: Whether execution succeeded
            error: Error message if failed
            context: Additional context (dict, stored as JSON)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now()
        start_time = now - timedelta(seconds=duration)

        cursor.execute("""
            INSERT INTO agent_executions
            (agent, task, start_time, end_time, duration_seconds, success, error_message, context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            agent,
            task,
            start_time.isoformat(),
            now.isoformat(),
            duration,
            success,
            error,
            json.dumps(context) if context else None
        ))

        conn.commit()
        conn.close()

        # Check if health degraded
        self._check_health_thresholds(agent)

    @contextmanager
    def track(self, agent: str, task: str, context: Optional[dict] = None):
        """
        Context manager for tracking execution.

        Usage:
            with monitor.track("telegram", "process_message"):
                # ... do work ...
                pass
        """
        start = time.time()
        error = None
        success = True

        try:
            yield
        except Exception as e:
            success = False
            error = str(e)
            raise
        finally:
            duration = time.time() - start
            self.record_execution(agent, task, duration, success, error, context)

    def get_health(self, agent: str, window_hours: int = 24) -> dict:
        """
        Get agent health metrics for the specified time window.

        Returns:
            {
                "agent": str,
                "status": "healthy" | "degraded" | "down",
                "success_rate": float (0-1),
                "avg_duration": float (seconds),
                "error_count": int,
                "last_run": datetime,
                "total_runs": int
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        since = datetime.now() - timedelta(hours=window_hours)

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                AVG(duration_seconds) as avg_duration,
                SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as errors,
                MAX(start_time) as last_run
            FROM agent_executions
            WHERE agent = ? AND start_time >= ?
        """, (agent, since.isoformat()))

        row = cursor.fetchone()
        conn.close()

        total, successes, avg_duration, errors, last_run = row

        if total == 0:
            return {
                "agent": agent,
                "status": "unknown",
                "success_rate": 0.0,
                "avg_duration": 0.0,
                "error_count": 0,
                "last_run": None,
                "total_runs": 0
            }

        success_rate = successes / total
        avg_duration = avg_duration or 0.0

        # Determine status
        if success_rate < 0.75:
            status = "down"
        elif success_rate < 0.90:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "agent": agent,
            "status": status,
            "success_rate": success_rate,
            "avg_duration": avg_duration,
            "error_count": errors,
            "last_run": last_run,
            "total_runs": total
        }

    def get_recent_errors(self, agent: Optional[str] = None, limit: int = 10) -> list[dict]:
        """Get recent execution failures"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if agent:
            cursor.execute("""
                SELECT agent, task, start_time, error_message
                FROM agent_executions
                WHERE success = FALSE AND agent = ?
                ORDER BY start_time DESC
                LIMIT ?
            """, (agent, limit))
        else:
            cursor.execute("""
                SELECT agent, task, start_time, error_message
                FROM agent_executions
                WHERE success = FALSE
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "agent": row[0],
                "task": row[1],
                "timestamp": row[2],
                "error": row[3]
            }
            for row in rows
        ]

    def create_alert(self, agent: str, alert_type: str, message: str):
        """Create health alert"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO agent_alerts (agent, alert_type, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (agent, alert_type, message, datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def get_active_alerts(self) -> list[dict]:
        """Get unresolved alerts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT agent, alert_type, message, timestamp
            FROM agent_alerts
            WHERE resolved = FALSE
            ORDER BY timestamp DESC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "agent": row[0],
                "type": row[1],
                "message": row[2],
                "timestamp": row[3]
            }
            for row in rows
        ]

    def _check_health_thresholds(self, agent: str):
        """Check if agent health crossed alert thresholds"""
        health = self.get_health(agent, window_hours=1)

        # Alert if success rate drops below 75% in last hour
        if health["total_runs"] >= 3 and health["success_rate"] < 0.75:
            self.create_alert(
                agent,
                "low_success_rate",
                f"Success rate dropped to {health['success_rate']:.1%} in last hour"
            )

        # Alert if avg duration exceeds 30 seconds
        if health["avg_duration"] > 30:
            self.create_alert(
                agent,
                "slow_execution",
                f"Average execution time: {health['avg_duration']:.1f}s"
            )

    def show_dashboard(self, window_hours: int = 24):
        """Display agent health dashboard"""
        print("\n" + "═" * 70)
        print("  Agent Health Dashboard")
        print("═" * 70)
        print(f"  Window: Last {window_hours} hours\n")

        agents = ["telegram", "bambu", "legalkanban", "briefings", "system"]

        for agent in agents:
            health = self.get_health(agent, window_hours)

            # Status icon
            if health["status"] == "healthy":
                icon = "✅"
            elif health["status"] == "degraded":
                icon = "⚠️ "
            elif health["status"] == "down":
                icon = "❌"
            else:
                icon = "❓"

            # Format metrics
            success_rate = f"{health['success_rate']:.0%}"
            avg_duration = f"{health['avg_duration']:.1f}s"
            runs = health['total_runs']

            print(f"  {icon} {agent:15} {health['status']:10} {success_rate:>6} success   avg {avg_duration:>6}   {runs:>3} runs")

        # Recent failures
        errors = self.get_recent_errors(limit=5)
        if errors:
            print("\n" + "─" * 70)
            print("  Recent Failures:")
            for err in errors:
                timestamp = datetime.fromisoformat(err["timestamp"]).strftime("%H:%M")
                print(f"    [{timestamp}] {err['agent']:12} {err['task']}")
                print(f"            {err['error'][:60]}")

        # Active alerts
        alerts = self.get_active_alerts()
        if alerts:
            print("\n" + "─" * 70)
            print("  Active Alerts:")
            for alert in alerts:
                print(f"    🚨 {alert['agent']:12} [{alert['type']}]")
                print(f"            {alert['message']}")

        print("═" * 70 + "\n")

    def cleanup_old_data(self, days: int = 30):
        """Delete execution records older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff = datetime.now() - timedelta(days=days)

        cursor.execute("""
            DELETE FROM agent_executions
            WHERE start_time < ?
        """, (cutoff.isoformat(),))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent health monitoring CLI")
    parser.add_argument("--dashboard", action="store_true", help="Show health dashboard")
    parser.add_argument("--status", metavar="AGENT", help="Show status for specific agent")
    parser.add_argument("--errors", action="store_true", help="Show recent errors")
    parser.add_argument("--alerts", action="store_true", help="Show active alerts")
    parser.add_argument("--cleanup", type=int, metavar="DAYS", help="Clean up records older than N days")
    parser.add_argument("--window", type=int, default=24, help="Time window in hours (default: 24)")

    args = parser.parse_args()

    monitor = AgentHealthMonitor()

    if args.dashboard:
        monitor.show_dashboard(args.window)

    elif args.status:
        health = monitor.get_health(args.status, args.window)
        print(f"\nAgent: {health['agent']}")
        print(f"Status: {health['status']}")
        print(f"Success Rate: {health['success_rate']:.1%}")
        print(f"Avg Duration: {health['avg_duration']:.2f}s")
        print(f"Error Count: {health['error_count']}")
        print(f"Total Runs: {health['total_runs']}")
        print(f"Last Run: {health['last_run']}\n")

    elif args.errors:
        errors = monitor.get_recent_errors(limit=10)
        print(f"\nRecent Errors ({len(errors)}):")
        for err in errors:
            print(f"  [{err['timestamp']}] {err['agent']} - {err['task']}")
            print(f"    Error: {err['error']}\n")

    elif args.alerts:
        alerts = monitor.get_active_alerts()
        print(f"\nActive Alerts ({len(alerts)}):")
        for alert in alerts:
            print(f"  {alert['agent']} [{alert['type']}]")
            print(f"    {alert['message']}")
            print(f"    {alert['timestamp']}\n")

    elif args.cleanup:
        deleted = monitor.cleanup_old_data(args.cleanup)
        print(f"Deleted {deleted} execution records older than {args.cleanup} days")

    else:
        parser.print_help()
