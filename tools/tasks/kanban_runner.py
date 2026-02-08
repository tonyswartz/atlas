#!/usr/bin/env python3
"""Isolated Kanban runner.

Source of truth: Obsidian note `ClawdBot Kanban.md`.

Rules (per Tony, 2026-01-26):
- Only act on [To-Do] and [In Progress]. Never move Backlog -> To-Do automatically.
- If [In Progress] is non-empty: execute that task if it contains explicit executable steps; otherwise ask Tony to add steps.
- If [In Progress] is empty and [To-Do] has a new item:
  1) If clarification is needed, ask Tony first (Telegram), and edit the To-Do line to be clearer.
  2) Once clear, move it to [In Progress] while working.
  3) When done, move it to [Done].
- If no To-Dos: do nothing.

Automation scope:
- This runner can do safe, local automation for tasks it understands (e.g., local LLM/Ollama setup).
- For vague/high-level tasks, it will request clarification and wait.

No external messaging is performed unless explicitly requested by Tony (it is, for clarifying questions).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Source of truth: the Obsidian note Tony is viewing.
NOTE_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/ClawdBot Kanban.md")

# Legacy JSON path (kept only for backward compatibility; no longer required)
TASKS_PATH = Path('/Users/printer/clawd/kanban/tasks.json')
SYNC_SCRIPT = Path('/Users/printer/atlas/tools/tasks/sync_kanban_to_obsidian.py')
LOG_PATH = Path('/Users/printer/atlas/logs/kanban-runner.log')
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

TELEGRAM_TARGET = "8241581699"  # Tony

# [project] tasks (2+ char name starting with a letter) are owned by
# claude_task_runner.py — this runner skips them entirely.
_CLAUDE_TASK_RE = re.compile(r"^\[([a-zA-Z]\w+)\]\s+")

REQUIRED_MODELS = [
    'llama3.2:3b',
    'qwen2.5:7b',
]


def log(msg: str) -> None:
    ts = datetime.now().strftime('%y-%m-%d %H:%M:%S')
    LOG_PATH.open('a', encoding='utf-8').write(f'[{ts}] {msg}\n')


def sh(cmd: list[str], timeout: int | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return p.returncode, p.stdout


def notify_tony(text: str) -> None:
    """Best-effort Telegram message to Tony."""
    # Use CLI so this works from isolated cron sessions.
    cmd = [
        "clawdbot",
        "message",
        "send",
        "--channel",
        "telegram",
        "--target",
        TELEGRAM_TARGET,
        "--message",
        text,
    ]
    rc, out = sh(cmd, timeout=30)
    if rc != 0:
        log(f"notify_tony failed rc={rc}: {out[:300]}")


def parse_note() -> dict[str, list[str]]:
    """Parse ClawdBot Kanban.md into buckets of plain titles."""
    if not NOTE_PATH.exists():
        return {"todo": [], "in_progress": [], "backlog": [], "completed": []}

    text = NOTE_PATH.read_text(encoding="utf-8")
    buckets = {"todo": [], "in_progress": [], "backlog": [], "completed": []}
    current = None

    header_map = {
        "[to-do]": "todo",
        "[in progress]": "in_progress",
        "[backlog]": "backlog",
        "[done]": "completed",
    }

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key = header_map.get(line.lower())
        if key:
            current = key
            continue
        if current and line.startswith("-"):
            title = line[1:].strip()
            if title:
                buckets[current].append(title)

    return buckets


def write_note(buckets: dict[str, list[str]]) -> None:
    """Write buckets back to ClawdBot Kanban.md in the standard format."""
    def section(header: str, items: list[str]) -> str:
        lines = [header]
        if items:
            lines += [f"- {t}" for t in items]
        else:
            lines += ["- "]
        return "\n".join(lines)

    content = "\n\n".join([
        section("[To-Do]", buckets.get("todo", [])),
        section("[In Progress]", buckets.get("in_progress", [])),
        section("[Backlog]", buckets.get("backlog", [])),
        section("[Done]", buckets.get("completed", [])),
    ]) + "\n"

    NOTE_PATH.write_text(content, encoding="utf-8")


def load_tasks() -> tuple[list[dict], bool]:
    """Legacy: load tasks.json if present."""
    if not TASKS_PATH.exists():
        return [], True
    obj = json.loads(TASKS_PATH.read_text(encoding='utf-8'))
    if isinstance(obj, dict) and 'tasks' in obj:
        return obj['tasks'], True
    if isinstance(obj, list):
        return obj, False
    raise ValueError('Unrecognized tasks.json format')


def save_tasks(tasks: list[dict], wrapped: bool) -> None:
    """Legacy: write tasks.json (best-effort)."""
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if wrapped:
        obj = {"tasks": tasks}
        TASKS_PATH.write_text(json.dumps(obj, indent=2), encoding='utf-8')
    else:
        TASKS_PATH.write_text(json.dumps(tasks, indent=2), encoding='utf-8')


def get_bucket(tasks: list[dict], status: str) -> list[dict]:
    return [t for t in tasks if (t.get('status') or '').lower() == status]


def sort_key(t: dict):
    return (t.get('created') or '', t.get('id') or '')


def sync_obsidian() -> None:
    # NOTE_PATH is source-of-truth now; no sync needed.
    # Keep legacy sync script support if someone still uses tasks.json.
    if SYNC_SCRIPT.exists() and TASKS_PATH.exists():
        rc, out = sh([sys.executable, str(SYNC_SCRIPT)], timeout=60)
        if rc != 0:
            log(f'sync failed rc={rc}: {out[:500]}')
        else:
            log('synced kanban -> obsidian (legacy)')


def ollama_list() -> set[str]:
    rc, out = sh(['ollama', 'list'], timeout=30)
    if rc != 0:
        log(f'ollama list failed rc={rc}: {out[:300]}')
        return set()
    names = set()
    for line in out.splitlines()[1:]:
        parts = line.split()
        if parts:
            names.add(parts[0].strip())
    return names


def ollama_pull(model: str) -> None:
    # Fire-and-forget; ollama does its own locking.
    log(f'starting ollama pull {model}')
    subprocess.Popen(['ollama', 'pull', model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def clawdbot_models_list() -> str:
    rc, out = sh(['clawdbot', 'models', 'list'], timeout=30)
    if rc != 0:
        log(f'clawdbot models list failed rc={rc}: {out[:300]}')
        return ''
    return out


def ensure_clawdbot_ollama_config() -> None:
    """Best-effort: ensure Clawdbot can see local Ollama models.

    We do NOT attempt fancy JSON editing here; we just ensure OLLAMA_API_KEY exists
    and restart the gateway (safe, local) if models still show as missing.

    Note: user-approved to run `clawdbot config ...` and restart for todo/in_progress.
    """
    out = clawdbot_models_list()
    if not out:
        return

    # If Ollama models show up as available, we're good.
    if 'ollama/qwen2.5:7b' in out and 'missing' not in out:
        log('clawdbot sees ollama models (no missing)')
        return

    # Try setting env var in config (idempotent). This requires commands.config=true
    # in gateway, but the CLI can still write directly.
    log('ensuring clawdbot config has env.OLLAMA_API_KEY')
    sh(['clawdbot', 'config', 'set', 'env.OLLAMA_API_KEY', 'ollama-local'], timeout=60)

    # Restart gateway to reload config + providers.
    log('restarting gateway to pick up ollama config')
    sh(['clawdbot', 'gateway', 'restart'], timeout=120)


def ensure_local_llm() -> None:
    installed = ollama_list()
    missing = [m for m in REQUIRED_MODELS if m not in installed]
    if missing:
        # If any pull already running, don't start another.
        rc, out = sh(['bash', '-lc', "ps aux | grep -i '[o]llama pull' | wc -l"], timeout=10)
        pulling = int(out.strip() or '0')
        if pulling > 0:
            log(f'ollama pull already running; missing={missing}')
            return

        # Pull one at a time, prioritize llama3.2 then qwen2.5
        ollama_pull(missing[0])
        return

    log('ollama models present')
    ensure_clawdbot_ollama_config()


def needs_clarification(title: str) -> bool:
    t = title.strip().lower()
    # Heuristic: if it's a "review"/"optimize"/"make sure" style task with no explicit deliverable.
    vague_words = [
        "review ",
        "optimize",
        "make sure",
        "figure out",
        "clean up",
    ]
    # If it already contains an explicit deliverable marker, treat as clear.
    if any(x in t for x in ["deliverable:", "output:", "done when:", "steps:"]):
        return False
    return any(w in t for w in vague_words) and len(t.split()) > 4


def extract_run_steps(title: str) -> list[str]:
    """Extract [run] steps from a single-line task.

    Syntax supported inside the task title:
      ... [run] <command> ...
    Multiple steps can be separated by " | " or " ; ".

    Example:
      Review cron jobs... [run] clawdbot cron list | [run] clawdbot models aliases list
    """
    steps: list[str] = []
    # Split on separators but keep only segments starting with [run]
    parts = re.split(r"\s*(?:\||;)\s*", title)
    for p in parts:
        m = re.search(r"\[run\]\s*(.+)$", p.strip(), re.I)
        if m:
            cmd = m.group(1).strip()
            if cmd:
                steps.append(cmd)
    return steps


def is_allowed_command(cmd: str) -> bool:
    c = cmd.strip()
    allow_prefixes = [
        "clawdbot ",
        "python3 /Users/printer/clawd/scripts/",
        "python3 /Users/printer/atlas/tools/",
        "python3 -m ",
        "rg ",
        "sed ",
        "cat ",
        "ls ",
    ]
    return any(c.startswith(p) for p in allow_prefixes)


def is_approved(title: str) -> bool:
    return "[approved]" in title.lower() or "approved:" in title.lower()


def run_steps(title: str) -> tuple[bool, str]:
    """Run [run] steps; returns (all_ok, summary_text)."""
    steps = extract_run_steps(title)
    if not steps:
        return False, "No executable [run] steps found."

    ran: list[str] = []
    for cmd in steps:
        if not is_allowed_command(cmd):
            return False, f"Blocked command (not allowlisted): {cmd}"
        rc, out = sh(["bash", "-lc", cmd], timeout=180)
        ran.append(f"{cmd} (rc={rc})")
        if rc != 0:
            return False, f"Step failed: {cmd}\n{out[:400]}"

    return True, "Ran steps:\n- " + "\n- ".join(ran)


def main() -> int:
    buckets = parse_note()

    todo = buckets.get("todo", [])
    inprog = buckets.get("in_progress", [])

    # [project] tasks are handled by claude_task_runner; ignore them here.
    inprog = [t for t in inprog if not _CLAUDE_TASK_RE.match(t)]
    todo   = [t for t in todo   if not _CLAUDE_TASK_RE.match(t)]

    # If something is already in progress, try to execute it (if it has steps + is approved).
    if inprog:
        current = inprog[0]

        steps = extract_run_steps(current)
        if steps and not is_approved(current):
            notify_tony(
                "Kanban: I drafted/see executable steps for the current [In Progress] item, but I’m waiting for approval before I run them.\n\n"
                f"Current: {current}\n\n"
                "To approve: edit that same line in ClawdBot Kanban.md and add ` [approved]` at the end.\n"
                "(After approval, I’ll run the [run] steps on the next tick and move it to [Done].)"
            )
            log("in_progress has steps but not approved; waiting")
            return 0

        ok, summary = run_steps(current)
        if not ok:
            # If there are no steps, ask Tony to add them.
            if "No executable" in summary:
                notify_tony(
                    "Kanban: I’m ready to work the current [In Progress] item, but it needs explicit steps.\n\n"
                    f"Current: {current}\n\n"
                    "Add steps directly to that line using this syntax:\n"
                    "  [run] <command> | [run] <command>\n\n"
                    "Then add ` [approved]` when you want me to execute.\n\n"
                    "Example:\n"
                    "  Review cron jobs... [run] clawdbot cron list | [run] clawdbot cron list --json [approved]"
                )
                log("in_progress present but no steps; asked Tony to add [run] steps")
                return 0

            notify_tony(f"Kanban: hit an issue while executing [In Progress]:\n- {current}\n\n{summary}")
            log(f"in_progress execution failed: {summary}")
            return 0

        # Success: move to Done.
        buckets["in_progress"] = []
        buckets["completed"] = [current] + buckets.get("completed", [])
        write_note(buckets)
        notify_tony(f"Kanban: completed ✅\n- {current}\n\n{summary}")
        log(f"completed in_progress: {current}")
        return 0

    # Nothing to do.
    if not todo:
        log("no todo items")
        return 0

    first = todo[0]

    # If unclear, ask Tony and annotate the task line (but don't start it).
    if needs_clarification(first):
        annotated = f"{first} (clarify: scope + done-when + output; asked {datetime.now().strftime('%y-%m-%d')})"
        if annotated != first:
            buckets["todo"][0] = annotated
            write_note(buckets)

        notify_tony(
            "Kanban: I see a new ClawdBot To-Do that needs clarification before I start:\n"
            f"- {first}\n\n"
            "Reply here with:\n"
            "1) Scope (what to include/exclude)\n"
            "2) Done-when (how we know it’s complete)\n"
            "3) Output location (which note/file should be updated)\n\n"
            "Tip: you can edit the To-Do line in ClawdBot Kanban.md to include 'Done when:' and/or explicit [run] steps."
        )
        log(f"asked clarification for todo: {first}")
        return 0

    # Approval-gated execution:
    steps = extract_run_steps(first)
    if steps and not is_approved(first):
        notify_tony(
            "Kanban: I see executable [run] steps on the next To-Do, but I’m waiting for approval before I start.\n\n"
            f"Next: {first}\n\n"
            "To approve: edit that To-Do line and add ` [approved]`.\n"
            "After approval, I’ll move it to [In Progress] and run the steps on the next tick."
        )
        log("todo has steps but not approved; waiting")
        return 0

    if not steps:
        # Don't guess steps automatically; ask Tony to add them.
        notify_tony(
            "Kanban: Next To-Do is ready, but to run it automatically I need explicit steps.\n\n"
            f"Next: {first}\n\n"
            "Add steps to that same line using:\n"
            "  [run] <command> | [run] <command>\n\n"
            "Then add ` [approved]` when you want me to execute."
        )
        log("todo has no steps; asked Tony to add [run] steps")
        return 0

    # Otherwise: start it by moving to In Progress (already approved + has steps).
    todo.pop(0)
    buckets["todo"] = todo
    buckets["in_progress"] = [first]
    write_note(buckets)
    log(f"moved todo -> in_progress: {first}")
    notify_tony(f"Kanban: started (moved to In Progress):\n- {first}")

    # Mirror into legacy tasks.json (best-effort)
    tasks = []
    now = datetime.now().strftime('%y-%m-%d %H:%M:%S')
    for t in buckets.get('todo', []):
        tasks.append({"id": f"note:{hash(t)}", "title": t, "status": "todo", "created": now})
    for t in buckets.get('in_progress', []):
        tasks.append({"id": f"note:{hash(t)}", "title": t, "status": "in_progress", "created": now})
    for t in buckets.get('backlog', []):
        tasks.append({"id": f"note:{hash(t)}", "title": t, "status": "backlog", "created": now})
    for t in buckets.get('completed', []):
        tasks.append({"id": f"note:{hash(t)}", "title": t, "status": "completed", "created": now})
    save_tasks(tasks, wrapped=True)

    # Execute local-only actions for tasks that match known automation.
    t = first.lower()
    if 'local llm' in t or 'ollama' in t:
        ensure_local_llm()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
