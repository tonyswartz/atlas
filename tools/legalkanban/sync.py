#!/usr/bin/env python3
"""
Master LegalKanban sync script

Orchestrates bidirectional sync:
  1. Push local changes (completions, due dates) to LegalKanban
  2. Pull updated tasks from LegalKanban to local file
"""
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent


def run_script(script_name):
    """Run a sync script and return success status."""
    script_path = TOOLS_DIR / script_name
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    return result.returncode == 0


def main():
    """Run full bidirectional sync."""
    print("=" * 60)
    print("LegalKanban Daily Sync")
    print("=" * 60)
    print()

    # Step 1: Push local changes to remote
    print("STEP 1: Syncing local changes to LegalKanban...")
    print("-" * 60)
    if not run_script("sync_bidirectional.py"):
        print("ERROR: Failed to sync local changes", file=sys.stderr)
        sys.exit(1)

    print()

    # Step 2: Pull remote tasks to local
    print("STEP 2: Pulling tasks from LegalKanban...")
    print("-" * 60)
    if not run_script("sync_tasks.py"):
        print("ERROR: Failed to pull tasks", file=sys.stderr)
        sys.exit(1)

    print()
    print("=" * 60)
    print("✓ Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
