#!/usr/bin/env bash
# Run a command with Atlas env vars from Apple Keychain (envchain).
# Usage: ./scripts/run_with_envchain.sh python tools/telegram/bot.py
#        ./scripts/run_with_envchain.sh bash -c "python tools/briefings/daily_brief.py"
# Requires: brew install envchain, and envchain --set atlas VAR1 VAR2 ... (see docs/ENVCHAIN.md)

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
exec /opt/homebrew/bin/envchain atlas "$@"
