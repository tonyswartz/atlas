#!/usr/bin/env python3
"""
LaunchD Configuration Health Checker

Automatically ensures all Atlas launchd services have:
- PYTHONDONTWRITEBYTECODE=1 environment variable

Runs daily via launchd to prevent bytecode cache issues.
Auto-fixes any services missing required configuration.
"""

import json
import os
import plistlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LOG_FILE = REPO_ROOT / "logs" / "launchd_config_checker.log"
TZ = ZoneInfo("America/Los_Angeles")


def log(message: str):
    """Log to file and stdout."""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)

    try:
        LOG_FILE.parent.mkdir(exist_ok=True, parents=True)
        with open(LOG_FILE, "a") as f:
            f.write(log_message + "\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


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
            "text": f"🔧 **LaunchD Config Checker**\n\n{message}",
            "parse_mode": "Markdown"
        }).encode()

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log("✓ Alert sent to Telegram")
    except Exception as e:
        log(f"ERROR: Failed to send Telegram alert: {e}")


def get_atlas_plists() -> list[Path]:
    """Get all Atlas launchd plist files."""
    return sorted(PLIST_DIR.glob("com.atlas.*.plist"))


def check_plist_has_env_var(plist_path: Path, env_var: str) -> bool:
    """Check if plist has specified environment variable."""
    try:
        with open(plist_path, 'rb') as f:
            plist = plistlib.load(f)

        env_vars = plist.get('EnvironmentVariables', {})
        return env_var in env_vars
    except Exception as e:
        log(f"ERROR: Failed to read {plist_path.name}: {e}")
        return False


def add_env_var_to_plist(plist_path: Path, env_var: str, value: str) -> bool:
    """Add environment variable to plist file."""
    try:
        with open(plist_path, 'rb') as f:
            plist = plistlib.load(f)

        if 'EnvironmentVariables' not in plist:
            plist['EnvironmentVariables'] = {}

        plist['EnvironmentVariables'][env_var] = value

        with open(plist_path, 'wb') as f:
            plistlib.dump(plist, f)

        log(f"✓ Added {env_var}={value} to {plist_path.name}")
        return True
    except Exception as e:
        log(f"ERROR: Failed to update {plist_path.name}: {e}")
        return False


def reload_service(plist_path: Path) -> bool:
    """Reload launchd service."""
    try:
        label = plist_path.stem

        # Unload
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            timeout=10
        )

        # Load
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            log(f"✓ Reloaded {label}")
            return True
        else:
            log(f"WARNING: Reload failed for {label}: {result.stderr}")
            return False
    except Exception as e:
        log(f"ERROR: Failed to reload {plist_path.name}: {e}")
        return False


def check_and_fix():
    """Main health check and auto-fix logic."""
    log("Starting launchd configuration check...")

    plists = get_atlas_plists()
    total = len(plists)
    log(f"Found {total} Atlas launchd services")

    missing = []
    fixed = []
    failed = []

    # Check each plist
    for plist_path in plists:
        if not check_plist_has_env_var(plist_path, "PYTHONDONTWRITEBYTECODE"):
            missing.append(plist_path.stem)
            log(f"⚠️  {plist_path.stem} missing PYTHONDONTWRITEBYTECODE")

            # Auto-fix
            if add_env_var_to_plist(plist_path, "PYTHONDONTWRITEBYTECODE", "1"):
                if reload_service(plist_path):
                    fixed.append(plist_path.stem)
                else:
                    failed.append(plist_path.stem)
            else:
                failed.append(plist_path.stem)

    # Report results
    if missing:
        log(f"Found {len(missing)} services missing bytecode prevention")

        if fixed:
            log(f"✓ Auto-fixed {len(fixed)} services")

        if failed:
            log(f"✗ Failed to fix {len(failed)} services: {failed}")

        # Send alert
        alert_message = f"**LaunchD Configuration Issues Fixed**\n\n"
        alert_message += f"Total services: {total}\n"
        alert_message += f"Missing config: {len(missing)}\n\n"

        if fixed:
            alert_message += f"**✓ Auto-fixed ({len(fixed)}):**\n"
            for service in fixed:
                alert_message += f"• {service}\n"

        if failed:
            alert_message += f"\n**✗ Failed to fix ({len(failed)}):**\n"
            for service in failed:
                alert_message += f"• {service}\n"
            alert_message += "\n⚠️ Manual intervention needed"

        send_telegram_alert(alert_message)
    else:
        log(f"✓ All {total} services have correct configuration")

    return len(missing)


def main():
    """Run configuration check and auto-fix."""
    try:
        issues_count = check_and_fix()
        return 0 if issues_count == 0 else 1
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
