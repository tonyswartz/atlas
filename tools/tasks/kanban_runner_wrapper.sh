#!/bin/bash
LOCKFILE=/tmp/kanban_runner.lock
LOGDIR=/Users/printer/atlas/logs
mkdir -p "$LOGDIR"
# Ensure cron can find flock and python3
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
exec 200>"$LOCKFILE"
flock -n 200 || exit 0
python3 /Users/printer/atlas/tools/tasks/kanban_runner.py
