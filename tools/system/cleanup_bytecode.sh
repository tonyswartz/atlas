#!/bin/bash
# Daily bytecode cache cleanup
# Runs at 5:55am daily to ensure fresh Python imports

REPO_ROOT="/Users/printer/atlas"

# Delete all __pycache__ directories and .pyc files
find "$REPO_ROOT" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$REPO_ROOT" -name '*.pyc' -delete 2>/dev/null || true

# Log completion (optional, for verification)
echo "$(date '+%Y-%m-%d %H:%M:%S') - Cleaned Python bytecode cache" >> "$REPO_ROOT/logs/bytecode_cleanup.log"
