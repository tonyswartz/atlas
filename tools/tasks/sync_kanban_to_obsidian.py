#!/usr/bin/env python3
"""Sync /Users/printer/clawd/kanban/tasks.json -> Obsidian note "ClawdBot Kanban.md".

- Uses simple sections: [To-Do] [In Progress] [Backlog] [Done]
- Writes bullet lists under each section.

This is intentionally dumb and deterministic: tasks.json is the source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

TASKS_PATH = Path("/Users/printer/clawd/kanban/tasks.json")
NOTE_PATH = Path(
    "/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/ClawdBot Kanban.md"
)

SECTION_ORDER = [
    ("todo", "[To-Do]"),
    ("in_progress", "[In Progress]"),
    ("backlog", "[Backlog]"),
    ("completed", "[Done]"),
]


def load_tasks() -> list[dict]:
    obj = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if isinstance(obj, dict) and "tasks" in obj:
        return obj["tasks"]
    if isinstance(obj, list):
        return obj
    raise ValueError("Unrecognized tasks.json format")


def norm_status(s: str | None) -> str:
    s = (s or "").strip().lower()
    if s in {"done", "complete"}:
        return "completed"
    if s in {"in progress", "in-progress"}:
        return "in_progress"
    return s


def main() -> int:
    tasks = load_tasks()

    buckets: dict[str, list[dict]] = {k: [] for k, _ in SECTION_ORDER}
    other: list[dict] = []

    for t in tasks:
        st = norm_status(t.get("status"))
        if st in buckets:
            buckets[st].append(t)
        else:
            other.append(t)

    # stable ordering: oldest first within each bucket
    def sort_key(t: dict):
        return (t.get("created") or "", t.get("id") or "")

    for k in buckets:
        buckets[k].sort(key=sort_key)

    lines: list[str] = []
    for key, header in SECTION_ORDER:
        lines.append(header)
        if buckets[key]:
            for t in buckets[key]:
                title = (t.get("title") or "(untitled)").strip()
                lines.append(f"- {title}")
        else:
            lines.append("- ")
        lines.append("")

    if other:
        lines.append("[Other]")
        for t in other:
            title = (t.get("title") or "(untitled)").strip()
            st = t.get("status")
            lines.append(f"- {title} ({st})")
        lines.append("")

    NOTE_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
