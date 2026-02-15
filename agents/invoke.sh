#!/bin/bash
# Quick wrapper for agent invocation
# Usage:
#   ./agents/invoke.sh telegram "Fix bot tool loop"
#   ./agents/invoke.sh --list
#   ./agents/invoke.sh --help

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Route to router.py
exec /opt/homebrew/bin/python3 "$REPO_ROOT/router.py" "$@"
