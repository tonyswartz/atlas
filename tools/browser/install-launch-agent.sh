#!/usr/bin/env bash
# Install the browser server as a LaunchAgent so it runs at login.
# Run from the atlas repo root: bash tools/browser/install-launch-agent.sh

set -e
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$REPO_ROOT/tools/browser/com.atlas.browser-server.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.atlas.browser-server.plist"
LOG_DIR="$REPO_ROOT/memory/logs"

mkdir -p "$LOG_DIR"
PYTHON_PATH="$(command -v python3)"
sed -e "s|REPO_ROOT|$REPO_ROOT|g" -e "s|PYTHON_PATH|$PYTHON_PATH|g" "$PLIST_SRC" > "$PLIST_DEST"
echo "Installed $PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "Loaded. Browser server will run at login and is starting now."
echo "Logs: $LOG_DIR/browser-server.log"
