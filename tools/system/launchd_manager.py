#!/usr/bin/env python3
"""
Launchd Manager - Creates and schedules launchd jobs
Called by Telegram bot to schedule scripts automatically
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"
TZ = ZoneInfo("America/Los_Angeles")


def create_plist(
    script_path: str,
    label: str,
    schedule: dict = None,
    run_at_load: bool = False,
    description: str = ""
) -> dict:
    """
    Create a launchd plist file.

    Args:
        script_path: Full path to the script to run (relative to REPO_ROOT or absolute)
        label: Reverse domain name label (e.g., com.atlas.my-script)
        schedule: Dict with schedule info (see parse_schedule for format)
        run_at_load: Whether to run script immediately on load
        description: Human-readable description of what this job does

    Returns:
        dict with status, plist_path, and message
    """
    # Resolve script path
    if not script_path.startswith("/"):
        full_script_path = REPO_ROOT / script_path
    else:
        full_script_path = Path(script_path)

    if not full_script_path.exists():
        return {
            "status": "error",
            "message": f"Script not found: {full_script_path}"
        }

    # Ensure label is valid
    if not label.startswith("com.atlas."):
        label = f"com.atlas.{label}"

    # Build plist content
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/envchain</string>
        <string>atlas</string>
        <string>/opt/homebrew/bin/python3</string>
        <string>{full_script_path}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{REPO_ROOT}</string>
    <key>StandardOutPath</key>
    <string>{REPO_ROOT}/logs/{label}.log</string>
    <key>StandardErrorPath</key>
    <string>{REPO_ROOT}/logs/{label}.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
"""

    # Add schedule if provided
    if schedule:
        if schedule.get("type") == "interval":
            plist_content += f"""    <key>StartInterval</key>
    <integer>{schedule["seconds"]}</integer>
"""
        elif schedule.get("type") == "calendar":
            plist_content += """    <key>StartCalendarInterval</key>
"""
            if isinstance(schedule.get("intervals"), list):
                plist_content += """    <array>
"""
                for interval in schedule["intervals"]:
                    plist_content += """        <dict>
"""
                    if "Minute" in interval:
                        plist_content += f"""            <key>Minute</key>
            <integer>{interval["Minute"]}</integer>
"""
                    if "Hour" in interval:
                        plist_content += f"""            <key>Hour</key>
            <integer>{interval["Hour"]}</integer>
"""
                    if "Day" in interval:
                        plist_content += f"""            <key>Day</key>
            <integer>{interval["Day"]}</integer>
"""
                    if "Weekday" in interval:
                        plist_content += f"""            <key>Weekday</key>
            <integer>{interval["Weekday"]}</integer>
"""
                    plist_content += """        </dict>
"""
                plist_content += """    </array>
"""
            else:
                plist_content += """    <dict>
"""
                interval = schedule["intervals"]
                if "Minute" in interval:
                    plist_content += f"""        <key>Minute</key>
        <integer>{interval["Minute"]}</integer>
"""
                if "Hour" in interval:
                    plist_content += f"""        <key>Hour</key>
        <integer>{interval["Hour"]}</integer>
"""
                if "Day" in interval:
                    plist_content += f"""        <key>Day</key>
        <integer>{interval["Day"]}</integer>
"""
                if "Weekday" in interval:
                    plist_content += f"""        <key>Weekday</key>
        <integer>{interval["Weekday"]}</integer>
"""
                plist_content += """    </dict>
"""

    # Add RunAtLoad if requested
    if run_at_load:
        plist_content += """    <key>RunAtLoad</key>
    <true/>
"""

    # Close plist
    plist_content += """</dict>
</plist>
"""

    # Write plist file
    LAUNCHD_DIR.mkdir(exist_ok=True)
    plist_path = LAUNCHD_DIR / f"{label}.plist"

    try:
        plist_path.write_text(plist_content, encoding="utf-8")
        return {
            "status": "success",
            "message": f"Created plist: {label}",
            "plist_path": str(plist_path),
            "label": label,
            "description": description
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create plist: {e}"
        }


def load_job(label: str) -> dict:
    """
    Load a launchd job.

    Args:
        label: Job label (with or without .plist extension)

    Returns:
        dict with status and message
    """
    if not label.endswith(".plist"):
        plist_path = LAUNCHD_DIR / f"{label}.plist"
    else:
        plist_path = LAUNCHD_DIR / label
        label = label[:-6]  # Remove .plist

    if not plist_path.exists():
        return {
            "status": "error",
            "message": f"Plist not found: {plist_path}"
        }

    try:
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return {
                "status": "success",
                "message": f"Loaded job: {label}",
                "label": label
            }
        else:
            # Check if already loaded
            if "service already loaded" in result.stderr.lower():
                return {
                    "status": "success",
                    "message": f"Job already loaded: {label}",
                    "label": label
                }
            return {
                "status": "error",
                "message": f"Failed to load job: {result.stderr}",
                "stderr": result.stderr
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to load job: {e}"
        }


def unload_job(label: str) -> dict:
    """
    Unload a launchd job.

    Args:
        label: Job label (with or without .plist extension)

    Returns:
        dict with status and message
    """
    if not label.endswith(".plist"):
        plist_path = LAUNCHD_DIR / f"{label}.plist"
    else:
        plist_path = LAUNCHD_DIR / label
        label = label[:-6]

    if not plist_path.exists():
        return {
            "status": "error",
            "message": f"Plist not found: {plist_path}"
        }

    try:
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return {
                "status": "success",
                "message": f"Unloaded job: {label}",
                "label": label
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to unload job: {result.stderr}",
                "stderr": result.stderr
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to unload job: {e}"
        }


def list_jobs() -> dict:
    """
    List all atlas launchd jobs.

    Returns:
        dict with status and list of jobs
    """
    try:
        plist_files = list(LAUNCHD_DIR.glob("com.atlas.*.plist"))
        jobs = []

        for plist_file in plist_files:
            label = plist_file.stem
            # Check if loaded
            result = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True,
                text=True,
                timeout=5
            )
            loaded = result.returncode == 0

            jobs.append({
                "label": label,
                "plist_path": str(plist_file),
                "loaded": loaded
            })

        return {
            "status": "success",
            "jobs": jobs,
            "count": len(jobs)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to list jobs: {e}"
        }


def parse_schedule(schedule_str: str) -> dict:
    """
    Parse human-readable schedule into launchd format.

    Supported formats:
    - "every 5 minutes" → StartInterval 300 seconds
    - "every hour" → StartInterval 3600 seconds
    - "every day at 9am" → StartCalendarInterval Hour=9
    - "every weekday at 5pm" → StartCalendarInterval Weekday=1-5, Hour=17
    - "daily at 9:30am" → StartCalendarInterval Hour=9, Minute=30

    Args:
        schedule_str: Human-readable schedule string

    Returns:
        dict with schedule configuration
    """
    schedule_str = schedule_str.lower().strip()

    # Every X minutes/hours
    if "every" in schedule_str and "minute" in schedule_str:
        parts = schedule_str.split()
        try:
            minutes = int(parts[1])
            return {
                "type": "interval",
                "seconds": minutes * 60
            }
        except (IndexError, ValueError):
            pass

    if "every hour" in schedule_str:
        return {
            "type": "interval",
            "seconds": 3600
        }

    # Daily at specific time
    if any(word in schedule_str for word in ["daily", "every day"]):
        # Extract time
        hour, minute = 0, 0
        if "at" in schedule_str:
            time_str = schedule_str.split("at")[1].strip()
            hour, minute = _parse_time(time_str)

        return {
            "type": "calendar",
            "intervals": {
                "Hour": hour,
                "Minute": minute
            }
        }

    # Weekday at specific time
    if "weekday" in schedule_str:
        hour, minute = 0, 0
        if "at" in schedule_str:
            time_str = schedule_str.split("at")[1].strip()
            hour, minute = _parse_time(time_str)

        # Create 5 entries for Monday-Friday
        intervals = []
        for weekday in range(1, 6):  # 1=Monday, 5=Friday
            intervals.append({
                "Weekday": weekday,
                "Hour": hour,
                "Minute": minute
            })

        return {
            "type": "calendar",
            "intervals": intervals
        }

    # Default to daily at 9am if can't parse
    return {
        "type": "calendar",
        "intervals": {
            "Hour": 9,
            "Minute": 0
        }
    }


def _parse_time(time_str: str) -> tuple:
    """Parse time string like '9am', '5:30pm' into (hour, minute)."""
    time_str = time_str.strip().lower()

    # Handle am/pm
    is_pm = "pm" in time_str
    time_str = time_str.replace("am", "").replace("pm", "").strip()

    # Split hour:minute
    if ":" in time_str:
        hour, minute = time_str.split(":")
        hour = int(hour)
        minute = int(minute)
    else:
        hour = int(time_str)
        minute = 0

    # Convert to 24-hour
    if is_pm and hour < 12:
        hour += 12
    elif not is_pm and hour == 12:
        hour = 0

    return hour, minute


def main():
    """CLI interface for launchd_manager."""
    parser = argparse.ArgumentParser(description="Manage launchd jobs")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Create plist
    create_parser = subparsers.add_parser("create", help="Create a launchd plist")
    create_parser.add_argument("--script", required=True, help="Path to script (relative or absolute)")
    create_parser.add_argument("--label", required=True, help="Job label (e.g., my-daily-task)")
    create_parser.add_argument("--schedule", help="Schedule (e.g., 'every 5 minutes', 'daily at 9am')")
    create_parser.add_argument("--run-at-load", action="store_true", help="Run immediately on load")
    create_parser.add_argument("--description", default="", help="Description of what this job does")

    # Load job
    load_parser = subparsers.add_parser("load", help="Load a launchd job")
    load_parser.add_argument("label", help="Job label")

    # Unload job
    unload_parser = subparsers.add_parser("unload", help="Unload a launchd job")
    unload_parser.add_argument("label", help="Job label")

    # List jobs
    subparsers.add_parser("list", help="List all atlas launchd jobs")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    if args.action == "create":
        schedule = None
        if args.schedule:
            schedule = parse_schedule(args.schedule)

        result = create_plist(
            args.script,
            args.label,
            schedule,
            args.run_at_load,
            args.description
        )
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "success" else 1)

    elif args.action == "load":
        result = load_job(args.label)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "success" else 1)

    elif args.action == "unload":
        result = unload_job(args.label)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "success" else 1)

    elif args.action == "list":
        result = list_jobs()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
