#!/usr/bin/env python3
"""
Mock chat test: run a set of realistic user questions through the conversation handler.

Verifies for each question:
  1) No errors (reply is not an error message or exception)
  2) Expected tools were called (at least one of the listed tools)
  3) Reply has substantial, non-generic content (not hallucination or vague)

Run from repo root (Ollama, OpenRouter, or MiniMax must be available):
  cd /Users/printer/atlas
  ATLAS_TEST_RECORD_TOOLS=1 python3 tools/telegram/mock_chat_test.py

Env options:
  MOCK_CHAT_MODEL=ollama    Use local Ollama
  MOCK_CHAT_MODEL=minimax   Use MiniMax API (requires MINIMAX key, e.g. envchain atlas)
  MAX_QUESTIONS=N            Run only first N questions (0 = all)
  MOCK_CHAT_TIMEOUT=120      Per-message timeout in seconds (0 = no timeout)
  RESET_SESSION_EACH=1       Clear session between questions
  DRY_RUN=1                  No LLM: run prefetch + Bambu paths only, verify tools

Expected tools per question (at least one of):
  tasks today / priorities   → kanban_read, journal_read_recent, reminders_read
  reminders list             → reminders_read
  Bambu / printer            → bambu
  remind me to X             → reminders_read, reminder_add
  what do you know about me  → memory_read
  meetings / calendar        → google_calendar_find_events
  search the web / lookup    → web_search, browser_search, or browser
  journal                    → journal_read_recent
  am I on track              → heartbeat_read
  browser open / Kraken etc  → browser, web_search, browser_search
  trial prep                 → trial_read_guide, trial_list_cases, read_goal
  read file / list files     → read_file, list_files
  case task by name          → legalkanban_search_cases, legalkanban_create_task
"""

import asyncio
import os
import sys
from pathlib import Path

# Run from repo root so config and tool paths resolve
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Telegram tools live in tools/telegram
sys.path.insert(0, str(REPO_ROOT / "tools" / "telegram"))

# Enable tool recording before importing tool_runner
os.environ["ATLAS_TEST_RECORD_TOOLS"] = "1"

from conversation import handle_message, reset_session
import tool_runner

TEST_USER_ID = 999999

# (user message, expected_tools: at least one of these must appear in TOOL_CALL_RECORD, short label)
MOCK_QUESTIONS = [
    (
        "What are my tasks for today?",
        ["kanban_read", "journal_read_recent", "reminders_read"],
        "tasks today",
    ),
    (
        "What's on my plate this week?",
        ["kanban_read", "journal_read_recent", "reminders_read"],
        "priorities",
    ),
    (
        "What do I have to remember? What are my reminders?",
        ["reminders_read"],
        "reminders",
    ),
    (
        "How's the printer? Is it printing?",
        ["bambu"],
        "Bambu",
    ),
    (
        "Remind me to call the dentist tomorrow.",
        ["reminders_read", "reminder_add"],
        "reminder add",
    ),
    (
        "What do you know about me?",
        ["memory_read"],
        "memory",
    ),
    (
        "Do I have any meetings today or this week?",
        ["google_calendar_find_events"],
        "calendar",
    ),
    (
        "Search the web for Ellensburg weather today.",
        ["web_search", "browser_search", "browser"],
        "web search",
    ),
    (
        "What's in my journal from the last few days?",
        ["journal_read_recent"],
        "journal",
    ),
    (
        "Am I on track? How's my week?",
        ["heartbeat_read"],
        "heartbeat",
    ),
    # Browser / look up
    (
        "Look up the Seattle Kraken score from last night.",
        ["web_search", "browser_search", "browser"],
        "browser / lookup",
    ),
    (
        "Open the Ellensburg weather page and tell me the forecast.",
        ["browser", "web_search", "browser_search"],
        "browser open",
    ),
    (
        "Search the web for DUI discovery deadlines in Washington.",
        ["web_search", "browser_search", "browser"],
        "web search legal",
    ),
    # Trial prep / file read
    (
        "What's the DUI case prep workflow? What do I do for trial prep?",
        ["trial_read_guide", "trial_list_cases", "trial_list_templates", "read_goal"],
        "trial prep",
    ),
    (
        "Show me what's in tools/manifest.md.",
        ["read_file"],
        "read file",
    ),
    (
        "What files are in the goals folder?",
        ["list_files"],
        "list files",
    ),
    # Calendar / schedule
    (
        "What's on my calendar tomorrow?",
        ["google_calendar_find_events"],
        "calendar tomorrow",
    ),
    # Case task (by name)
    (
        "Add a task for Nelson: file motion in limine by Friday.",
        ["legalkanban_search_cases", "legalkanban_create_task", "reminder_add"],
        "case task by name",
    ),
]


def _is_error_reply(reply: str) -> bool:
    if not reply or not reply.strip():
        return True
    lower = reply.lower()
    if "api error" in lower or "couldn't do that" in lower or "error code" in lower:
        return True
    if "operation failed" in lower or "please try again" in lower:
        return True
    if "not found" in lower and "tool" in lower:
        return True
    return False


def _is_too_vague(reply: str) -> bool:
    """Heuristic: reply should not be a single sentence or purely deflecting."""
    if len(reply.strip()) < 80:
        return True
    lower = reply.lower()
    deflect = (
        "could you clarify",
        "could you tell me more",
        "i don't have access",
        "i'm not able to",
        "i cannot access",
        "i don't have that information",
        "i would need more",
    )
    if any(d in lower for d in deflect) and len(reply) < 200:
        return True
    return False


async def run_one(question: str, expected_tools: list[str], label: str, reset_before: bool, timeout: float = 0) -> dict:
    if reset_before:
        reset_session(TEST_USER_ID)
    tool_runner.TOOL_CALL_RECORD.clear()
    try:
        if timeout > 0:
            reply = await asyncio.wait_for(handle_message(question, TEST_USER_ID), timeout=timeout)
        else:
            reply = await handle_message(question, TEST_USER_ID)
    except asyncio.TimeoutError as e:
        return {
            "ok": False,
            "error": "Timeout: " + str(e),
            "reply": "",
            "tools": list(tool_runner.TOOL_CALL_RECORD),
            "label": label,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "reply": "",
            "tools": list(tool_runner.TOOL_CALL_RECORD),
            "label": label,
        }
    recorded = [(n, a) for n, a in tool_runner.TOOL_CALL_RECORD]
    tools_called = [n for n, _ in recorded]
    expected_ok = not expected_tools or any(t in tools_called for t in expected_tools)
    no_error = not _is_error_reply(reply)
    not_vague = not _is_too_vague(reply)
    return {
        "ok": no_error and expected_ok,
        "error": None,
        "reply": reply,
        "tools": recorded,
        "tools_called": tools_called,
        "expected_tools": expected_tools,
        "expected_ok": expected_ok,
        "no_error": no_error,
        "not_vague": not_vague,
        "label": label,
    }


def _dry_run():
    """Run prefetch and Bambu paths only (no LLM); verify expected tools."""
    tool_runner.TOOL_CALL_RECORD.clear()
    # Simulate "what are my tasks" prefetch
    tool_runner.execute("kanban_read", {})
    tool_runner.execute("journal_read_recent", {"days": 7})
    tool_runner.execute("reminders_read", {})
    t1 = list(tool_runner.TOOL_CALL_RECORD)
    tool_runner.TOOL_CALL_RECORD.clear()
    # Simulate Bambu
    tool_runner.execute("bambu", {"action": "status"})
    t2 = list(tool_runner.TOOL_CALL_RECORD)
    print("DRY RUN (no LLM)")
    print("  Priorities prefetch tools:", [n for n, _ in t1])
    print("  Bambu query tools:", [n for n, _ in t2])
    ok = ("kanban_read" in [n for n, _ in t1] and "bambu" in [n for n, _ in t2])
    print("  PASS" if ok else "  FAIL")
    return 0 if ok else 1


def main():
    if os.environ.get("DRY_RUN") == "1":
        return _dry_run()
    reset_each = os.environ.get("RESET_SESSION_EACH", "0") == "1"
    force_model = os.environ.get("MOCK_CHAT_MODEL", "")
    max_q = int(os.environ.get("MAX_QUESTIONS", "0") or 0)
    per_msg_timeout = float(os.environ.get("MOCK_CHAT_TIMEOUT", "0") or 0)
    reset_session(TEST_USER_ID)
    if force_model in ("ollama", "minimax"):
        from conversation import _sessions
        _sessions[TEST_USER_ID] = {
            "messages": [],
            "system_prompt": "",
            "memory_loaded": False,
            "model_id": force_model,
        }
        print("Forcing model: {} ({})".format(force_model, "local" if force_model == "ollama" else "MiniMax API"))
    print("Mock chat test (user_id={})".format(TEST_USER_ID))
    print("Reset session each question:", reset_each)
    questions_to_run = MOCK_QUESTIONS[:max_q] if max_q > 0 else MOCK_QUESTIONS
    if max_q > 0:
        print("Running first {} questions (MAX_QUESTIONS={})".format(max_q, max_q))
    print("-" * 60)
    results = []
    for question, expected_tools, label in questions_to_run:
        r = asyncio.run(run_one(question, expected_tools, label, reset_before=reset_each, timeout=per_msg_timeout))
        results.append((question, r))
    # Report
    failed = 0
    for question, r in results:
        status = "PASS" if r["ok"] and r.get("not_vague", True) else "FAIL"
        if status == "FAIL":
            failed += 1
        print("\n[{}] {} ({})".format(status, r["label"], question[:50] + ("…" if len(question) > 50 else "")))
        print("  Tools called:", r.get("tools_called", []))
        if r.get("expected_tools"):
            print("  Expected (one of):", r["expected_tools"], "→", "ok" if r.get("expected_ok") else "MISSING")
        if r.get("error"):
            print("  Error:", r["error"])
        if r.get("reply"):
            preview = (r["reply"][:200] + "…") if len(r["reply"]) > 200 else r["reply"]
            print("  Reply preview:", preview.replace("\n", " "))
        if not r.get("no_error"):
            print("  (Reply looks like an error message)")
        if not r.get("not_vague"):
            print("  (Reply may be too vague/short)")
    print("\n" + "-" * 60)
    print("Total: {} passed, {} failed".format(len(results) - failed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
