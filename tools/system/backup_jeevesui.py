#!/usr/bin/env python3
"""Backup JeevesUI directory daily.

Creates compressed backups of JeevesUI and rotates old backups.
Run via cron at 3 AM daily.

Usage: python3 tools/system/backup_jeevesui.py
"""

import shutil
import sys
from pathlib import Path
from datetime import datetime

JEEVESUI_PATH = Path("/Users/printer/clawd/JeevesUI")
BACKUP_DIR = Path("/Users/printer/atlas/backups/jeevesui")
KEEP_DAYS = 7

def log(msg: str) -> None:
    """Log with timestamp."""
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def backup() -> int:
    """Create backup of JeevesUI directory."""
    if not JEEVESUI_PATH.exists():
        log("❌ JeevesUI not found at expected path")
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    backup_name = f"jeevesui-{timestamp}"
    backup_path = BACKUP_DIR / backup_name

    try:
        log(f"Creating backup: {backup_name}.tar.gz")
        shutil.make_archive(
            str(backup_path),
            "gztar",
            JEEVESUI_PATH.parent,
            "JeevesUI",
            # Exclude node_modules and .git to save space
        )

        # Get backup size
        backup_file = Path(f"{backup_path}.tar.gz")
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        log(f"✅ Backup created: {backup_file.name} ({size_mb:.1f} MB)")

    except Exception as e:
        log(f"❌ Backup failed: {e}")
        return 1

    # Clean old backups
    try:
        backups = sorted(BACKUP_DIR.glob("jeevesui-*.tar.gz"))
        if len(backups) > KEEP_DAYS:
            for old_backup in backups[:-KEEP_DAYS]:
                old_backup.unlink()
                log(f"🗑️  Removed old backup: {old_backup.name}")

        log(f"📦 Total backups: {len(backups[:KEEP_DAYS])}")

    except Exception as e:
        log(f"⚠️ Failed to clean old backups: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(backup())
