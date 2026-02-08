#!/usr/bin/env python3
"""Claude CLI task runner.

Reads [project] tasks from Atlas Tasks.md, runs them via ``claude -p``,
shows the diff, and waits for ``[approved]`` before committing.

Quota-aware: if Claude hits a rate-limit, persists a "waiting" state and
re-checks each poll until quota clears, then auto-resumes.

Task format in Kanban (user writes):
  [project] description

Runner adds the start date and moves to In Progress:
  [project] description [YY-MM-DD]

User approves commit by editing the In Progress line:
  [project] description [YY-MM-DD] [approved]

State: data/claude_task_state.json
Logs:  logs/claude_task_runner.log
Config: args/projects.yaml
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

import yaml  # PyYAML

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
REPO_ROOT     = Path(__file__).resolve().parent.parent.parent
KANBAN_PATH   = Path(
    "/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Atlas Tasks.md"
)
STATE_PATH    = REPO_ROOT / "data" / "claude_task_state.json"
LOG_PATH      = REPO_ROOT / "logs" / "claude_task_runner.log"
PROJECTS_YAML = REPO_ROOT / "args" / "projects.yaml"

CLAUDE_BIN    = "/Users/printer/.local/bin/claude"
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT   = "8241581699"

# Project name: 2+ chars starting with a letter — won't match [x] checkboxes
TASK_RE = re.compile(
    r"^\[([a-zA-Z]\w+)\]\s+"           # [project]
    r"(.+?)"                            # description (non-greedy)
    r"(?:\s+\[(\d{2}-\d{2}-\d{2})\])?"  # optional [YY-MM-DD]
    r"(?:\s+\[approved\])?$",           # optional [approved]
    re.IGNORECASE,
)
APPROVED_RE = re.compile(r"\[approved\]\s*$", re.IGNORECASE)

# Kanban section names — never treat these as project names
_KANBAN_SECTIONS = {"todo", "done", "backlog", "completed", "to-do", "in progress"}

# Indicators of a temporary API quota / rate-limit error
QUOTA_KEYWORDS = [
    "quota", "rate limit", "rate-limit", "429",
    "too many requests", "usage limit",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_PATH.open("a").write(f"[{ts}] {msg}\n")


def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN:
        log("No Telegram token configured")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "Markdown"
    }).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        log(f"Telegram send failed: {e}")
        return False


def load_projects() -> dict:
    if not PROJECTS_YAML.exists():
        log("projects.yaml not found")
        return {}
    with open(PROJECTS_YAML) as fh:
        return yaml.safe_load(fh) or {}


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            log("Corrupt state file; resetting")
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Kanban I/O  (mirrors kanban_runner format exactly)
# ---------------------------------------------------------------------------
_HEADER_MAP = {
    "[to-do]":      "todo",
    "[in progress]": "in_progress",
    "[backlog]":    "backlog",
    "[done]":       "completed",
}


def parse_kanban() -> dict[str, list[str]]:
    if not KANBAN_PATH.exists():
        return {"todo": [], "in_progress": [], "backlog": [], "completed": []}
    buckets: dict[str, list[str]] = {
        "todo": [], "in_progress": [], "backlog": [], "completed": []
    }
    current: str | None = None
    for raw in KANBAN_PATH.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        key = _HEADER_MAP.get(line.lower())
        if key:
            current = key
            continue
        if current and line.startswith("-"):
            title = line[1:].strip()
            if title:
                buckets[current].append(title)
    return buckets


def write_kanban(buckets: dict[str, list[str]]) -> None:
    def section(header: str, items: list[str]) -> str:
        lines = [header]
        lines += [f"- {t}" for t in items] if items else ["- "]
        return "\n".join(lines)

    content = "\n\n".join([
        section("[To-Do]",       buckets.get("todo", [])),
        section("[In Progress]", buckets.get("in_progress", [])),
        section("[Backlog]",     buckets.get("backlog", [])),
        section("[Done]",        buckets.get("completed", [])),
    ]) + "\n"
    KANBAN_PATH.write_text(content)


# ---------------------------------------------------------------------------
# Task parsing
# ---------------------------------------------------------------------------
def is_claude_task(title: str) -> bool:
    """True if title matches the [project] task pattern (excludes section names)."""
    m = TASK_RE.match(title.strip())
    return bool(m) and m.group(1).lower() not in _KANBAN_SECTIONS


def parse_task(title: str) -> dict | None:
    m = TASK_RE.match(title.strip())
    if not m:
        return None
    project = m.group(1).lower()
    if project in _KANBAN_SECTIONS:
        return None
    return {
        "project":     project,
        "description": m.group(2).strip(),
        "date":        m.group(3),               # None if not yet stamped
        "approved":    bool(APPROVED_RE.search(title)),
        "raw":         title.strip(),
    }


# ---------------------------------------------------------------------------
# Claude invocation & quota probing
# ---------------------------------------------------------------------------
def is_quota_error(output: str) -> bool:
    lower = output.lower()
    return any(kw in lower for kw in QUOTA_KEYWORDS)


def test_quota_cleared() -> bool:
    """Lightweight probe: one-shot prompt with $0.01 cap to see if API is available."""
    try:
        p = subprocess.run(
            [CLAUDE_BIN, "-p", "--permission-mode", "dontAsk",
             "--max-budget-usd", "0.01", "say: OK"],
            capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
        )
        return not is_quota_error(p.stdout + p.stderr)
    except (subprocess.TimeoutExpired, Exception) as exc:
        log(f"quota probe failed: {exc}")
        return False


def run_claude(project_path: str, description: str, budget: float) -> tuple[int, str]:
    """Invoke claude -p. Returns (exit_code, combined output)."""
    prompt = (
        f"Your task: {description}\n\n"
        "Implement the requested changes. Do not commit — changes will be reviewed separately."
    )
    cmd = [
        CLAUDE_BIN, "-p",
        "--permission-mode", "dontAsk",
        "--disallowed-tools", "Bash(git:*)",
        "--max-budget-usd", str(budget),
        prompt,
    ]
    log(f"claude invocation in {project_path}")
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, cwd=project_path, timeout=600
        )
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return -1, "Claude timed out after 10 min"
    except Exception as exc:
        return -1, str(exc)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------
def git_diff_stat(project_path: str) -> str:
    try:
        p = subprocess.run(
            ["git", "diff", "--stat", "--no-color"],
            capture_output=True, text=True, cwd=project_path, timeout=10,
        )
        return p.stdout.strip() or "(no changes)"
    except Exception:
        return "(diff unavailable)"


def git_status_files(project_path: str) -> list[str]:
    """All changed / untracked files via git status --porcelain."""
    try:
        p = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=project_path, timeout=10,
        )
        return [line[3:].strip() for line in p.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def commit_changes(project_path: str, description: str) -> tuple[bool, str]:
    """Stage changed files (not blanket git add .) and commit."""
    files = git_status_files(project_path)
    if not files:
        return False, "Nothing to commit"
    try:
        subprocess.run(
            ["git", "add"] + files,
            cwd=project_path, check=True, capture_output=True, text=True, timeout=10,
        )
        msg = (
            f"{description}\n\n"
            "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
        )
        p = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=project_path, capture_output=True, text=True, timeout=10,
        )
        return p.returncode == 0, (p.stdout or p.stderr).strip()
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Core flow
# ---------------------------------------------------------------------------
def handle_run(project_path: str, task: dict, budget: float, state: dict) -> None:
    """Run Claude on a task, then park state for the next phase."""
    rc, output = run_claude(project_path, task["description"], budget)

    # --- Temporary rate-limit → auto-resume later ---
    if rc != 0 and is_quota_error(output):
        state["status"] = "waiting"
        state["quota_wait_since"] = datetime.now().isoformat()
        save_state(state)
        send_telegram(f"⏳ *{task['project']}* — rate-limited\nWill auto-resume when quota clears.")
        log(f"quota hit for {task['project']}")
        return

    # Even on non-zero exit there may be partial work on disk; check for it.
    diff = git_diff_stat(project_path)
    has_changes = diff != "(no changes)"

    if rc != 0 and not has_changes:
        # Clean error, nothing salvageable.
        state["status"] = "error"
        state["error_output"] = output[-500:]
        save_state(state)
        send_telegram(
            f"🔴 *{task['project']}* — claude exited {rc}\n"
            f"```\n{output[-400:]}\n```"
        )
        log(f"claude rc={rc}, no changes, for {task['project']}")
        return

    # Success (or partial work worth reviewing).
    state["status"] = "pending_approval"
    state.pop("quota_wait_since", None)
    state.pop("error_output", None)
    save_state(state)

    prefix = "🟡" if rc != 0 else "🔵"
    note   = f" (partial — exit {rc})" if rc != 0 else ""
    send_telegram(
        f"{prefix} *{task['project']}*{note} — ready for review\n"
        f"Edit the In Progress line and add `[approved]` to commit.\n\n"
        f"```\n{diff[:2000]}\n```"
    )
    log(f"pending approval: {task['project']} — {task['description']}")


def main() -> int:
    config   = load_projects()
    projects = config.get("projects", {})
    defaults = config.get("defaults", {})

    state   = load_state()
    buckets = parse_kanban()

    # ── Quota recovery ────────────────────────────────────────────────────
    if state.get("status") == "waiting":
        if not test_quota_cleared():
            log("still rate-limited")
            return 0
        log("quota cleared — resuming")
        task        = state.get("task", {})
        proj_name   = task.get("project", "")
        project_cfg = projects.get(proj_name)
        if not project_cfg:
            log(f"project {proj_name} missing from config during resume")
            return 1
        send_telegram(f"🔄 *{proj_name}* — quota cleared, resuming")
        state["status"] = "running"
        save_state(state)
        handle_run(
            project_cfg["path"], task,
            project_cfg.get("budget_usd", defaults.get("budget_usd", 2.0)),
            state,
        )
        return 0

    # ── Pending approval (commit gate) ───────────────────────────────────
    if state.get("status") == "pending_approval":
        task      = state.get("task", {})
        proj_name = task.get("project", "")

        for line in buckets.get("in_progress", []):
            parsed = parse_task(line)
            if parsed and parsed["project"] == proj_name and parsed["approved"]:
                project_cfg = projects.get(proj_name)
                if not project_cfg:
                    log(f"project {proj_name} missing")
                    return 1
                ok, result = commit_changes(project_cfg["path"], task["description"])
                if ok:
                    buckets["in_progress"].remove(line)
                    buckets["completed"].insert(0, line)
                    write_kanban(buckets)
                    save_state({})
                    send_telegram(f"✅ *{proj_name}* — committed\n{result}")
                    log(f"committed: {proj_name}")
                else:
                    send_telegram(f"🔴 *{proj_name}* — commit failed\n```\n{result}\n```")
                    log(f"commit failed: {result}")
                return 0

        # If the task disappeared from In Progress entirely, user cancelled.
        still_there = any(
            (parse_task(ln) or {}).get("project") == proj_name
            for ln in buckets.get("in_progress", [])
        )
        if not still_there:
            log(f"task {proj_name} removed from In Progress; clearing state")
            save_state({})
        else:
            log("waiting for approval")
        return 0

    # ── Error state — wait for user to clear (remove from In Progress) ───
    if state.get("status") == "error":
        task      = state.get("task", {})
        proj_name = task.get("project", "")
        still_there = any(
            (parse_task(ln) or {}).get("project") == proj_name
            for ln in buckets.get("in_progress", [])
        )
        if not still_there:
            log(f"error state cleared — task removed for {proj_name}")
            save_state({})
        else:
            log("in error state; waiting for user")
        return 0

    # ── Already running (shouldn't happen across polls, but guard) ────────
    if state.get("status") == "running":
        log("task already marked running; possible stale state")
        return 0

    # ── Pick up new [project] task from To-Do ─────────────────────────────
    claude_line = None
    for line in buckets.get("todo", []):
        if is_claude_task(line):
            claude_line = line
            break

    if not claude_line:
        return 0

    parsed = parse_task(claude_line)
    if not parsed:
        return 0

    proj_name   = parsed["project"]
    project_cfg = projects.get(proj_name)
    if not project_cfg:
        send_telegram(f"🔴 Unknown project: `{proj_name}`\nAdd it to `args/projects.yaml`")
        log(f"unknown project: {proj_name}")
        return 1

    project_path = project_cfg["path"]

    # Sanity checks on project path
    if not Path(project_path).is_dir():
        send_telegram(f"🔴 *{proj_name}* — path doesn't exist: `{project_path}`")
        log(f"project path missing: {project_path}")
        return 1
    if not (Path(project_path) / ".git").is_dir():
        send_telegram(f"🔴 *{proj_name}* — not a git repo: `{project_path}`")
        log(f"not a git repo: {project_path}")
        return 1

    # Stamp date and move To-Do → In Progress
    date_str = datetime.now().strftime("%y-%m-%d")
    new_line = claude_line if parsed["date"] else f"{claude_line} [{date_str}]"

    buckets["todo"].remove(claude_line)
    buckets["in_progress"].insert(0, new_line)
    write_kanban(buckets)

    task = {
        "project":     proj_name,
        "description": parsed["description"],
        "date":        parsed["date"] or date_str,
        "raw":         new_line,
    }
    budget = project_cfg.get("budget_usd", defaults.get("budget_usd", 2.0))

    state = {
        "status":     "running",
        "task":       task,
        "started_at": datetime.now().isoformat(),
    }
    save_state(state)

    send_telegram(f"🟡 *{proj_name}* — {parsed['description']}\nBudget: ${budget}")
    log(f"starting: {proj_name} — {parsed['description']}")

    handle_run(project_path, task, budget, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
