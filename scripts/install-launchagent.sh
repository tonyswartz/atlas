#!/bin/bash
# Install Atlas Telegram bot LaunchAgent so it runs at login.
# Run from anywhere; script finds the Atlas repo root.

set -e
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PLIST_SRC="$REPO_ROOT/com.atlas.telegram-bot.plist"
DEST="$HOME/Library/LaunchAgents/com.atlas.telegram-bot.plist"

if [[ ! -f "$PLIST_SRC" ]]; then
  echo "ERROR: plist not found at $PLIST_SRC"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$DEST"
# Unload first if already loaded (avoids "Load failed: 5" on retry)
launchctl bootout "gui/$(id -u)" com.atlas.telegram-bot 2>/dev/null || true
# Load with bootstrap (required on macOS Ventura/Sonoma; load is deprecated)
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed and loaded. Atlas Telegram bot will start at login."
