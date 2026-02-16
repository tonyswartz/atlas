#!/usr/bin/env python3
"""
Git sync and conditional bot restart.

Runs at midnight (via launchd) to:
  - git fetch, pull (merge), and push so the repo is synced with GitHub
  - Restart the Telegram bot (and thus use updated code) only if the bot is not busy
  - If the bot is busy, set a pending-restart flag; a separate launchd job runs every 10 min
    and restarts the bot when it becomes idle.

Busy = data/bot_busy_since exists and was touched in the last IDLE_MINUTES.
Pending = data/pending_restart_after_sync exists (sync ran but skipped restart due to busy).

Usage:
  python tools/system/git_sync_and_restart.py           # Full sync at midnight + restart or set pending
  python tools/system/git_sync_and_restart.py --deferred-only   # Only run deferred restart if pending + idle
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Repo root (script lives in tools/system/)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = REPO_ROOT / "data"
BOT_BUSY_FILE = DATA / "bot_busy_since"
PENDING_RESTART_FILE = DATA / "pending_restart_after_sync"
TELEGRAM_BOT_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.atlas.telegram-bot.plist"

# Consider bot idle if busy file is older than this (minutes)
IDLE_MINUTES = 10


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{ts}] {msg}", flush=True)


def is_bot_busy() -> bool:
    """True if bot is currently handling a message (busy file exists and recent)."""
    if not BOT_BUSY_FILE.exists():
        return False
    try:
        mtime = BOT_BUSY_FILE.stat().st_mtime
        return (time.time() - mtime) < (IDLE_MINUTES * 60)
    except OSError:
        return False


def do_restart_bot() -> bool:
    """Unload and load the Telegram bot LaunchAgent. Returns True on success."""
    if not TELEGRAM_BOT_PLIST.exists():
        log(f"Plist not found: {TELEGRAM_BOT_PLIST}")
        return False
    try:
        subprocess.run(
            ["launchctl", "unload", str(TELEGRAM_BOT_PLIST)],
            capture_output=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        time.sleep(1)
        subprocess.run(
            ["launchctl", "load", str(TELEGRAM_BOT_PLIST)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        log("Telegram bot restarted (launchctl unload/load).")
        return True
    except Exception as e:
        log(f"Restart failed: {e}")
        return False


def run_git_sync() -> bool:
    """Fetch, pull (merge), and push. Returns True if sync succeeded (no merge conflict)."""
    try:
        r = subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
        )
        if r.returncode != 0:
            log(f"git fetch failed: {r.stderr or r.stdout}")
            return False

        r = subprocess.run(
            ["git", "pull", "origin", "--no-rebase"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
        )
        if r.returncode != 0:
            log(f"git pull failed: {r.stderr or r.stdout}")
            return False

        # Push if we have local commits to push
        r = subprocess.run(
            ["git", "status", "-sb"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=REPO_ROOT,
        )
        if r.returncode == 0 and "ahead" in r.stdout:
            r2 = subprocess.run(
                ["git", "push", "origin"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=REPO_ROOT,
            )
            if r2.returncode != 0:
                log(f"git push failed: {r2.stderr or r2.stdout}")
            else:
                log("git push completed.")
        return True
    except subprocess.TimeoutExpired:
        log("git command timed out")
        return False
    except Exception as e:
        log(f"Sync error: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Git sync and conditional bot restart")
    parser.add_argument(
        "--deferred-only",
        action="store_true",
        help="Only run deferred restart: if pending and bot idle, restart and clear pending",
    )
    args = parser.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)

    if args.deferred_only:
        if not PENDING_RESTART_FILE.exists():
            return 0
        if is_bot_busy():
            return 0
        if do_restart_bot():
            try:
                PENDING_RESTART_FILE.unlink()
            except OSError:
                pass
        return 0

    # Full run: sync then restart or set pending
    if not run_git_sync():
        return 1

    if is_bot_busy():
        try:
            PENDING_RESTART_FILE.touch()
            log("Bot busy — set pending_restart_after_sync; will restart when idle.")
        except OSError:
            pass
        return 0

    do_restart_bot()
    if PENDING_RESTART_FILE.exists():
        try:
            PENDING_RESTART_FILE.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
