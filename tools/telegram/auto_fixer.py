#!/usr/bin/env python3
"""
Autonomous Code Repair System

Uses MiniMax to diagnose and fix failing Telegram bot tools automatically.
Triggered by bot_health_monitor when same tool fails repeatedly.

Safety features:
- Creates backup before modifying code
- Validates syntax after applying fix
- Detailed logging of all changes
- Rollback capability if fix fails
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.common.credentials import get_credential

TZ = ZoneInfo("America/Los_Angeles")
TOOLS_DIR = REPO_ROOT / "tools" / "telegram"
BACKUPS_DIR = REPO_ROOT / "data" / "backups"
LOG_FILE = REPO_ROOT / "logs" / "auto_fixer.log"

# MiniMax API configuration
MINIMAX_BASE_URL = "https://api.minimax.io/v1"
MINIMAX_MODEL = "MiniMax-M2.5"


def log(message: str):
    """Log to file and stdout."""
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)

    try:
        LOG_FILE.parent.mkdir(exist_ok=True, parents=True)
        with open(LOG_FILE, "a") as f:
            f.write(log_message + "\n")
    except Exception as e:
        print(f"Failed to write log: {e}")


def get_minimax_api_key() -> str:
    """Get MiniMax API key from envchain."""
    # Note: envchain key is misspelled "MINIMIAX_CODING"
    key = get_credential("MINIMIAX_CODING")
    if not key:
        raise ValueError("MINIMIAX_CODING API key not found")
    return key


def call_minimax(prompt: str) -> str:
    """Call MiniMax API for code analysis and repair."""
    import urllib.request

    api_key = get_minimax_api_key()

    url = f"{MINIMAX_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = json.dumps({
        "model": MINIMAX_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,  # Low temperature for deterministic fixes
        "max_tokens": 4000
    })

    req = urllib.request.Request(url, data=payload.encode(), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())

            # Extract response content
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Strip <think> tags if present
            if "<think>" in content and "</think>" in content:
                content = content.split("</think>", 1)[1].strip()

            return content
    except Exception as e:
        log(f"ERROR: MiniMax API call failed: {e}")
        raise


def create_backup(file_path: Path) -> Path:
    """Create timestamped backup of file before modification."""
    BACKUPS_DIR.mkdir(exist_ok=True, parents=True)

    timestamp = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{file_path.stem}_backup_{timestamp}{file_path.suffix}"
    backup_path = BACKUPS_DIR / backup_name

    backup_path.write_text(file_path.read_text())
    log(f"✓ Created backup: {backup_path}")

    return backup_path


def validate_python_syntax(file_path: Path) -> bool:
    """Validate Python file syntax."""
    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        log(f"ERROR: Syntax validation failed: {e}")
        return False


def fix_tool(tool_name: str, failures: list[dict]) -> dict:
    """
    Diagnose and fix a failing tool using MiniMax.

    Args:
        tool_name: Name of the tool (e.g., "rotary_read_agenda")
        failures: List of recent failures with timestamps, errors, context

    Returns:
        {
            "success": bool,
            "tool_name": str,
            "backup_path": str or None,
            "changes_summary": str,
            "fix_applied": bool
        }
    """
    log(f"🔧 Starting auto-fix for tool: {tool_name}")
    log(f"Failure count: {len(failures)}")

    result = {
        "success": False,
        "tool_name": tool_name,
        "backup_path": None,
        "changes_summary": "",
        "fix_applied": False
    }

    # Find tool file
    tool_file = TOOLS_DIR / f"{tool_name}.py"
    if not tool_file.exists():
        # Try tool_runner.py (for tools defined there)
        tool_file = TOOLS_DIR / "tool_runner.py"
        if not tool_file.exists():
            log(f"ERROR: Tool file not found: {tool_name}")
            result["changes_summary"] = "Tool file not found"
            return result

    # Read current code
    try:
        current_code = tool_file.read_text()
    except Exception as e:
        log(f"ERROR: Failed to read tool file: {e}")
        result["changes_summary"] = f"Failed to read file: {e}"
        return result

    # Build diagnostic prompt for MiniMax
    failure_summaries = []
    for f in failures[-5:]:  # Last 5 failures
        failure_summaries.append(
            f"Timestamp: {f.get('timestamp', 'unknown')}\n"
            f"Error: {f.get('error', 'No error message')}\n"
            f"Context: {f.get('context', 'No context')}"
        )

    prompt = f"""You are debugging a Python tool in a Telegram bot that has failed {len(failures)} times.

**Tool Name:** {tool_name}

**Recent Failures:**
{chr(10).join(failure_summaries)}

**Current Code:**
```python
{current_code}
```

**Task:**
1. Identify the root cause of the failures
2. Propose a minimal fix that resolves the issue
3. Return ONLY the complete fixed code (no explanations before or after)
4. Ensure the fix:
   - Handles edge cases that caused failures
   - Maintains existing functionality
   - Uses proper error handling
   - Follows existing code style

Return the full corrected Python code, nothing else."""

    # Call MiniMax for diagnosis and fix
    try:
        fixed_code = call_minimax(prompt)

        # Remove markdown code fences if present
        if "```python" in fixed_code:
            fixed_code = fixed_code.split("```python", 1)[1]
            fixed_code = fixed_code.split("```", 1)[0]
        elif "```" in fixed_code:
            fixed_code = fixed_code.split("```", 1)[1]
            fixed_code = fixed_code.split("```", 1)[0]

        fixed_code = fixed_code.strip()

    except Exception as e:
        log(f"ERROR: MiniMax diagnosis failed: {e}")
        result["changes_summary"] = f"MiniMax API error: {e}"
        return result

    # Create backup
    try:
        backup_path = create_backup(tool_file)
        result["backup_path"] = str(backup_path)
    except Exception as e:
        log(f"ERROR: Failed to create backup: {e}")
        result["changes_summary"] = f"Backup failed: {e}"
        return result

    # Apply fix
    try:
        tool_file.write_text(fixed_code)
        log(f"✓ Applied fix to {tool_file}")
    except Exception as e:
        log(f"ERROR: Failed to write fixed code: {e}")
        result["changes_summary"] = f"Write failed: {e}"
        return result

    # Validate syntax
    if not validate_python_syntax(tool_file):
        log(f"ERROR: Fixed code has syntax errors - rolling back")
        # Rollback
        tool_file.write_text(current_code)
        result["changes_summary"] = "Fixed code had syntax errors - rolled back"
        return result

    # Success - commit to git
    try:
        commit_result = commit_fix_to_git(tool_file, tool_name, failures, backup_path)
        if commit_result["success"]:
            log(f"✓ Committed fix to git: {commit_result['commit_hash']}")
        else:
            log(f"WARNING: Git commit failed: {commit_result['error']}")
    except Exception as e:
        log(f"WARNING: Git commit exception: {e}")

    result["success"] = True
    result["fix_applied"] = True
    result["changes_summary"] = f"Auto-fixed {tool_name} after {len(failures)} failures. Backup: {backup_path.name}"

    return result


def commit_fix_to_git(file_path: Path, tool_name: str, failures: list, backup_path: Path) -> dict:
    """
    Commit the auto-fix to git with detailed message.

    Returns:
        {"success": bool, "commit_hash": str or None, "error": str or None}
    """
    try:
        # Stage the modified file
        stage_result = subprocess.run(
            ["git", "add", str(file_path)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10
        )

        if stage_result.returncode != 0:
            return {"success": False, "commit_hash": None, "error": f"git add failed: {stage_result.stderr}"}

        # Build detailed commit message
        failure_count = len(failures)
        first_failure = failures[0]["timestamp"] if failures else "unknown"
        last_failure = failures[-1]["timestamp"] if failures else "unknown"

        commit_msg = f"""Auto-fix: {tool_name} ({failure_count} failures)

🤖 Autonomous code repair by MiniMax

**Tool:** {tool_name}
**Failures:** {failure_count} times
**Time window:** {first_failure} to {last_failure}
**Backup:** {backup_path.name}

**Recent errors:**
{chr(10).join([f'- {f.get("error", "No error message")}' for f in failures[-3:]])}

This fix was automatically generated, validated, and deployed by
the bot health monitor's auto-repair system.

To rollback: git revert HEAD
To review backup: cat data/backups/{backup_path.name}

Co-Authored-By: MiniMax M2.5 <noreply@minimax.io>"""

        # Commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=10
        )

        if commit_result.returncode != 0:
            return {"success": False, "commit_hash": None, "error": f"git commit failed: {commit_result.stderr}"}

        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=5
        )

        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else None

        return {"success": True, "commit_hash": commit_hash, "error": None}

    except Exception as e:
        return {"success": False, "commit_hash": None, "error": str(e)}


def main():
    """Test the auto-fixer with a sample failure."""
    # Example usage
    test_failures = [
        {
            "timestamp": "2026-02-16 10:30:00",
            "error": "KeyError: 'content'",
            "context": "Session had tool_use messages without content field"
        },
        {
            "timestamp": "2026-02-16 10:45:00",
            "error": "KeyError: 'content'",
            "context": "Same error in different session"
        },
        {
            "timestamp": "2026-02-16 11:00:00",
            "error": "KeyError: 'content'",
            "context": "Recurring pattern"
        }
    ]

    result = fix_tool("test_tool", test_failures)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
