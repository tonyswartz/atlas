#!/usr/bin/env python3
"""Service Health Monitor - Auto-starts critical services if they're down.

Monitors:
- Telegram bot (tools/telegram/bot.py)
- JeevesUI (http://localhost:6001)

Sends Telegram notification on auto-recovery.
Run via cron every 5-10 minutes.
"""

import os
import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path
from datetime import datetime

# Service definitions
SERVICES = {
    "telegram_bot": {
        "check": lambda: check_process("bot.py"),
        "start": lambda: start_telegram_bot(),
        "critical": True,
        "notify_on_start": True,
    },
    "jeevesui": {
        "check": lambda: check_http("http://localhost:6001"),
        "start": lambda: start_jeevesui(),
        "critical": False,
        "notify_on_start": True,
    },
}

STATE_FILE = Path("/Users/printer/atlas/data/service_health_state.json")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "8241581699"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def check_process(name: str) -> bool:
    """Check if process with name in command line is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception as e:
        log(f"Process check failed for {name}: {e}")
        return False


def check_http(url: str) -> bool:
    """Check if HTTP endpoint responds (any response = healthy)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True  # Any HTTP response means server is running
    except urllib.error.HTTPError:
        return True  # HTTP error (like 404) still means server is responding
    except Exception:
        return False  # Connection refused, timeout, etc. = server down


def start_telegram_bot() -> bool:
    """Start Telegram bot via launchctl."""
    try:
        # Unload first (in case it's in a bad state)
        subprocess.run(
            ["launchctl", "unload", os.path.expanduser("~/Library/LaunchAgents/com.atlas.telegram-bot.plist")],
            capture_output=True,
            timeout=10,
        )
        time.sleep(1)

        # Load and start
        result = subprocess.run(
            ["launchctl", "load", os.path.expanduser("~/Library/LaunchAgents/com.atlas.telegram-bot.plist")],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Give it a moment to start
        time.sleep(3)

        # Verify it's running
        if check_process("bot.py"):
            log("Telegram bot started successfully")
            return True
        else:
            log("Telegram bot failed to start")
            return False

    except Exception as e:
        log(f"Failed to start Telegram bot: {e}")
        return False


def start_jeevesui() -> bool:
    """Start JeevesUI server."""
    try:
        # Check if already running
        if check_http("http://localhost:6001"):
            return True

        # Start JeevesUI
        jeevesui_path = Path("/Users/printer/clawd/JeevesUI")
        if not jeevesui_path.exists():
            log("JeevesUI path not found - skipping auto-start")
            return False

        # Launch in background
        subprocess.Popen(
            ["npm", "start"],
            cwd=jeevesui_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait and verify
        time.sleep(5)
        if check_http("http://localhost:6001"):
            log("JeevesUI started successfully")
            return True
        else:
            log("JeevesUI failed to start")
            return False

    except Exception as e:
        log(f"Failed to start JeevesUI: {e}")
        return False


def send_telegram(message: str) -> None:
    """Send Telegram notification."""
    if not TELEGRAM_TOKEN:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }).encode()

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        log(f"Failed to send Telegram notification: {e}")


def load_state() -> dict:
    """Load last recovery state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_recovery": {}}


def save_state(state: dict) -> None:
    """Save recovery state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main() -> int:
    """Check all services and auto-start if needed."""
    log("Running service health check...")

    state = load_state()
    recoveries = []

    for service_name, config in SERVICES.items():
        try:
            # Check if service is healthy
            is_healthy = config["check"]()

            if is_healthy:
                # Service is up - clear any previous recovery timestamp
                if service_name in state["last_recovery"]:
                    del state["last_recovery"][service_name]
                continue

            # Service is down
            log(f"❌ {service_name} is down")

            # Check if we recently tried to recover (prevent spam)
            last_recovery = state["last_recovery"].get(service_name)
            if last_recovery:
                last_recovery_time = datetime.fromisoformat(last_recovery)
                minutes_since = (datetime.now() - last_recovery_time).total_seconds() / 60
                if minutes_since < 15:
                    log(f"  Skipping recovery - attempted {minutes_since:.1f} min ago")
                    continue

            # Attempt recovery
            log(f"  Attempting to start {service_name}...")
            success = config["start"]()

            if success:
                recoveries.append(service_name)
                state["last_recovery"][service_name] = datetime.now().isoformat()
                log(f"✅ {service_name} recovered")
            else:
                log(f"❌ {service_name} recovery failed")
                state["last_recovery"][service_name] = datetime.now().isoformat()

        except Exception as e:
            log(f"Error checking {service_name}: {e}")

    # Send notification if any services were recovered
    if recoveries:
        services_list = ", ".join(recoveries)
        send_telegram(f"🔧 *Service Auto-Recovery*\n\nRestarted: {services_list}")

    save_state(state)
    log("Health check complete")
    return 0


if __name__ == "__main__":
    # Load .env for cron
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
    except ImportError:
        pass

    sys.exit(main())
