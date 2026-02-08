#!/usr/bin/env python3
"""
System configuration and automation setup.

Handles:
- Chat ID destination updates for briefing scripts
- Cron job management (add/remove/update schedules)
- New automation creation (YouTube monitors, RSS feeds, etc.)
- Environment variable updates

Usage:
    python system_config.py --action <action> [options]

Actions:
    update_chat_id      Update chat destination for a briefing script
    add_cron            Add a new cron job
    remove_cron         Remove a cron job
    update_cron_time    Change when a cron job runs
    create_monitor      Create a new monitoring automation (YouTube, RSS, etc.)
    list_automations    List all active automations
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from cron_manager import add_cron_job, remove_cron_job, update_cron_schedule, list_cron_jobs

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"
BRIEFING_SCRIPTS = {
    "daily_brief": REPO_ROOT / "tools/briefings/daily_brief.py",
    "research_brief": REPO_ROOT / "tools/briefings/research_brief.py",
    "local_news": REPO_ROOT / "tools/briefings/local_news.py",
    "weekly_review": REPO_ROOT / "tools/briefings/weekly_review.py",
}


def update_chat_id(script_name: str, chat_id: str) -> Dict:
    """
    Update the Telegram chat ID for a briefing script.

    For scripts that read from environment variable, updates .env.
    For scripts with hardcoded chat IDs, updates the source file.

    Args:
        script_name: Name of briefing script (daily_brief, research_brief, etc.)
        chat_id: New Telegram chat ID (can be group or individual)

    Returns:
        Dict with success status and message
    """
    if script_name not in BRIEFING_SCRIPTS:
        return {
            "success": False,
            "error": f"Unknown script: {script_name}. Available: {', '.join(BRIEFING_SCRIPTS.keys())}"
        }

    script_path = BRIEFING_SCRIPTS[script_name]
    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}

    # Read script content
    content = script_path.read_text(encoding="utf-8")

    # Strategy 1: Script reads from environment variable
    if "os.environ.get" in content and "TELEGRAM_CHAT_ID" in content:
        # Update .env file
        if _update_env_var("TELEGRAM_CHAT_ID", chat_id):
            return {
                "success": True,
                "message": f"Updated TELEGRAM_CHAT_ID={chat_id} in .env. All scripts using this variable will now send to {chat_id}."
            }
        else:
            return {"success": False, "error": "Failed to update .env file"}

    # Strategy 2: Script has hardcoded chat_id
    # Pattern: chat_id = "8241581699" or TELEGRAM_CHAT_ID = "8241581699"
    pattern = re.compile(r'(chat_id|TELEGRAM_CHAT_ID)\s*=\s*["\'](\d+)["\']')
    match = pattern.search(content)

    if not match:
        return {
            "success": False,
            "error": f"Could not find chat_id in {script_name}. Manual update required."
        }

    old_chat_id = match.group(2)
    old_line = match.group(0)
    var_name = match.group(1)
    new_line = f'{var_name} = "{chat_id}"'

    # Replace in content
    new_content = content.replace(old_line, new_line)
    script_path.write_text(new_content, encoding="utf-8")

    return {
        "success": True,
        "message": f"Updated {script_name}: changed chat_id from {old_chat_id} to {chat_id}",
        "old_chat_id": old_chat_id,
        "new_chat_id": chat_id
    }


def _update_env_var(key: str, value: str) -> bool:
    """
    Update or add an environment variable in .env file.

    Args:
        key: Environment variable name
        value: New value

    Returns:
        True if successful, False otherwise
    """
    try:
        # Read existing .env
        if ENV_FILE.exists():
            lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        # Update or append
        found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f'{key}="{value}"')
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f'{key}="{value}"')

        # Write back
        ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except Exception as e:
        print(f"ERROR: Failed to update .env: {e}", file=sys.stderr)
        return False


def add_automation(script_path: str, schedule: str, comment: Optional[str] = None) -> Dict:
    """
    Add a new cron job for an automation script.

    Args:
        script_path: Full path to script (relative to repo root or absolute)
        schedule: Cron schedule string (e.g., "0 17 * * *" for 5pm daily)
        comment: Optional comment for crontab

    Returns:
        Dict with success status and message
    """
    # Resolve path
    if not Path(script_path).is_absolute():
        full_path = REPO_ROOT / script_path
    else:
        full_path = Path(script_path)

    if not full_path.exists():
        return {"success": False, "error": f"Script not found: {full_path}"}

    # Get Python interpreter path
    python_bin = sys.executable

    # Build command with logging
    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{full_path.stem}.log"
    command = f"{python_bin} {full_path} >> {log_file} 2>&1"

    # Add cron job
    success = add_cron_job(schedule, command, comment)

    if success:
        return {
            "success": True,
            "message": f"Added cron job: {schedule} {full_path.name}",
            "schedule": schedule,
            "script": str(full_path),
            "log_file": str(log_file)
        }
    else:
        return {"success": False, "error": "Failed to add cron job"}


def remove_automation(pattern: str) -> Dict:
    """
    Remove cron job(s) matching a pattern.

    Args:
        pattern: Substring to match in the cron job command

    Returns:
        Dict with success status and message
    """
    success = remove_cron_job(pattern)
    if success:
        return {
            "success": True,
            "message": f"Removed cron job(s) matching: {pattern}"
        }
    else:
        return {
            "success": False,
            "error": f"No cron jobs matched pattern: {pattern}"
        }


def update_automation_schedule(pattern: str, new_schedule: str) -> Dict:
    """
    Update the schedule of existing cron job(s).

    Args:
        pattern: Substring to match in the cron job command
        new_schedule: New cron schedule (e.g., "0 6 * * *")

    Returns:
        Dict with success status and message
    """
    success = update_cron_schedule(pattern, new_schedule)
    if success:
        return {
            "success": True,
            "message": f"Updated schedule for {pattern} to {new_schedule}"
        }
    else:
        return {
            "success": False,
            "error": f"Failed to update schedule for {pattern}"
        }


def list_automations() -> Dict:
    """
    List all active automation cron jobs.

    Returns:
        Dict with success status and list of jobs
    """
    jobs = list_cron_jobs()

    # Filter to only jobs pointing to our repo
    repo_jobs = [
        job for job in jobs
        if str(REPO_ROOT) in job["command"]
    ]

    return {
        "success": True,
        "count": len(repo_jobs),
        "jobs": repo_jobs
    }


def create_youtube_monitor(channel_url: str, schedule: str, chat_id: Optional[str] = None) -> Dict:
    """
    Create a YouTube channel monitor that checks for new videos.

    Args:
        channel_url: YouTube channel URL
        schedule: Cron schedule for checks (e.g., "0 17 * * *" for 5pm daily)
        chat_id: Optional Telegram chat ID (uses default if not provided)

    Returns:
        Dict with success status and message
    """
    # Extract channel ID from URL
    # Formats: youtube.com/@username, youtube.com/channel/ID, youtube.com/c/name
    channel_id = None
    if "@" in channel_url:
        channel_id = channel_url.split("@")[1].split("?")[0].split("/")[0]
    elif "/channel/" in channel_url:
        channel_id = channel_url.split("/channel/")[1].split("?")[0].split("/")[0]
    elif "/c/" in channel_url:
        channel_id = channel_url.split("/c/")[1].split("?")[0].split("/")[0]
    else:
        return {"success": False, "error": f"Could not parse channel ID from URL: {channel_url}"}

    # Create monitor script from template
    monitor_script = REPO_ROOT / "tools/monitors" / f"youtube_{channel_id}.py"
    monitor_script.parent.mkdir(parents=True, exist_ok=True)

    # Use chat_id from env if not provided
    if not chat_id:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "8241581699")

    # Write monitor script
    template = _youtube_monitor_template(channel_url, channel_id, chat_id)
    monitor_script.write_text(template, encoding="utf-8")
    monitor_script.chmod(0o755)

    # Add cron job
    result = add_automation(
        str(monitor_script),
        schedule,
        comment=f"YouTube monitor: {channel_id}"
    )

    if result["success"]:
        result["message"] = f"Created YouTube monitor for {channel_id}. Checks: {schedule}"
        result["monitor_script"] = str(monitor_script)

    return result


def _youtube_monitor_template(channel_url: str, channel_id: str, chat_id: str) -> str:
    """Generate YouTube monitor script from template."""
    return f'''#!/usr/bin/env python3
"""
YouTube channel monitor: {channel_id}

Checks for new videos and sends Telegram notification.
Created by system_config.py automation.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CHANNEL_URL = "{channel_url}"
CHANNEL_ID = "{channel_id}"
TELEGRAM_CHAT_ID = "{chat_id}"
STATE_FILE = Path(__file__).parent.parent.parent / "data" / f"youtube_{{CHANNEL_ID}}_state.json"
TZ = ZoneInfo("America/Los_Angeles")


def get_latest_video():
    """
    Fetch latest video from YouTube channel via RSS feed.

    Returns:
        Dict with video_id, title, published_date, or None if error
    """
    # YouTube RSS feed format
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={{CHANNEL_ID}}"

    try:
        req = urllib.request.Request(rss_url, headers={{"User-Agent": "Mozilla/5.0"}})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml = resp.read().decode("utf-8")

        # Simple XML parsing (no external deps)
        import re
        entry_match = re.search(r'<entry>(.*?)</entry>', xml, re.DOTALL)
        if not entry_match:
            return None

        entry = entry_match.group(1)

        video_id_match = re.search(r'<yt:videoId>(.*?)</yt:videoId>', entry)
        title_match = re.search(r'<title>(.*?)</title>', entry)
        published_match = re.search(r'<published>(.*?)</published>', entry)

        if not (video_id_match and title_match and published_match):
            return None

        return {{
            "video_id": video_id_match.group(1),
            "title": title_match.group(1),
            "published": published_match.group(1),
            "url": f"https://youtube.com/watch?v={{video_id_match.group(1)}}"
        }}
    except Exception as e:
        print(f"ERROR: Failed to fetch YouTube feed: {{e}}", file=sys.stderr)
        return None


def load_state():
    """Load last seen video from state file."""
    if not STATE_FILE.exists():
        return {{}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {{}}


def save_state(state):
    """Save current state to file."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"ERROR: Failed to save state: {{e}}", file=sys.stderr)


def send_telegram(text: str) -> bool:
    """Send Telegram notification."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token or token.startswith("<"):
        print("ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{{token}}/sendMessage"
    payload = json.dumps({{
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }}).encode()

    try:
        req = urllib.request.Request(url, data=payload, headers={{"Content-Type": "application/json"}})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"ERROR: Failed to send Telegram message: {{e}}", file=sys.stderr)
        return False


def main():
    latest = get_latest_video()
    if not latest:
        print("WARNING: Could not fetch latest video")
        sys.exit(1)

    state = load_state()
    last_video_id = state.get("last_video_id")

    # First run: just save state
    if not last_video_id:
        print(f"First run. Latest video: {{latest['title']}}")
        save_state({{"last_video_id": latest["video_id"], "last_check": datetime.now(TZ).isoformat()}})
        sys.exit(0)

    # Check if new video posted
    if latest["video_id"] != last_video_id:
        print(f"New video detected: {{latest['title']}}")

        message = (
            f"🎥 **New video on {{CHANNEL_ID}}**\\n\\n"
            f"**{{latest['title']}}**\\n\\n"
            f"{{latest['url']}}"
        )

        if send_telegram(message):
            print("Notification sent")
            save_state({{"last_video_id": latest["video_id"], "last_check": datetime.now(TZ).isoformat()}})
        else:
            print("ERROR: Failed to send notification")
            sys.exit(1)
    else:
        print(f"No new videos. Latest: {{latest['title']}}")
        state["last_check"] = datetime.now(TZ).isoformat()
        save_state(state)


if __name__ == "__main__":
    main()
'''


def main():
    parser = argparse.ArgumentParser(description="System configuration and automation setup")
    parser.add_argument("--action", required=True, choices=[
        "update_chat_id", "add_cron", "remove_cron", "update_cron_time",
        "create_monitor", "list_automations"
    ])

    # Chat ID update
    parser.add_argument("--script", help="Briefing script name (for update_chat_id)")
    parser.add_argument("--chat-id", help="Telegram chat ID")

    # Cron management
    parser.add_argument("--schedule", help="Cron schedule (e.g., '0 17 * * *' for 5pm daily)")
    parser.add_argument("--script-path", help="Path to script (for add_cron)")
    parser.add_argument("--pattern", help="Pattern to match in cron job (for remove/update)")
    parser.add_argument("--comment", help="Optional comment for cron job")

    # Monitor creation
    parser.add_argument("--monitor-type", choices=["youtube", "rss"], help="Type of monitor to create")
    parser.add_argument("--url", help="URL to monitor (YouTube channel, RSS feed, etc.)")

    args = parser.parse_args()

    result = None

    if args.action == "update_chat_id":
        if not args.script or not args.chat_id:
            print("ERROR: --script and --chat-id required", file=sys.stderr)
            sys.exit(1)
        result = update_chat_id(args.script, args.chat_id)

    elif args.action == "add_cron":
        if not args.schedule or not args.script_path:
            print("ERROR: --schedule and --script-path required", file=sys.stderr)
            sys.exit(1)
        result = add_automation(args.script_path, args.schedule, args.comment)

    elif args.action == "remove_cron":
        if not args.pattern:
            print("ERROR: --pattern required", file=sys.stderr)
            sys.exit(1)
        result = remove_automation(args.pattern)

    elif args.action == "update_cron_time":
        if not args.pattern or not args.schedule:
            print("ERROR: --pattern and --schedule required", file=sys.stderr)
            sys.exit(1)
        result = update_automation_schedule(args.pattern, args.schedule)

    elif args.action == "create_monitor":
        if args.monitor_type == "youtube":
            if not args.url or not args.schedule:
                print("ERROR: --url and --schedule required for YouTube monitor", file=sys.stderr)
                sys.exit(1)
            result = create_youtube_monitor(args.url, args.schedule, args.chat_id)
        else:
            print(f"ERROR: Monitor type {args.monitor_type} not yet implemented", file=sys.stderr)
            sys.exit(1)

    elif args.action == "list_automations":
        result = list_automations()

    # Output result as JSON
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
