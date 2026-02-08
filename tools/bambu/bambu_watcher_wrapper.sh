#!/bin/bash
LOCKFILE=/tmp/bambu_watcher.lock
# Create directory for logs if missing
LOGDIR=/Users/printer/atlas/logs
mkdir -p "$LOGDIR"
# Ensure cron can find Homebrew binaries
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
exec 200>"$LOCKFILE"
# Try to acquire non-blocking lock; exit gracefully if already running
/opt/homebrew/bin/flock -n 200 || exit 0
# Run the watcher
python3 /Users/printer/atlas/tools/bambu/bambu_watcher.py
# If any pending prompts exist, send spool prompt
python3 /Users/printer/atlas/tools/bambu/bambu_prompt_poller.py
# Process any pending reply to a spool prompt
python3 /Users/printer/atlas/tools/bambu/bambu_reply_handler.py
