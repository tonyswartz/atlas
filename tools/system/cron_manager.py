#!/usr/bin/env python3
"""
Cron job management utilities.

Provides safe cron manipulation: list, add, remove, update schedules.
All operations use subprocess to interact with crontab.
"""

import re
import subprocess
import sys
from typing import List, Dict, Optional


def list_cron_jobs() -> List[Dict[str, str]]:
    """
    List all cron jobs for the current user.

    Returns:
        List of dicts with keys: schedule, command, full_line
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            return []

        jobs = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Cron format: minute hour day month weekday command
            # Example: 0 6 * * * /path/to/script.py
            parts = line.split(None, 5)
            if len(parts) >= 6:
                schedule = " ".join(parts[:5])
                command = parts[5]
                jobs.append({
                    "schedule": schedule,
                    "command": command,
                    "full_line": line
                })

        return jobs
    except Exception as e:
        print(f"ERROR: Failed to list cron jobs: {e}", file=sys.stderr)
        return []


def add_cron_job(schedule: str, command: str, comment: Optional[str] = None) -> bool:
    """
    Add a new cron job.

    Args:
        schedule: Cron schedule (e.g., "0 6 * * *" for 6am daily)
        command: Command to run
        comment: Optional comment line to add above the job

    Returns:
        True if successful, False otherwise
    """
    if not _validate_cron_schedule(schedule):
        print(f"ERROR: Invalid cron schedule: {schedule}", file=sys.stderr)
        return False

    try:
        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False
        )
        existing = result.stdout if result.returncode == 0 else ""

        # Check if job already exists
        new_line = f"{schedule} {command}"
        if new_line in existing:
            print(f"WARNING: Cron job already exists: {new_line}", file=sys.stderr)
            return True

        # Append new job
        new_crontab = existing.rstrip() + "\n"
        if comment:
            new_crontab += f"# {comment}\n"
        new_crontab += f"{new_line}\n"

        # Write updated crontab
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True
        )

        print(f"OK: Added cron job: {new_line}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to add cron job: {e}", file=sys.stderr)
        return False


def remove_cron_job(pattern: str) -> bool:
    """
    Remove cron job(s) matching a pattern.

    Args:
        pattern: Substring to match in the command portion

    Returns:
        True if at least one job was removed, False otherwise
    """
    try:
        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            print("WARNING: No crontab exists", file=sys.stderr)
            return False

        # Filter out matching jobs
        lines = result.stdout.splitlines()
        new_lines = []
        removed_count = 0

        for line in lines:
            if line.strip().startswith("#") or not line.strip():
                new_lines.append(line)
                continue

            if pattern in line:
                print(f"Removing: {line}")
                removed_count += 1
            else:
                new_lines.append(line)

        if removed_count == 0:
            print(f"WARNING: No cron jobs matched pattern: {pattern}", file=sys.stderr)
            return False

        # Write updated crontab
        new_crontab = "\n".join(new_lines) + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True
        )

        print(f"OK: Removed {removed_count} cron job(s)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to remove cron job: {e}", file=sys.stderr)
        return False


def update_cron_schedule(pattern: str, new_schedule: str) -> bool:
    """
    Update the schedule of cron job(s) matching a pattern.

    Args:
        pattern: Substring to match in the command portion
        new_schedule: New cron schedule (e.g., "0 17 * * *" for 5pm daily)

    Returns:
        True if at least one job was updated, False otherwise
    """
    if not _validate_cron_schedule(new_schedule):
        print(f"ERROR: Invalid cron schedule: {new_schedule}", file=sys.stderr)
        return False

    try:
        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            print("WARNING: No crontab exists", file=sys.stderr)
            return False

        # Update matching jobs
        lines = result.stdout.splitlines()
        new_lines = []
        updated_count = 0

        for line in lines:
            if line.strip().startswith("#") or not line.strip():
                new_lines.append(line)
                continue

            if pattern in line:
                # Extract command portion (after schedule)
                parts = line.split(None, 5)
                if len(parts) >= 6:
                    command = parts[5]
                    new_line = f"{new_schedule} {command}"
                    print(f"Updating: {line} → {new_line}")
                    new_lines.append(new_line)
                    updated_count += 1
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if updated_count == 0:
            print(f"WARNING: No cron jobs matched pattern: {pattern}", file=sys.stderr)
            return False

        # Write updated crontab
        new_crontab = "\n".join(new_lines) + "\n"
        subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            check=True
        )

        print(f"OK: Updated {updated_count} cron job(s)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to update cron job: {e}", file=sys.stderr)
        return False


def _validate_cron_schedule(schedule: str) -> bool:
    """
    Validate a cron schedule string.

    Args:
        schedule: Cron schedule (e.g., "0 6 * * *")

    Returns:
        True if valid, False otherwise
    """
    parts = schedule.split()
    if len(parts) != 5:
        return False

    # Basic validation: each part should be number, *, */n, or range
    cron_field_pattern = re.compile(r'^(\*|(\d+(-\d+)?(,\d+(-\d+)?)*)|(\*/\d+))$')

    for part in parts:
        if not cron_field_pattern.match(part):
            return False

    return True


if __name__ == "__main__":
    # CLI interface for testing
    if len(sys.argv) < 2:
        print("Usage:")
        print("  cron_manager.py list")
        print("  cron_manager.py add '<schedule>' '<command>' ['comment']")
        print("  cron_manager.py remove '<pattern>'")
        print("  cron_manager.py update '<pattern>' '<new_schedule>'")
        sys.exit(1)

    action = sys.argv[1]

    if action == "list":
        jobs = list_cron_jobs()
        if not jobs:
            print("No cron jobs found")
        else:
            for job in jobs:
                print(f"{job['schedule']} {job['command']}")

    elif action == "add":
        if len(sys.argv) < 4:
            print("ERROR: add requires schedule and command")
            sys.exit(1)
        schedule = sys.argv[2]
        command = sys.argv[3]
        comment = sys.argv[4] if len(sys.argv) > 4 else None
        success = add_cron_job(schedule, command, comment)
        sys.exit(0 if success else 1)

    elif action == "remove":
        if len(sys.argv) < 3:
            print("ERROR: remove requires pattern")
            sys.exit(1)
        pattern = sys.argv[2]
        success = remove_cron_job(pattern)
        sys.exit(0 if success else 1)

    elif action == "update":
        if len(sys.argv) < 4:
            print("ERROR: update requires pattern and new_schedule")
            sys.exit(1)
        pattern = sys.argv[2]
        new_schedule = sys.argv[3]
        success = update_cron_schedule(pattern, new_schedule)
        sys.exit(0 if success else 1)

    else:
        print(f"ERROR: Unknown action: {action}")
        sys.exit(1)
