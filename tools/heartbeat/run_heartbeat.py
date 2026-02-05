#!/usr/bin/env python3
"""Run heartbeat checklist. Reads HEARTBEAT.md and heartbeat-state.json; prints a short status.

Use via: python3 tools/heartbeat/run_heartbeat.py (from repo root).
Output is one line: HEARTBEAT_OK or a brief summary. Cron or the Telegram run_tool can call this.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HEARTBEAT_MD = REPO_ROOT / "HEARTBEAT.md"
STATE_JSON = REPO_ROOT / "memory" / "heartbeat-state.json"


def main() -> None:
    if not HEARTBEAT_MD.exists():
        print("HEARTBEAT_OK")
        return

    lines = HEARTBEAT_MD.read_text(encoding="utf-8").strip().splitlines()
    checklist = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]

    state = {}
    if STATE_JSON.exists():
        try:
            state = json.loads(STATE_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    if not checklist:
        print("HEARTBEAT_OK")
        return

    # For now just report OK; state can be updated when we add real checks (email, calendar, etc.)
    print("HEARTBEAT_OK")


if __name__ == "__main__":
    main()
