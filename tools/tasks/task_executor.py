#!/usr/bin/env python3
"""Task Executor - Polls JeevesUI for approved tasks and executes them via Claude CLI.

Runs every 5 minutes via cron.
Picks up APPROVED tasks, runs them, reports progress and results.

Usage: python3 tools/tasks/task_executor.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
JEEVESUI_URL = "http://localhost:6001"
CLAUDE_BIN = Path.home() / ".local/bin/claude"
STATE_FILE = REPO_ROOT / "data/task_executor_state.json"
LOG_FILE = REPO_ROOT / "logs/task_executor.log"

# Load .env for credentials
_DOT_ENV = REPO_ROOT / ".env"
if _DOT_ENV.exists():
    for line in _DOT_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = "8241581699"


def log(msg: str) -> None:
    """Log with timestamp."""
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line.rstrip())
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line)


def api_request(method: str, endpoint: str, data: dict = None) -> dict | None:
    """Make API request to JeevesUI."""
    try:
        url = f"{JEEVESUI_URL}{endpoint}"
        if data:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                method=method,
            )
        else:
            req = urllib.request.Request(url, method=method)

        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log(f"API request failed: {method} {endpoint} - {e}")
        return None


def send_telegram(message: str) -> None:
    """Send Telegram notification."""
    if not TELEGRAM_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        log(f"Failed to send Telegram: {e}")


def get_approved_tasks() -> list:
    """Fetch tasks with status=APPROVED."""
    result = api_request("GET", "/api/tasks?status=APPROVED&limit=10")
    if result and "tasks" in result:
        return result["tasks"]
    return []


def update_task_status(task_id: str, status: str, **kwargs) -> None:
    """Update task status and optional fields."""
    data = {"status": status, **kwargs}
    api_request("PATCH", f"/api/tasks/{task_id}", data)


def add_task_update(task_id: str, message: str, metadata: dict = None) -> None:
    """Add progress update to task."""
    data = {"message": message, "metadata": metadata}
    api_request("POST", f"/api/tasks/{task_id}/updates", data)


def execute_task(task: dict) -> dict:
    """Execute task using Claude CLI."""
    task_id = task["id"]
    title = task["title"]
    project = task["project"]
    budget = task["budgetUsd"]

    log(f"Executing task #{task_id[:8]}: {title}")

    # Update status to RUNNING
    update_task_status(task_id, "RUNNING")
    add_task_update(task_id, "Task started - executing via Claude CLI")
    send_telegram(f"⚡ *Task Started*\n\n#{task_id[:8]}: {title}\nBudget: ${budget:.2f}")

    # Determine working directory
    project_paths = {
        "atlas": str(REPO_ROOT),
        "jeevesui": "/Users/printer/clawd/JeevesUI",
    }
    work_dir = project_paths.get(project, str(REPO_ROOT))

    if not Path(work_dir).exists():
        error_msg = f"Project directory not found: {work_dir}"
        log(f"ERROR: {error_msg}")
        update_task_status(
            task_id,
            "FAILED",
            exitCode=1,
            errorMessage=error_msg,
            spentUsd=0,
        )
        return {"success": False, "error": error_msg}

    # Build Claude command
    prompt = task.get("description") or title
    cmd = [
        str(CLAUDE_BIN),
        "-p",  # Non-interactive
        "--permission-mode", "dontAsk",  # Auto-approve all
        "--disallowed-tools", "Bash(git:push*)",  # Block git push
        "--max-budget-usd", str(budget),
        prompt,
    ]

    log(f"Running: {' '.join(cmd)}")
    log(f"Working directory: {work_dir}")

    try:
        start_time = time.time()
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout
        )
        duration = time.time() - start_time

        output = result.stdout
        error_output = result.stderr
        exit_code = result.returncode

        log(f"Task completed with exit code: {exit_code}")
        log(f"Duration: {duration:.1f}s")

        # Parse output for cost (simple heuristic)
        spent = 0.0
        for line in (output + error_output).split("\n"):
            if "$" in line and "spent" in line.lower():
                try:
                    # Try to extract dollar amount
                    import re
                    match = re.search(r'\$(\d+\.?\d*)', line)
                    if match:
                        spent = float(match.group(1))
                except:
                    pass

        # Determine success
        success = exit_code == 0

        # Update task with results
        if success:
            summary = output[:500] + ("..." if len(output) > 500 else "")
            update_task_status(
                task_id,
                "COMPLETED",
                exitCode=exit_code,
                outputSummary=summary,
                outputFull=output[:10000],  # Limit full output
                spentUsd=spent,
            )
            send_telegram(
                f"✅ *Task Complete!*\n\n"
                f"#{task_id[:8]}: {title}\n"
                f"Cost: ${spent:.2f} / ${budget:.2f}\n"
                f"Duration: {duration:.0f}s"
            )
        else:
            error_msg = error_output[:500] + ("..." if len(error_output) > 500 else "")
            update_task_status(
                task_id,
                "FAILED",
                exitCode=exit_code,
                errorMessage=error_msg,
                outputFull=(output + "\n\n" + error_output)[:10000],
                spentUsd=spent,
            )
            send_telegram(
                f"❌ *Task Failed*\n\n"
                f"#{task_id[:8]}: {title}\n"
                f"Exit code: {exit_code}\n"
                f"Error: {error_msg[:200]}"
            )

        return {
            "success": success,
            "exit_code": exit_code,
            "spent": spent,
            "duration": duration,
        }

    except subprocess.TimeoutExpired:
        log("ERROR: Task timed out after 30 minutes")
        update_task_status(
            task_id,
            "FAILED",
            exitCode=124,
            errorMessage="Task timed out after 30 minutes",
            spentUsd=budget,  # Assume full budget spent on timeout
        )
        send_telegram(f"⏱️ *Task Timeout*\n\n#{task_id[:8]}: {title}\nExceeded 30 minute limit")
        return {"success": False, "error": "timeout"}

    except Exception as e:
        log(f"ERROR: Task execution failed: {e}")
        update_task_status(
            task_id,
            "FAILED",
            exitCode=1,
            errorMessage=str(e),
            spentUsd=0,
        )
        send_telegram(f"❌ *Task Error*\n\n#{task_id[:8]}: {title}\n{str(e)}")
        return {"success": False, "error": str(e)}


def main() -> int:
    """Main execution loop."""
    log("Task executor starting...")

    # Get approved tasks
    tasks = get_approved_tasks()

    if not tasks:
        log("No approved tasks found")
        return 0

    log(f"Found {len(tasks)} approved task(s)")

    # Execute each task sequentially
    for task in tasks:
        try:
            execute_task(task)
            time.sleep(2)  # Brief pause between tasks
        except Exception as e:
            log(f"Unexpected error executing task: {e}")

    log("Task executor finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
