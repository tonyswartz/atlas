#!/usr/bin/env python3
"""
Telegram Bot Self-Healing Monitor

Detects and automatically fixes common bot issues:
- Tool loops (stuck calling tools without text responses)
- Session bloat (conversation history too large)
- Bot process crashes
- Stuck/frozen sessions

AUTO-REPAIR CAPABILITY:
- Tracks tool failures over time
- When same tool fails 3+ times in 6 hours, triggers MiniMax auto-fixer
- Creates backups before modifying code
- Validates fixes before deploying

Runs every 5-10 minutes via launchd.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

SESSIONS_FILE = REPO_ROOT / "data" / "sessions.json"
FAILURES_FILE = REPO_ROOT / "data" / "bot_failure_tracking.json"
LOG_FILE = REPO_ROOT / "logs" / "bot_health_monitor.log"
TZ = ZoneInfo("America/Los_Angeles")

# Thresholds for detection
MAX_TOOL_ONLY_MESSAGES = 3  # Max consecutive "[Tools were used.]" messages
MAX_SESSION_MESSAGES = 100  # Max messages before session is too large
MAX_SESSION_AGE_HOURS = 24  # Clear sessions older than this

# Auto-fix configuration (loaded from args/telegram.yaml)
def _get_auto_fix_config() -> dict:
    """Load auto-fix configuration from args/telegram.yaml."""
    try:
        from tools.telegram.config import load_config
        config = load_config()
        return config.get("bot", {}).get("auto_fix", {
            "enabled": True,
            "failures_threshold": 3,
            "time_window_hours": 6
        })
    except Exception:
        # Fallback to defaults
        return {
            "enabled": True,
            "failures_threshold": 3,
            "time_window_hours": 6
        }

AUTO_FIX_CONFIG = _get_auto_fix_config()
AUTO_FIX_ENABLED = AUTO_FIX_CONFIG.get("enabled", True)
AUTO_FIX_FAILURES_THRESHOLD = AUTO_FIX_CONFIG.get("failures_threshold", 3)
AUTO_FIX_TIME_WINDOW_HOURS = AUTO_FIX_CONFIG.get("time_window_hours", 6)


def log(message: str):
    """Log to file and stdout."""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)

    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(log_message + "\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


def load_sessions() -> dict:
    """Load sessions from JSON file."""
    if not SESSIONS_FILE.exists():
        return {}

    try:
        return json.loads(SESSIONS_FILE.read_text())
    except Exception as e:
        log(f"ERROR: Failed to load sessions: {e}")
        return {}


def save_sessions(sessions: dict):
    """Save sessions to JSON file."""
    try:
        SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))
    except Exception as e:
        log(f"ERROR: Failed to save sessions: {e}")


def detect_tool_loop(messages: list) -> bool:
    """
    Detect if session is stuck in a tool loop.
    Returns True if last N messages are all "[Tools were used.]"
    """
    if len(messages) < MAX_TOOL_ONLY_MESSAGES:
        return False

    # Check last N messages
    recent = messages[-MAX_TOOL_ONLY_MESSAGES:]
    tool_only_count = 0

    for msg in recent:
        if msg.get("role") == "assistant":
            content = msg.get("content", "").strip()
            if content == "[Tools were used.]" or content.endswith("[Tools were used.]"):
                tool_only_count += 1

    return tool_only_count >= MAX_TOOL_ONLY_MESSAGES


def detect_session_bloat(messages: list) -> bool:
    """Detect if session has too many messages."""
    return len(messages) > MAX_SESSION_MESSAGES


def is_bot_running() -> bool:
    """Check if Telegram bot process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "telegram/bot.py"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        log(f"ERROR: Failed to check bot process: {e}")
        return False


def restart_bot():
    """Restart the Telegram bot via launchd."""
    try:
        uid = os.getuid()
        result = subprocess.run(
            ["launchctl", "kickstart", "-k", f"gui/{uid}/com.atlas.telegram-bot"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            log("✓ Bot restarted via launchd")
            return True
        else:
            log(f"ERROR: Bot restart failed: {result.stderr}")
            return False
    except Exception as e:
        log(f"ERROR: Failed to restart bot: {e}")
        return False


def send_telegram_alert(message: str):
    """Send alert to user via Telegram."""
    try:
        from tools.common.credentials import get_telegram_token
        import urllib.request

        token = get_telegram_token()
        if not token:
            log("WARNING: No Telegram token - skipping alert")
            return

        chat_id = "8241581699"  # Tony's personal chat
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": f"🔧 **Bot Health Monitor**\n\n{message}",
            "parse_mode": "Markdown"
        }).encode()

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log("✓ Alert sent to Telegram")
    except Exception as e:
        log(f"ERROR: Failed to send Telegram alert: {e}")


def load_failure_tracking() -> dict:
    """Load failure tracking data from JSON file."""
    if not FAILURES_FILE.exists():
        return {}

    try:
        return json.loads(FAILURES_FILE.read_text())
    except Exception as e:
        log(f"ERROR: Failed to load failure tracking: {e}")
        return {}


def save_failure_tracking(tracking: dict):
    """Save failure tracking data to JSON file."""
    try:
        FAILURES_FILE.parent.mkdir(exist_ok=True, parents=True)
        FAILURES_FILE.write_text(json.dumps(tracking, indent=2))
    except Exception as e:
        log(f"ERROR: Failed to save failure tracking: {e}")


def extract_tool_from_session(messages: list) -> str:
    """
    Extract which tool likely caused the failure from session messages.

    Looks for patterns in recent messages to identify the problematic tool.
    Returns tool name or "unknown" if can't determine.
    """
    # Look at last few user messages for clues
    for msg in reversed(messages[-10:]):
        if msg.get("role") == "user":
            content = msg.get("content", "").lower()

            # Check for common tool patterns
            if "rotary" in content:
                return "rotary_tool"
            elif "kanban" in content or "task" in content:
                return "kanban_tool"
            elif "calendar" in content or "schedule" in content:
                return "calendar_tool"
            elif "journal" in content or "log" in content:
                return "journal_tool"
            elif "reminder" in content:
                return "reminder_tool"
            elif "memory" in content or "remember" in content:
                return "memory_tool"

    # Default fallback
    return "unknown_tool"


def record_failure(tool_name: str, error_context: str):
    """Record a tool failure for auto-fix tracking."""
    tracking = load_failure_tracking()

    if tool_name not in tracking:
        tracking[tool_name] = []

    tracking[tool_name].append({
        "timestamp": datetime.now(TZ).isoformat(),
        "error": error_context,
        "context": f"Tool loop detected - {MAX_TOOL_ONLY_MESSAGES} consecutive tool-only messages"
    })

    save_failure_tracking(tracking)
    log(f"Recorded failure for {tool_name} (total: {len(tracking[tool_name])})")


def should_trigger_auto_fix(tool_name: str) -> tuple[bool, list]:
    """
    Check if tool has failed enough times to trigger auto-fix.

    Returns:
        (should_fix: bool, recent_failures: list)
    """
    if not AUTO_FIX_ENABLED:
        return False, []

    tracking = load_failure_tracking()
    failures = tracking.get(tool_name, [])

    if not failures:
        return False, []

    # Filter to failures within time window
    cutoff = datetime.now(TZ) - timedelta(hours=AUTO_FIX_TIME_WINDOW_HOURS)
    recent = [
        f for f in failures
        if datetime.fromisoformat(f["timestamp"]) > cutoff
    ]

    if len(recent) >= AUTO_FIX_FAILURES_THRESHOLD:
        log(f"⚠️  {tool_name} has {len(recent)} failures in {AUTO_FIX_TIME_WINDOW_HOURS}h - triggering auto-fix")
        return True, recent

    return False, []


def trigger_auto_fix(tool_name: str, failures: list) -> dict:
    """
    Trigger autonomous code repair using MiniMax.

    Returns result dict from auto_fixer.
    """
    try:
        from tools.telegram.auto_fixer import fix_tool

        log(f"🤖 Triggering MiniMax auto-fix for {tool_name}")
        result = fix_tool(tool_name, failures)

        if result["success"]:
            log(f"✓ Auto-fix succeeded: {result['changes_summary']}")

            # Clear failure tracking for this tool after successful fix
            tracking = load_failure_tracking()
            if tool_name in tracking:
                del tracking[tool_name]
                save_failure_tracking(tracking)
                log(f"Cleared failure history for {tool_name}")
        else:
            log(f"✗ Auto-fix failed: {result['changes_summary']}")

        return result
    except Exception as e:
        log(f"ERROR: Auto-fix exception: {e}")
        return {
            "success": False,
            "tool_name": tool_name,
            "changes_summary": f"Exception during auto-fix: {e}"
        }


def check_and_heal():
    """Main health check and remediation logic."""
    log("Starting health check...")

    sessions = load_sessions()
    issues_found = []
    sessions_cleared = []
    auto_fixes_applied = []

    # Check each session
    for user_id, session_data in list(sessions.items()):
        messages = session_data.get("messages", [])

        # Detect tool loops
        if detect_tool_loop(messages):
            log(f"⚠️  Tool loop detected in session {user_id}")
            issues_found.append(f"Tool loop in session {user_id}")

            # Extract which tool caused the failure
            tool_name = extract_tool_from_session(messages)
            log(f"Identified problematic tool: {tool_name}")

            # Record the failure
            record_failure(tool_name, "Tool loop - consecutive tool-only messages")

            # Check if we should trigger auto-fix
            should_fix, recent_failures = should_trigger_auto_fix(tool_name)
            if should_fix:
                log(f"🤖 Triggering auto-fix for {tool_name}")
                fix_result = trigger_auto_fix(tool_name, recent_failures)

                if fix_result["success"]:
                    # Get git commit info
                    try:
                        git_hash = subprocess.run(
                            ["git", "rev-parse", "--short", "HEAD"],
                            capture_output=True,
                            text=True,
                            cwd=REPO_ROOT,
                            timeout=5
                        ).stdout.strip()
                        git_info = f" (commit: `{git_hash}`)" if git_hash else ""
                    except Exception:
                        git_info = ""

                    auto_fixes_applied.append(
                        f"✓ Auto-fixed {tool_name}: {fix_result['changes_summary']}{git_info}"
                    )
                else:
                    auto_fixes_applied.append(
                        f"✗ Auto-fix failed for {tool_name}: {fix_result['changes_summary']}"
                    )

            sessions_cleared.append(user_id)
            del sessions[user_id]
            continue

        # Detect session bloat
        if detect_session_bloat(messages):
            log(f"⚠️  Session bloat detected in session {user_id} ({len(messages)} messages)")
            issues_found.append(f"Session bloat in {user_id} ({len(messages)} messages)")
            sessions_cleared.append(user_id)
            del sessions[user_id]
            continue

    # Save if any sessions were cleared
    if sessions_cleared:
        save_sessions(sessions)
        log(f"✓ Cleared {len(sessions_cleared)} stuck sessions: {sessions_cleared}")

    # Check if bot is running
    if not is_bot_running():
        log("⚠️  Bot process not running!")
        issues_found.append("Bot process not running")

        # Try to restart
        if restart_bot():
            issues_found.append("Bot restarted successfully")
        else:
            issues_found.append("Failed to restart bot - manual intervention needed")

    # Send alert if issues were found
    if issues_found or auto_fixes_applied:
        alert_message = ""

        if issues_found:
            alert_message += "**Issues detected and remediated:**\n\n"
            for issue in issues_found:
                alert_message += f"• {issue}\n"

        if auto_fixes_applied:
            alert_message += "\n**🤖 Autonomous Code Repairs:**\n\n"
            for fix in auto_fixes_applied:
                alert_message += f"• {fix}\n"

        if sessions_cleared:
            alert_message += f"\nCleared sessions: {', '.join(sessions_cleared)}"

        send_telegram_alert(alert_message)
        log(f"Health check complete - {len(issues_found)} issues, {len(auto_fixes_applied)} auto-fixes")
    else:
        log("✓ Health check complete - no issues found")

    return len(issues_found)


def main():
    """Run health check and remediation."""
    try:
        issues_count = check_and_heal()
        return 0 if issues_count == 0 else 1
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
