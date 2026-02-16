#!/usr/bin/env python3
"""
Telegram Bot Self-Healing Monitor

Detects and automatically fixes common bot issues:
- Tool loops (stuck calling tools without text responses)
- Session bloat (conversation history too large)
- Bot process crashes
- Stuck/frozen sessions

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
LOG_FILE = REPO_ROOT / "logs" / "bot_health_monitor.log"
TZ = ZoneInfo("America/Los_Angeles")

# Thresholds for detection
MAX_TOOL_ONLY_MESSAGES = 3  # Max consecutive "[Tools were used.]" messages
MAX_SESSION_MESSAGES = 100  # Max messages before session is too large
MAX_SESSION_AGE_HOURS = 24  # Clear sessions older than this


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


def check_and_heal():
    """Main health check and remediation logic."""
    log("Starting health check...")

    sessions = load_sessions()
    issues_found = []
    sessions_cleared = []

    # Check each session
    for user_id, session_data in list(sessions.items()):
        messages = session_data.get("messages", [])

        # Detect tool loops
        if detect_tool_loop(messages):
            log(f"⚠️  Tool loop detected in session {user_id}")
            issues_found.append(f"Tool loop in session {user_id}")
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
    if issues_found:
        alert_message = "Issues detected and remediated:\n\n"
        for issue in issues_found:
            alert_message += f"• {issue}\n"

        if sessions_cleared:
            alert_message += f"\nCleared sessions: {', '.join(sessions_cleared)}"

        send_telegram_alert(alert_message)
        log(f"Health check complete - {len(issues_found)} issues found")
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
