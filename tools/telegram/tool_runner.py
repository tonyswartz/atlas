"""
Tool runner.

Translates Claude's tool_use requests into subprocess calls against the existing
memory scripts and goal files. Parses their stdout back into strings for Claude.

All subprocess calls use arg lists (never shell=True) to prevent injection.
Tool failures return a generic user-facing message; real errors are logged.
"""

import asyncio
import csv
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from config import get_repo_root, load_config

REPO_ROOT = get_repo_root()

# Ensure we can import from the repo root (e.g. memory module)
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

import memory.memory_read
import memory.memory_write
import tools.memory.conversation_tracker


def _resolve_path(key: str, default: Path) -> Path:
    """Resolve path from config paths section or use default. Paths can be absolute or relative to repo root."""
    try:
        config = load_config()
        paths = config.get("paths") or {}
        raw = paths.get(key)
        if not raw:
            return default
        p = Path(raw)
        if not p.is_absolute():
            p = (REPO_ROOT / raw).resolve()
        return p
    except Exception:
        return default
# Obsidian vault Trials folder (same as commands.VAULT / "Trials")
TRIALS_ROOT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Trials")

# Obsidian vault Rotary folders
ROTARY_ROOT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary")
ROTARY_LOG = ROTARY_ROOT / "Rotary Log.md"
ROTARY_TEMPLATE = ROTARY_ROOT / "Templates" / "Agenda Template.md"
ROTARY_MEETINGS = ROTARY_ROOT / "Meetings"

logger = logging.getLogger(__name__)

USER_FACING_ERROR = "Operation failed. Please try again."

# Test mode: when ATLAS_TEST_RECORD_TOOLS=1, each execute() appends (tool_name, tool_input) here
TOOL_CALL_RECORD: list[tuple[str, dict]] = []


def _run(args: list, cwd: Path = REPO_ROOT, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a subprocess with the given args. Returns the CompletedProcess."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout
    )


def _parse_output(stdout: str) -> str:
    """
    Parse script stdout into a clean result string.

    Scripts fall into two patterns:
      - Status line ("OK ..." or "ERROR ...") followed by JSON
      - Pure JSON (memory_read --format json)
      - Raw text (read_goal returns markdown)

    Strategy: find the first line starting with '{', parse from there as JSON.
    If no '{' found, return raw stdout (handles markdown goal files).
    """
    lines = stdout.strip().split("\n")

    # Find where JSON starts
    json_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break

    if json_start is not None:
        json_text = "\n".join(lines[json_start:])
        try:
            parsed = json.loads(json_text)
            return json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass

    # No valid JSON found — return raw output (e.g. goal markdown)
    return stdout.strip()


async def execute(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool by name with the given input dict from Claude's tool_use block.

    Returns a string result to feed back to Claude as a tool_result.
    """
    return await asyncio.to_thread(_execute_sync, tool_name, tool_input)


def _execute_sync(tool_name: str, tool_input: dict) -> str:
    """
    Synchronous implementation of tool execution.
    """
    if os.environ.get("ATLAS_TEST_RECORD_TOOLS"):
        TOOL_CALL_RECORD.append((tool_name, dict(tool_input)))
    try:
        if tool_name == "memory_read":
            return _memory_read(tool_input)
        elif tool_name == "memory_write":
            return _memory_write(tool_input)
        elif tool_name == "memory_search":
            return _memory_search(tool_input)
        elif tool_name == "memory_db":
            return _memory_db(tool_input)
        elif tool_name == "read_goal":
            return _read_goal(tool_input)
        elif tool_name == "journal_read_recent":
            return _journal_read_recent(tool_input)
        elif tool_name == "reminders_read":
            return _reminders_read()
        elif tool_name == "kanban_read":
            return _kanban_read()
        elif tool_name == "heartbeat_read":
            return _heartbeat_read()
        elif tool_name == "trial_read_guide":
            return _trial_read_guide()
        elif tool_name == "trial_list_cases":
            return _trial_list_cases()
        elif tool_name == "trial_list_templates":
            return _trial_list_templates()
        elif tool_name == "trial_read_template":
            return _trial_read_template(tool_input)
        elif tool_name == "trial_save_document":
            return _trial_save_document(tool_input)
        elif tool_name == "rotary_read_log":
            return _rotary_read_log()
        elif tool_name == "rotary_read_template":
            return _rotary_read_template()
        elif tool_name == "rotary_read_agenda":
            return _rotary_read_agenda(tool_input)
        elif tool_name == "rotary_save_agenda":
            return _rotary_save_agenda(tool_input)
        elif tool_name == "read_file":
            return _read_file(tool_input)
        elif tool_name == "list_files":
            return _list_files(tool_input)
        elif tool_name == "edit_file":
            return _edit_file(tool_input)
        elif tool_name == "reminder_add":
            return _reminder_add(tool_input)
        elif tool_name == "reminder_mark_done":
            return _reminder_mark_done(tool_input)
        elif tool_name == "bambu":
            return _bambu(tool_input)
        elif tool_name == "browser_search":
            return _browser_search(tool_input)
        elif tool_name == "run_tool":
            return _run_tool(tool_input)
        elif tool_name == "browser":
            return _browser(tool_input)
        elif tool_name == "web_search":
            return _web_search(tool_input)
        elif tool_name == "system_config":
            return _system_config(tool_input)
        elif tool_name == "telegram_groups":
            return _telegram_groups(tool_input)
        elif tool_name == "conversation_context":
            return _conversation_context(tool_input)
        elif tool_name == "legalkanban_search_cases":
            return _legalkanban_search_cases(tool_input)
        elif tool_name == "legalkanban_create_task":
            return _legalkanban_create_task(tool_input)
        elif tool_name == "podcast_create_episode":
            return _podcast_create_episode(tool_input)
        elif tool_name == "podcast_approve_script":
            return _podcast_approve_script(tool_input)
        elif tool_name == "schedule_read":
            return _schedule_read(tool_input)
        elif tool_name == "schedule_preview":
            return _schedule_preview(tool_input)
        elif tool_name == "schedule_add":
            return _schedule_add(tool_input)
        elif tool_name == "script_writer":
            return _script_writer(tool_input)
        elif tool_name == "launchd_manager":
            return _launchd_manager(tool_input)
        elif tool_name in _ZAPIER_TOOLS:
            return _zapier(tool_name, tool_input)
        else:
            return json.dumps({"success": False, "error": USER_FACING_ERROR})
    except Exception as e:
        logger.exception("Tool runner exception")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


# ---------------------------------------------------------------------------
# Individual tool translators
# ---------------------------------------------------------------------------

def _memory_read(inp: dict) -> str:
    """
    Directly call memory.memory_read.load_all_memory to avoid subprocess overhead.
    """
    try:
        # Map arguments
        # memory_read.py logic:
        # include_memory = not args.logs_only
        # include_logs = not args.memory_only
        include_memory = not inp.get("logs_only")
        include_logs = not inp.get("memory_only")
        include_db = inp.get("include_db", False)
        log_days = int(inp.get("days", 2))

        # Call directly
        context = memory.memory_read.load_all_memory(
            include_memory=include_memory,
            include_logs=include_logs,
            include_db=include_db,
            log_days=log_days
            # db_hours default is 24, min_importance default is 5
        )

        # Format output
        fmt = inp.get("format", "json")
        if fmt == "markdown":
            return memory.memory_read.format_as_markdown(context)
        elif fmt == "summary":
            summary = context.get('summary', {})
            return json.dumps({
                "success": True,
                "loaded_at": context.get('loaded_at'),
                "memory_file_loaded": context.get('memory_file', {}).get('success', False),
                "memory_sections": summary.get('memory_sections', []),
                "logs_loaded": summary.get('logs_loaded', 0),
                "log_dates": summary.get('log_dates', []),
                "db_entries_loaded": summary.get('db_entries_loaded', 0)
            }, indent=2)
        else:
            # Default to JSON
            return json.dumps(context, indent=2, default=str)

    except Exception as e:
        logger.exception("memory_read direct call failed")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _memory_write(inp: dict) -> str:
    """
    Directly call memory.memory_write functions to avoid subprocess overhead.
    """
    try:
        content = inp["content"]
        # Handle MEMORY.md update
        if inp.get("update_memory_md"):
            section = inp.get("section", "key_facts")
            result = memory.memory_write.append_to_memory_file(content, section)
        else:
            tags_raw = inp.get("tags")
            tags = tags_raw.split(',') if tags_raw else None
            entry_type = inp.get("type", "fact")

            # replicate logic from memory_write.py
            if entry_type == 'note':
                result = memory.memory_write.append_to_daily_log(
                    content=content,
                    entry_type='note',
                    timestamp=True,
                    category=tags[0] if tags else None
                )
            else:
                result = memory.memory_write.write_to_memory(
                    content=content,
                    entry_type=entry_type,
                    source=inp.get("source", "session"),
                    importance=int(inp.get("importance", 5)),
                    tags=tags,
                    context=inp.get("context"),
                    log_to_file=True,
                    add_to_db=True
                )

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.exception("memory_write direct call failed")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _memory_search(inp: dict) -> str:
    args = [sys.executable, "memory/hybrid_search.py"]

    args.extend(["--query", inp["query"]])

    if "limit" in inp:
        args.extend(["--limit", str(inp["limit"])])
    if inp.get("keyword_only", True):
        args.append("--keyword-only")
    if "type" in inp:
        args.extend(["--type", inp["type"]])

    result = _run(args)
    if result.returncode != 0:
        logger.warning("memory_search failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return _parse_output(result.stdout)


def _memory_db(inp: dict) -> str:
    args = [sys.executable, "memory/memory_db.py"]

    args.extend(["--action", inp["action"]])

    if "id" in inp:
        args.extend(["--id", str(inp["id"])])
    if "query" in inp:
        args.extend(["--query", inp["query"]])
    if "type" in inp:
        args.extend(["--type", inp["type"]])
    if "hours" in inp:
        args.extend(["--hours", str(inp["hours"])])
    if "limit" in inp:
        args.extend(["--limit", str(inp["limit"])])

    result = _run(args)
    if result.returncode != 0:
        logger.warning("memory_db failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return _parse_output(result.stdout)


def _read_goal(inp: dict) -> str:
    filename = inp.get("filename", "")
    goals_dir = REPO_ROOT / "goals"

    # Path traversal guard: resolve and check it stays inside goals/
    target = (goals_dir / filename).resolve()
    if not target.is_relative_to(goals_dir.resolve()):
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    if not target.exists():
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    return target.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Journal (read-only; Obsidian export CSV)
# ---------------------------------------------------------------------------

_DEFAULT_JOURNAL_CSV_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Journals/journal-entries-2025-01-01-to-2026-01-31.csv")


def _journal_read_recent(inp: dict) -> str:
    """Read the last N days of journal entries from the Obsidian journal CSV. Read-only."""
    path = _resolve_path("journal_csv", _DEFAULT_JOURNAL_CSV_PATH)
    if not path.exists():
        return json.dumps({"success": False, "error": "Journal export not found.", "entries": []})

    days = max(1, min(31, int(inp.get("days", 7))))

    try:
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except (OSError, csv.Error) as e:
        logger.warning("journal_read_recent failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR, "entries": []})

    # Sort by date descending (most recent first), then by time
    def row_key(r):
        return (r.get("Date") or "", r.get("Time") or "")

    rows_sorted = sorted(rows, key=row_key, reverse=True)

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    entries = []
    seen_dates = set()
    for r in rows_sorted:
        d = (r.get("Date") or "").strip()
        if d < cutoff:
            break
        if d in seen_dates:
            continue
        seen_dates.add(d)
        text = (r.get("Entry Text") or "").strip()
        mood = (r.get("Mood Rating") or "").strip()
        entries.append({"date": d, "entry_text": text or "(no text)", "mood_rating": mood})

    # Return chronological order (oldest of window first)
    entries.reverse()
    return json.dumps({"success": True, "days_requested": days, "entries": entries}, indent=2)


# ---------------------------------------------------------------------------
# Reminders (read-only; Tony Reminders.md in vault)
# ---------------------------------------------------------------------------

_DEFAULT_REMINDERS_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Tony Reminders.md")
_REMINDER_SECTIONS = ["[Shopping]", "[Today]", "[Later This Week]", "[Later This Month]", "[Later Later]"]

# Tony Tasks.md (LegalKanban-synced tasks + other task sections)
_DEFAULT_KANBAN_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Tony Tasks.md")


def _reminders_read() -> str:
    """Read Tony Reminders.md by section. Read-only; same sections as reminder_add."""
    path = _resolve_path("reminders", _DEFAULT_REMINDERS_PATH)
    if not path.exists():
        return json.dumps({"success": True, "message": "Reminders file not found.", "sections": {}})

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("reminders_read failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR, "sections": {}})

    sections = {h: [] for h in _REMINDER_SECTIONS}
    current = None
    for raw in content.splitlines():
        line = raw.rstrip()
        if line.strip() in sections:
            current = line.strip()
            continue
        if current and line.strip().startswith("- ") and line.strip() != "- ":
            sections[current].append(line.strip())

    # Drop empty sections for cleaner output
    sections = {k: v for k, v in sections.items() if v}
    return json.dumps({"success": True, "sections": sections}, indent=2)


def _kanban_read() -> str:
    """Read Tony Tasks.md (includes LegalKanban-synced tasks). Read-only."""
    path = _resolve_path("kanban", _DEFAULT_KANBAN_PATH)
    if not path.exists():
        return json.dumps({"success": True, "message": "Tasks file not found.", "content": ""})

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("kanban_read failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR, "content": ""})

    return json.dumps({"success": True, "content": content.strip()}, indent=2)


# ---------------------------------------------------------------------------
# Heartbeat (read-only; HEARTBEAT.md + heartbeat-state.json)
# ---------------------------------------------------------------------------

HEARTBEAT_MD = REPO_ROOT / "HEARTBEAT.md"
HEARTBEAT_STATE = REPO_ROOT / "memory" / "heartbeat-state.json"


def _heartbeat_read() -> str:
    """Read HEARTBEAT.md checklist and heartbeat-state.json. Read-only."""
    checklist = []
    if HEARTBEAT_MD.exists():
        try:
            lines = HEARTBEAT_MD.read_text(encoding="utf-8").strip().splitlines()
            checklist = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        except OSError as e:
            logger.warning("heartbeat_read HEARTBEAT.md failed: %s", e)

    state = {}
    if HEARTBEAT_STATE.exists():
        try:
            state = json.loads(HEARTBEAT_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    return json.dumps({
        "success": True,
        "checklist": checklist,
        "state": state,
    }, indent=2)


# ---------------------------------------------------------------------------
# Trial prep tools (Obsidian Trials/ = Case Prep Guide + templates + case folders)
# ---------------------------------------------------------------------------

def _trial_safe_path(*parts: str) -> Path | None:
    """Resolve path under TRIALS_ROOT; return None if outside."""
    if not TRIALS_ROOT.exists():
        return None
    target = TRIALS_ROOT.joinpath(*parts).resolve()
    try:
        target.relative_to(TRIALS_ROOT.resolve())
    except ValueError:
        return None
    return target


def _trial_read_guide() -> str:
    path = _trial_safe_path("Case Prep Guide.md")
    if not path or not path.is_file():
        return json.dumps({"success": False, "error": "Case Prep Guide not found."})
    return path.read_text(encoding="utf-8")


def _trial_list_cases() -> str:
    if not TRIALS_ROOT.exists():
        return json.dumps({"success": False, "error": "Trials folder not found."})
    out: dict[str, list[str]] = {}
    for year_dir in sorted(TRIALS_ROOT.iterdir()):
        if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
            cases = [d.name for d in year_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if cases:
                out[year_dir.name] = sorted(cases)
    return json.dumps(out, indent=2)


def _trial_list_templates() -> str:
    templates_dir = _trial_safe_path("Templates")
    if not templates_dir or not templates_dir.is_dir():
        return json.dumps({"success": False, "error": "Templates folder not found."})
    names = [f.name for f in templates_dir.iterdir() if f.suffix == ".md"]
    return json.dumps({"templates": sorted(names)})


def _trial_read_template(inp: dict) -> str:
    name = (inp.get("template_name") or "").strip()
    if not name:
        return json.dumps({"success": False, "error": "template_name required."})
    # No path traversal: only basename
    if "/" in name or "\\" in name or name.startswith("."):
        return json.dumps({"success": False, "error": "Invalid template name."})
    path = _trial_safe_path("Templates", name)
    if not path or not path.is_file():
        return json.dumps({"success": False, "error": f"Template not found: {name}"})
    return path.read_text(encoding="utf-8")


def _trial_save_document(inp: dict) -> str:
    year = (inp.get("year") or "").strip()
    case_name = (inp.get("case_name") or "").strip()
    doc_name = (inp.get("document_name") or "").strip()
    content = inp.get("content", "")
    if not year or not case_name or not doc_name:
        return json.dumps({"success": False, "error": "year, case_name, and document_name required."})
    if "/" in doc_name or "\\" in doc_name or doc_name.startswith("."):
        return json.dumps({"success": False, "error": "Invalid document_name."})
    if "/" in case_name or "\\" in case_name or "." in case_name:
        return json.dumps({"success": False, "error": "Invalid case_name."})
    path = _trial_safe_path(year, case_name, doc_name)
    if not path:
        return json.dumps({"success": False, "error": "Invalid path."})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"success": True, "path": str(path)})
    except Exception as e:
        logger.warning("trial_save_document failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


# ---------------------------------------------------------------------------
# Rotary agenda tools
# ---------------------------------------------------------------------------
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")


def _parse_rotary_log(text: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Return (spotlights, speakers) keyed by 'M/D' date string."""
    spotlights: dict[str, str] = {}
    speakers: dict[str, dict[str, str]] = {}
    current: str | None = None

    for line in text.splitlines():
        s = line.strip()
        if s == "## Member Spotlight Schedule":
            current = "spotlight"
            continue
        if s == "## Speaker Schedule":
            current = "speaker"
            continue
        if s.startswith("##"):
            current = None
            continue

        if current and s.startswith("- "):
            m = re.match(r"-\s+(\d+/\d+):\s*(.*)", s)
            if not m:
                continue
            date_key, value = m.group(1), m.group(2).strip()
            if current == "spotlight":
                spotlights[date_key] = value
            else:
                name, topic = (value.split(" — ", 1) + ["TBD"])[:2]
                speakers[date_key] = {"name": name.strip(), "topic": topic.strip()}

    return spotlights, speakers


def _rotary_read_log() -> str:
    """Read Rotary Log and return next meeting info."""
    if not ROTARY_LOG.exists():
        return json.dumps({"success": False, "error": "Rotary Log.md not found."})

    try:
        spotlights, speakers = _parse_rotary_log(ROTARY_LOG.read_text())
        today = datetime.now(TZ).date()

        # Find nearest upcoming (or today) meeting date from the schedule
        best_date = None
        best_key: str | None = None
        for key in spotlights:
            try:
                month, day = (int(x) for x in key.split("/"))
                candidate = today.replace(month=month, day=day)
                if candidate < today:
                    candidate = candidate.replace(year=today.year + 1)
                if best_date is None or candidate < best_date:
                    best_date = candidate
                    best_key = key
            except Exception:
                continue

        if not best_date or not best_key:
            return json.dumps({"success": False, "error": "No upcoming meeting dates found in Rotary Log."})

        spotlight = spotlights.get(best_key, "[TBD]")
        speaker = speakers.get(best_key, {"name": "[TBD]", "topic": "[TBD]"})

        return json.dumps({
            "success": True,
            "meeting_date": best_date.strftime("%Y-%m-%d"),
            "meeting_date_long": best_date.strftime("%A, %B %d, %Y"),
            "member_spotlight": spotlight,
            "speaker_name": speaker["name"],
            "speaker_topic": speaker["topic"]
        }, indent=2)
    except Exception as e:
        logger.warning("rotary_read_log failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _rotary_read_template() -> str:
    """Read the Rotary agenda template."""
    if not ROTARY_TEMPLATE.exists():
        return json.dumps({"success": False, "error": "Agenda Template.md not found."})
    try:
        return ROTARY_TEMPLATE.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("rotary_read_template failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _rotary_read_agenda(inp: dict) -> str:
    """Read an existing Rotary agenda by date."""
    meeting_date_str = (inp.get("meeting_date") or "").strip()

    if not meeting_date_str:
        return json.dumps({"success": False, "error": "meeting_date required (YYYY-MM-DD)."})

    try:
        # Parse meeting date
        meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()

        # Look for agenda file
        agenda_file = ROTARY_MEETINGS / f"{meeting_date.strftime('%Y-%m-%d')} Agenda.md"

        if not agenda_file.exists():
            return json.dumps({"success": False, "error": f"No agenda found for {meeting_date_str}."})

        content = agenda_file.read_text(encoding="utf-8")
        return json.dumps({"success": True, "content": content, "date": meeting_date_str})
    except ValueError:
        return json.dumps({"success": False, "error": "Invalid meeting_date format. Use YYYY-MM-DD."})
    except Exception as e:
        logger.warning("rotary_read_agenda failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _rotary_save_agenda(inp: dict) -> str:
    """Save a completed Rotary agenda with automatic backup and validation."""
    content = inp.get("content", "")
    meeting_date_str = (inp.get("meeting_date") or "").strip()

    if not content:
        return json.dumps({"success": False, "error": "content required."})
    if not meeting_date_str:
        return json.dumps({"success": False, "error": "meeting_date required (YYYY-MM-DD)."})

    try:
        # Parse meeting date
        meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()

        # Prepare output path
        ROTARY_MEETINGS.mkdir(parents=True, exist_ok=True)
        out_file = ROTARY_MEETINGS / f"{meeting_date.strftime('%Y-%m-%d')} Agenda.md"

        # SAFEGUARD: Validate content length before overwriting
        if out_file.exists():
            existing_content = out_file.read_text(encoding="utf-8")
            existing_len = len(existing_content)
            new_len = len(content)

            # Reject if new content is suspiciously short (< 50% of original AND < 500 chars)
            # This catches accidental overwrites with partial content
            if new_len < 500 and new_len < (existing_len * 0.5):
                logger.warning(
                    "rotary_save_agenda BLOCKED suspicious overwrite: "
                    f"existing={existing_len} chars, new={new_len} chars (too short)"
                )
                return json.dumps({
                    "success": False,
                    "error": f"Content too short ({new_len} chars). "
                            f"Existing agenda is {existing_len} chars. "
                            f"Use rotary_read_agenda first to get the full content, "
                            f"then modify and save the complete agenda."
                })

            # Create timestamped backup before overwriting
            backup_dir = ROTARY_MEETINGS / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"{meeting_date.strftime('%Y-%m-%d')}_backup_{timestamp}.md"
            backup_file.write_text(existing_content, encoding="utf-8")
            logger.info(f"rotary_save_agenda: created backup at {backup_file.name}")

        # Save the new content
        out_file.write_text(content, encoding="utf-8")

        # Return relative path from Obsidian vault root
        vault_root = ROTARY_ROOT.parent
        rel_path = out_file.relative_to(vault_root)

        return json.dumps({"success": True, "path": str(rel_path)})
    except ValueError:
        return json.dumps({"success": False, "error": "Invalid meeting_date format. Use YYYY-MM-DD."})
    except Exception as e:
        logger.warning("rotary_save_agenda failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _bambu(inp: dict) -> str:
    """Query or control Bambu printer via bambu-cli."""
    action = (inp.get("action") or "").strip().lower()

    # Map actions to bambu-cli commands
    _CMD_MAP = {
        "status":    ["/opt/homebrew/bin/bambu-cli", "--json", "status"],
        "ams":       ["/opt/homebrew/bin/bambu-cli", "--json", "ams", "status"],
        "pause":     ["/opt/homebrew/bin/bambu-cli", "print", "pause"],
        "resume":    ["/opt/homebrew/bin/bambu-cli", "print", "resume"],
        "stop":      ["/opt/homebrew/bin/bambu-cli", "print", "stop"],
        "light_on":  ["/opt/homebrew/bin/bambu-cli", "light", "on"],
        "light_off": ["/opt/homebrew/bin/bambu-cli", "light", "off"],
    }

    if action not in _CMD_MAP:
        return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    try:
        result = subprocess.run(_CMD_MAP[action], capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("bambu-cli %s failed: %s", action, e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    out = result.stdout.strip()
    if result.returncode != 0:
        logger.warning("bambu-cli %s exit %d: %s", action, result.returncode, (result.stderr or out)[:200])
        return json.dumps({"success": False, "error": out or USER_FACING_ERROR})

    # For JSON-output commands (status, ams), parse and return structured
    if action in ("status", "ams"):
        try:
            data = json.loads(out)
            return json.dumps({"success": True, "action": action, "data": data}, indent=2)
        except json.JSONDecodeError:
            pass  # fall through to raw

    # For control commands, return confirmation
    return json.dumps({"success": True, "action": action, "message": out or f"{action} command sent."})


def _browser_search(inp: dict) -> str:
    """Search the web via DuckDuckGo HTML endpoint. No API key or browser needed."""
    import re
    import urllib.request
    import urllib.parse

    query = (inp.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query is required."})
    count = min(int(inp.get("count") or 5), 10)

    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode("utf-8")
    except Exception as e:
        logger.warning("browser_search fetch failed: %s", e)
        return json.dumps({"ok": False, "error": f"Search request failed: {e}"})

    def _clean(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s).strip()

    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', body, re.DOTALL)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</div>', body, re.DOTALL)
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"', body)

    results = []
    for i in range(min(count, len(titles))):
        results.append({
            "title": _clean(titles[i]) if i < len(titles) else "",
            "url": links[i] if i < len(links) else "",
            "snippet": _clean(snippets[i]) if i < len(snippets) else "",
        })

    return json.dumps({"ok": True, "query": query, "results": results}, indent=2)


def _browser(inp: dict) -> str:
    """Send a browser action to the Safari server. Requires tools/browser/browser_server.py to be running."""
    browser_path = REPO_ROOT / "tools" / "browser" / "browser.py"
    if not browser_path.exists():
        logger.warning("browser.py not found at %s", browser_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    args = [sys.executable, str(browser_path), "--action", inp["action"]]
    if inp.get("url"):
        args.extend(["--url", inp["url"]])
    if inp.get("selector"):
        args.extend(["--selector", inp["selector"]])
    if inp.get("by"):
        args.extend(["--by", inp["by"]])
    if inp.get("text") is not None:
        args.extend(["--text", inp["text"]])
    if inp.get("max_chars") is not None:
        args.extend(["--max-chars", str(inp["max_chars"])])
    result = _run(args)
    if result.returncode != 0:
        logger.warning("browser failed: %s", result.stderr.strip())
    return _parse_output(result.stdout)


def _web_search(inp: dict) -> str:
    """Search the web via Brave Search API. Requires BRAVE_API_KEY in .env."""
    script_path = REPO_ROOT / "tools" / "research" / "web_search.py"
    if not script_path.exists():
        logger.warning("web_search.py not found at %s", script_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    query = inp.get("query", "").strip()
    if not query:
        logger.error(f"web_search called without query parameter. Input: {inp}")
        return json.dumps({"success": False, "error": "Missing query parameter"})

    args = [sys.executable, str(script_path), "--query", query]
    if inp.get("count") is not None:
        args.extend(["--count", str(inp["count"])])
    result = _run(args)
    if result.returncode != 0:
        logger.warning("web_search failed: %s", result.stderr.strip())
    return _parse_output(result.stdout)


def _read_file(inp: dict) -> str:
    """Read a file inside the repo. Path traversal guarded to REPO_ROOT."""
    raw = (inp.get("path") or "").strip()
    if not raw:
        return json.dumps({"success": False, "error": "path is required."})
    target = (REPO_ROOT / raw).resolve()
    try:
        rel_path = target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return json.dumps({"success": False, "error": "Path is outside the repo."})

    # Security: Block access to sensitive files and directories
    for part in rel_path.parts:
        if part == ".git" or part == ".env" or part.startswith(".env.") or part in ("credentials.json", "token.json"):
            return json.dumps({"success": False, "error": "Access denied to sensitive file."})

    if not target.is_file():
        # Lazy backfill: episode script mirror may not exist for episodes created before mirror existed
        parts = rel_path.parts
        if len(parts) == 4 and parts[0] == "data" and parts[1] == "podcast_episodes" and parts[3] in ("script_draft.md", "script_approved.md"):
            episode_id = parts[2]
            try:
                config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
                import yaml
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                episodes_base = Path(config["paths"]["episodes_dir"])
                if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
                    episode_dir = episodes_base / episode_id
                else:
                    segs = episode_id.split("-", 1)
                    podcast_short = segs[0]
                    ep_num = segs[1]
                    podcast_full_name = next((c["name"] for k, c in config["podcasts"].items() if k == podcast_short), None)
                    if not podcast_full_name:
                        return json.dumps({"success": False, "error": f"File not found: {raw}"})
                    episode_dir = episodes_base / podcast_full_name / ep_num
                obsidian_script = episode_dir / parts[3]
                if obsidian_script.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    import shutil
                    shutil.copy2(obsidian_script, target)
                else:
                    return json.dumps({"success": False, "error": f"File not found: {raw}"})
            except Exception as e:
                logger.warning("read_file episode backfill failed: %s", e)
                return json.dumps({"success": False, "error": f"File not found: {raw}"})
    try:
        return target.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("read_file failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _list_files(inp: dict) -> str:
    """List directory contents inside the repo. Path traversal guarded to REPO_ROOT."""
    raw = (inp.get("path") or "").strip()
    target = (REPO_ROOT / raw).resolve() if raw else REPO_ROOT.resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return json.dumps({"success": False, "error": "Path is outside the repo."})
    if not target.is_dir():
        return json.dumps({"success": False, "error": f"Directory not found: {raw or '(root)'}"})
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    items = []
    for p in entries:
        if p.name.startswith("."):
            continue
        items.append({"name": p.name, "type": "dir" if p.is_dir() else "file"})
    return json.dumps({"success": True, "path": raw or ".", "entries": items}, indent=2)


def _edit_file(inp: dict) -> str:
    """Edit a file in the repo. Only allows data/podcast_episodes/<episode_id>/*.md; syncs to Obsidian."""
    raw = (inp.get("path") or "").strip()
    content = inp.get("content")
    if not raw:
        return json.dumps({"success": False, "error": "path is required."})
    if content is None:
        return json.dumps({"success": False, "error": "content is required."})

    target = (REPO_ROOT / raw).resolve()
    try:
        rel_path = target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return json.dumps({"success": False, "error": "Path is outside the repo."})

    # Only allow episode script paths: data/podcast_episodes/<episode_id>/script_*.md
    parts = rel_path.parts
    if len(parts) != 4 or parts[0] != "data" or parts[1] != "podcast_episodes" or parts[3] not in ("script_draft.md", "script_approved.md"):
        return json.dumps({"success": False, "error": "edit_file only allows data/podcast_episodes/<episode_id>/script_draft.md or script_approved.md"})

    episode_id = parts[2]  # e.g. sololaw-031
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        logger.warning("edit_file write failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    # Sync to Obsidian when possible
    try:
        config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        episodes_base = Path(config["paths"]["episodes_dir"])
        if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
            episode_dir = episodes_base / episode_id
        else:
            segs = episode_id.split("-", 1)
            podcast_short = segs[0]
            ep_num = segs[1]
            podcast_full_name = None
            for name, podcast_config in config["podcasts"].items():
                if name == podcast_short:
                    podcast_full_name = podcast_config["name"]
                    break
            if not podcast_full_name:
                return json.dumps({"success": True, "message": "Script updated in repo. Obsidian sync skipped (unknown podcast)."})
            episode_dir = episodes_base / podcast_full_name / ep_num
        obsidian_file = episode_dir / parts[-1]
        if episode_dir.exists():
            obsidian_file.write_text(content, encoding="utf-8")
            return json.dumps({"success": True, "message": "Script updated and synced to Obsidian."})
    except Exception as e:
        logger.warning("edit_file Obsidian sync failed: %s", e)
    return json.dumps({"success": True, "message": "Script updated in repo. Obsidian sync skipped (path not available)."})


def _reminder_add(inp: dict) -> str:
    """Add a reminder by calling reminder_add.py as a subprocess."""
    task = (inp.get("task") or "").strip()
    if not task:
        return json.dumps({"success": False, "error": "task is required."})
    schedule = (inp.get("schedule") or "").strip()
    script = REPO_ROOT / "tools" / "briefings" / "reminder_add.py"
    if not script.exists():
        logger.warning("reminder_add.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    args = [sys.executable, str(script), task]
    if schedule:
        args.append(schedule)
    result = _run(args)
    if result.returncode != 0:
        logger.warning("reminder_add failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    msg = result.stdout.strip() or "Reminder added."
    return json.dumps({"success": True, "message": msg})


def _reminder_mark_done(inp: dict) -> str:
    """Mark one or more reminders as done in Tony Reminders.md by matching text (and optional date)."""
    items = inp.get("items")
    if isinstance(items, str):
        items = [s.strip() for s in items.split(",") if s.strip()]
    if not isinstance(items, list):
        items = []
    items = [s.strip() for s in items if isinstance(s, str) and s.strip()]
    if not items:
        return json.dumps({"success": False, "error": "items (list of reminder text to mark done) is required.", "marked_count": 0})
    script = REPO_ROOT / "tools" / "briefings" / "reminder_add.py"
    if not script.exists():
        logger.warning("reminder_add.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR, "marked_count": 0})
    args = [sys.executable, str(script), "--mark-done"] + items
    result = _run(args, cwd=REPO_ROOT)
    try:
        out = (result.stdout or "").strip()
        data = json.loads(out) if out else {}
        if not data.get("success"):
            return json.dumps({"success": False, "error": data.get("message", result.stderr or USER_FACING_ERROR), "marked_count": data.get("marked_count", 0)})
        return json.dumps({"success": True, "marked_count": data.get("marked_count", 0), "message": data.get("message", "")})
    except json.JSONDecodeError:
        return json.dumps({"success": False, "error": result.stderr or USER_FACING_ERROR, "marked_count": 0})


def _legalkanban_search_cases(inp: dict) -> str:
    """Search open LegalKanban cases by name (e.g. last name)."""
    query = (inp.get("query") or "").strip()
    if not query:
        return json.dumps({"success": False, "error": "query is required.", "cases": []})
    script = REPO_ROOT / "tools" / "legalkanban" / "case_search.py"
    if not script.exists():
        logger.warning("case_search.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR, "cases": []})
    result = _run([sys.executable, str(script), query, "--json"], cwd=REPO_ROOT)
    try:
        # Script prints JSON to stdout
        out = (result.stdout or "").strip()
        data = json.loads(out) if out else {}
        if not data.get("success"):
            return json.dumps({"success": False, "error": data.get("error", USER_FACING_ERROR), "cases": data.get("cases", [])})
        return json.dumps({"success": True, "cases": data.get("cases", [])}, indent=2)
    except json.JSONDecodeError as e:
        logger.warning("legalkanban_search_cases parse failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR, "cases": []})


def _legalkanban_create_task(inp: dict) -> str:
    """Create a task in LegalKanban (syncs to Tony Tasks.md)."""
    title = (inp.get("title") or "").strip()
    if not title:
        return json.dumps({"success": False, "error": "title is required."})
    script = REPO_ROOT / "tools" / "legalkanban" / "task_create.py"
    if not script.exists():
        logger.warning("task_create.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    args = [sys.executable, str(script), "--title", title, "--system", "legalkanban", "--json"]
    if inp.get("case_id") is not None:
        args.extend(["--case-id", str(int(inp["case_id"]))])
    if inp.get("priority"):
        p = (inp.get("priority") or "").strip().lower()
        if p in ("high", "medium", "low"):
            args.extend(["--priority", p])
    if inp.get("due_date"):
        args.extend(["--due-date", (inp.get("due_date") or "").strip()])
    if inp.get("description"):
        args.extend(["--description", (inp.get("description") or "").strip()])
    result = _run(args, cwd=REPO_ROOT)
    try:
        out = (result.stdout or "").strip()
        data = json.loads(out) if out else {}
        if result.returncode != 0 or not data.get("success"):
            return json.dumps({"success": False, "error": data.get("error", result.stderr or USER_FACING_ERROR)})
        return json.dumps(data, indent=2)
    except json.JSONDecodeError:
        if result.returncode != 0:
            logger.warning("legalkanban_create_task failed: %s", result.stderr)
            return json.dumps({"success": False, "error": result.stderr or USER_FACING_ERROR})
        return json.dumps({"success": True, "message": "Task created."})


# Allowlisted scripts for run_tool: script_name -> path relative to REPO_ROOT
_RUN_TOOL_ALLOWLIST = {
    "daily_brief": "tools/briefings/daily_brief.py",
    "research_brief": "tools/briefings/research_brief.py",
    "local_news": "tools/briefings/local_news.py",
    "news_briefing": "tools/briefings/news_briefing.py",
    "run_heartbeat": "tools/heartbeat/run_heartbeat.py",
}


def _run_tool(inp: dict) -> str:
    script_name = inp.get("script_name", "")
    if script_name not in _RUN_TOOL_ALLOWLIST:
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    script_path = REPO_ROOT / _RUN_TOOL_ALLOWLIST[script_name]
    if not script_path.exists():
        logger.warning("run_tool script not found: %s", script_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    result = _run([sys.executable, str(script_path)])
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        logger.warning("run_tool %s failed (exit %s): %s", script_name, result.returncode, err)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return out or "(no output)"


# ---------------------------------------------------------------------------
# System configuration and automation
# ---------------------------------------------------------------------------

def _telegram_groups(inp: dict) -> str:
    """Query known Telegram groups (autodetected from incoming messages)."""
    try:
        from tools.telegram import group_manager
    except ImportError:
        sys.path.insert(0, str(REPO_ROOT / "tools" / "telegram"))
        import group_manager

    action = inp.get("action", "list")

    if action == "list":
        groups = group_manager.list_groups()
        return json.dumps({
            "success": True,
            "count": len(groups),
            "groups": groups
        }, indent=2)

    elif action == "find":
        name = inp.get("name", "")
        if not name:
            return json.dumps({"success": False, "error": "name is required for find action"})

        group = group_manager.get_group_by_name(name)
        if group:
            return json.dumps({
                "success": True,
                "group": group
            }, indent=2)
        else:
            return json.dumps({
                "success": False,
                "error": f"No group found matching: {name}"
            })

    else:
        return json.dumps({"success": False, "error": f"Unknown action: {action}"})


def _script_writer(inp: dict) -> str:
    """Generate a Python script from natural language description."""
    script_writer_path = REPO_ROOT / "tools" / "system" / "script_writer.py"
    if not script_writer_path.exists():
        logger.warning("script_writer.py not found at %s", script_writer_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    task_description = inp.get("task_description", "")
    output_path = inp.get("output_path", "")
    schedule = inp.get("schedule")

    if not task_description or not output_path:
        return json.dumps({"success": False, "error": "task_description and output_path are required"})

    # Build command
    args = [sys.executable, str(script_writer_path), "--task", task_description, "--output", output_path]
    if schedule:
        args.extend(["--schedule", schedule])

    # Execute
    result = _run(args)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()

    if result.returncode != 0:
        logger.warning("script_writer failed (exit %s): %s", result.returncode, err)
        try:
            error_data = json.loads(out)
            return json.dumps(error_data)
        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": err or out or USER_FACING_ERROR})

    return out or json.dumps({"success": True})


def _conversation_context(inp: dict) -> str:
    """Get conversation history and patterns."""
    try:
        action = inp.get("action", "recent")

        if action == "recent":
            hours = int(inp.get("hours", 24))
            limit = int(inp.get("limit", 20))
            turns = tools.memory.conversation_tracker.get_recent_conversation(hours=hours, limit=limit)
            return json.dumps({"success": True, "turns": turns}, indent=2, default=str)

        elif action == "patterns":
            patterns = tools.memory.conversation_tracker.detect_patterns()
            return json.dumps({"success": True, "patterns": patterns}, indent=2, default=str)

        elif action == "corrections":
            summary = tools.memory.conversation_tracker.get_corrections_summary()
            return json.dumps({"success": True, "corrections": summary}, indent=2, default=str)

        else:
            return json.dumps({"success": False, "error": f"Unknown action: {action}"})

    except Exception as e:
        logger.exception("conversation_tracker failed")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _proactive_intelligence(inp: dict) -> str:
    """Get proactive suggestions and insights."""
    engine_path = REPO_ROOT / "tools" / "intelligence" / "proactive_engine.py"
    if not engine_path.exists():
        logger.warning("proactive_engine.py not found")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    action = inp.get("action", "suggestions")
    args = [sys.executable, str(engine_path), "--action", action]

    if action == "intent" and "text" in inp:
        args.extend(["--text", inp["text"]])

    result = _run(args)
    if result.returncode != 0:
        logger.warning("proactive_engine failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    return result.stdout.strip() or json.dumps({"success": True})


def _log_correction(inp: dict) -> str:
    """Log a user correction for learning."""
    try:
        original = inp.get("original_response", "")
        correction = inp.get("correction", "")
        pattern = inp.get("learned_pattern", "")

        if not original or not correction:
            return json.dumps({"success": False, "error": "original_response and correction required"})

        tools.memory.conversation_tracker.log_correction(original, correction, learned_pattern=pattern)

        # Also save to memory for long-term retention
        memory_write_path = REPO_ROOT / "memory" / "memory_write.py"
        if memory_write_path.exists():
            content = f"Correction learned: {pattern}" if pattern else f"User corrected: {correction}"
            _run([
                sys.executable, str(memory_write_path),
                "--content", content,
                "--type", "insight",
                "--importance", "8",
                "--source", "correction"
            ])

        return json.dumps({"success": True, "message": "Correction logged and learned"})
    except Exception as e:
        logger.exception("log_correction failed")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


def _system_config(inp: dict) -> str:
    """Route system configuration actions to system_config.py via subprocess."""
    config_script = REPO_ROOT / "tools" / "system" / "system_config.py"
    if not config_script.exists():
        logger.warning("system_config.py not found at %s", config_script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    action = inp.get("action", "")
    if not action:
        return json.dumps({"success": False, "error": "action is required."})

    # Build command line arguments
    args = [sys.executable, str(config_script), "--action", action]

    # Map action-specific parameters
    if action == "update_chat_id":
        if "script_name" in inp:
            args.extend(["--script", inp["script_name"]])
        if "chat_id" in inp:
            args.extend(["--chat-id", inp["chat_id"]])

    elif action == "add_cron":
        if "script_path" in inp:
            args.extend(["--script-path", inp["script_path"]])
        if "schedule" in inp:
            args.extend(["--schedule", inp["schedule"]])
        if "comment" in inp:
            args.extend(["--comment", inp["comment"]])

    elif action == "remove_cron":
        if "pattern" in inp:
            args.extend(["--pattern", inp["pattern"]])

    elif action == "update_cron_time":
        if "pattern" in inp:
            args.extend(["--pattern", inp["pattern"]])
        if "schedule" in inp:
            args.extend(["--schedule", inp["schedule"]])

    elif action == "create_youtube_monitor":
        if "youtube_url" in inp:
            args.extend(["--monitor-type", "youtube", "--url", inp["youtube_url"]])
        if "schedule" in inp:
            args.extend(["--schedule", inp["schedule"]])
        if "chat_id" in inp:
            args.extend(["--chat-id", inp["chat_id"]])

    # Execute
    result = _run(args)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()

    if result.returncode != 0:
        logger.warning("system_config %s failed (exit %s): %s", action, result.returncode, err)
        # Try to parse error from output
        try:
            error_data = json.loads(out)
            return json.dumps(error_data)
        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": err or out or USER_FACING_ERROR})

    return out or json.dumps({"success": True})


# ---------------------------------------------------------------------------
# Zapier MCP bridge (Gmail + Google Calendar)
# ---------------------------------------------------------------------------

_ZAPIER_TOOLS = {
    "gmail_create_draft",
    "google_calendar_retrieve_event_by_id",
    "google_calendar_find_events",
    "google_calendar_find_busy_periods_in_calendar",
    "google_calendar_find_calendars",
    "google_calendar_create_detailed_event",
    "google_calendar_move_event_to_another_calendar",
}


def _podcast_create_episode(inp: dict) -> str:
    """Create a new podcast episode from an idea."""
    podcast = inp.get("podcast")
    idea = inp.get("idea")

    if not podcast or not idea:
        return json.dumps({"success": False, "error": "podcast and idea are required"})

    script = REPO_ROOT / "tools" / "podcast" / "idea_processor.py"
    if not script.exists():
        logger.warning("idea_processor.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    args = [
        sys.executable,
        str(script),
        "--podcast", podcast,
        "--idea", idea
    ]

    result = _run(args, cwd=REPO_ROOT)

    if result.returncode != 0:
        logger.warning("podcast_create_episode failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": "Failed to create episode"})

    # Parse episode ID from stdout
    output = result.stdout.strip()
    episode_id = None
    for line in output.split("\n"):
        if "Episode created:" in line or "episode_id" in line.lower():
            # Extract episode ID from output
            parts = line.split(":")
            if len(parts) > 1:
                episode_id = parts[1].strip()
                break

    return json.dumps({
        "success": True,
        "message": "Episode created successfully. Script generation in progress.",
        "episode_id": episode_id,
        "output": output
    })


def _podcast_approve_script(inp: dict) -> str:
    """Approve a podcast script and trigger voice synthesis."""
    episode_id = inp.get("episode_id")
    pronunciation_fixes = inp.get("pronunciation_fixes", {})

    if not episode_id:
        return json.dumps({"success": False, "error": "episode_id is required"})

    # First, copy script_draft.md to script_approved.md
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        episodes_base = Path(config["paths"]["episodes_dir"])

        # Parse episode_id to get directory
        if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
            episode_dir = episodes_base / episode_id
        else:
            parts = episode_id.split("-", 1)
            podcast_name_short = parts[0]
            episode_num = parts[1]
            # Map short name to full name
            podcast_full_name = None
            for name, podcast_config in config["podcasts"].items():
                if name == podcast_name_short:
                    podcast_full_name = podcast_config["name"]
                    break
            if not podcast_full_name:
                return json.dumps({"success": False, "error": f"Unknown podcast: {podcast_name_short}"})
            episode_dir = episodes_base / podcast_full_name / episode_num

        draft_path = episode_dir / "script_draft.md"
        approved_path = episode_dir / "script_approved.md"

        if not draft_path.exists():
            return json.dumps({"success": False, "error": "Script draft not found"})

        # Copy draft to approved (Obsidian)
        import shutil
        shutil.copy2(draft_path, approved_path)

        # Mirror to repo so bot can read/edit
        mirror_dir = REPO_ROOT / "data" / "podcast_episodes" / episode_id
        mirror_draft = mirror_dir / "script_draft.md"
        mirror_approved = mirror_dir / "script_approved.md"
        if mirror_draft.exists():
            shutil.copy2(mirror_draft, mirror_approved)

        # Store one-off pronunciation fixes in state if provided
        if pronunciation_fixes:
            state_path = episode_dir / "state.json"
            if state_path.exists():
                with open(state_path) as f:
                    state = json.load(f)
                state["pronunciation_fixes"] = pronunciation_fixes
                with open(state_path, "w") as f:
                    json.dump(state, f, indent=2)

    except Exception as e:
        logger.exception("Failed to copy script to approved")
        return json.dumps({"success": False, "error": f"Failed to prepare script: {str(e)}"})

    # Now trigger TTS synthesis
    script = REPO_ROOT / "tools" / "podcast" / "tts_synthesizer.py"
    if not script.exists():
        logger.warning("tts_synthesizer.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    args = [
        sys.executable,
        str(script),
        "--episode-id", episode_id
    ]

    # Run with envchain for API keys
    envchain_args = ["/opt/homebrew/bin/envchain", "atlas"] + args
    result = _run(envchain_args, cwd=REPO_ROOT)

    if result.returncode != 0:
        logger.warning("podcast_approve_script (TTS) failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": "Voice synthesis failed", "output": result.stderr.strip()})

    return json.dumps({
        "success": True,
        "message": "Script approved! Voice synthesis and audio mixing complete. Final MP3 sent to Telegram.",
        "episode_id": episode_id
    })


def _podcast_regenerate_voice(inp: dict) -> str:
    """Regenerate voice and audio for an existing episode after manual script edits."""
    episode_id = inp.get("episode_id")
    pronunciation_fixes = inp.get("pronunciation_fixes", {})

    if not episode_id:
        return json.dumps({"success": False, "error": "episode_id is required"})

    # Verify episode exists and has approved script
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        episodes_base = Path(config["paths"]["episodes_dir"])

        # Parse episode_id to get directory
        if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
            episode_dir = episodes_base / episode_id
        else:
            parts = episode_id.split("-", 1)
            podcast_name_short = parts[0]
            episode_num = parts[1]
            # Map short name to full name
            podcast_full_name = None
            for name, podcast_config in config["podcasts"].items():
                if name == podcast_name_short:
                    podcast_full_name = podcast_config["name"]
                    break
            if not podcast_full_name:
                return json.dumps({"success": False, "error": f"Unknown podcast: {podcast_name_short}"})
            episode_dir = episodes_base / podcast_full_name / episode_num

        approved_path = episode_dir / "script_approved.md"

        if not approved_path.exists():
            return json.dumps({"success": False, "error": "No approved script found. Edit the script in Obsidian first."})

        # Store one-off pronunciation fixes in state if provided
        if pronunciation_fixes:
            state_path = episode_dir / "state.json"
            if state_path.exists():
                with open(state_path) as f:
                    state = json.load(f)
                state["pronunciation_fixes"] = pronunciation_fixes
                with open(state_path, "w") as f:
                    json.dump(state, f, indent=2)

    except Exception as e:
        logger.exception("Failed to verify episode")
        return json.dumps({"success": False, "error": f"Failed to verify episode: {str(e)}"})

    # Trigger TTS synthesis
    script = REPO_ROOT / "tools" / "podcast" / "tts_synthesizer.py"
    if not script.exists():
        logger.warning("tts_synthesizer.py not found at %s", script)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    args = [
        sys.executable,
        str(script),
        "--episode-id", episode_id
    ]

    # Run with envchain for API keys
    envchain_args = ["/opt/homebrew/bin/envchain", "atlas"] + args
    result = _run(envchain_args, cwd=REPO_ROOT)

    if result.returncode != 0:
        logger.warning("podcast_regenerate_voice (TTS) failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": "Voice synthesis failed", "output": result.stderr.strip()})

    return json.dumps({
        "success": True,
        "message": "Voice regenerated! Audio mixing complete. Updated MP3 sent to Telegram.",
        "episode_id": episode_id
    })


def _podcast_regenerate_paragraph(inp: dict) -> str:
    """Regenerate a specific paragraph of an episode after manual edits."""
    episode_id = inp.get("episode_id")
    paragraph_number = inp.get("paragraph_number")
    search_term = inp.get("search_term")
    pronunciation_fixes = inp.get("pronunciation_fixes", {})

    if not episode_id:
        return json.dumps({"success": False, "error": "episode_id is required"})

    if paragraph_number is None and not search_term:
        return json.dumps({"success": False, "error": "Either paragraph_number or search_term is required"})

    # Load episode and find paragraph
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        episodes_base = Path(config["paths"]["episodes_dir"])

        # Parse episode_id to get directory
        if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
            episode_dir = episodes_base / episode_id
        else:
            parts = episode_id.split("-", 1)
            podcast_name_short = parts[0]
            episode_num = parts[1]
            # Map short name to full name
            podcast_full_name = None
            for name, podcast_config in config["podcasts"].items():
                if name == podcast_name_short:
                    podcast_full_name = podcast_config["name"]
                    break
            if not podcast_full_name:
                return json.dumps({"success": False, "error": f"Unknown podcast: {podcast_name_short}"})
            episode_dir = episodes_base / podcast_full_name / episode_num

        paragraphs_dir = episode_dir / "paragraphs"
        metadata_file = paragraphs_dir / "paragraph_metadata.json"

        if not metadata_file.exists():
            return json.dumps({"success": False, "error": "No paragraph metadata found. Episode may not use paragraph-based synthesis."})

        with open(metadata_file) as f:
            metadata = json.load(f)

        # Find paragraph to regenerate
        target_paragraph = None

        if paragraph_number is not None:
            # Find by number
            for para in metadata["paragraphs"]:
                if para["number"] == paragraph_number:
                    target_paragraph = para
                    break
        elif search_term:
            # Find by search term in script
            script_path = episode_dir / "script_approved.md"
            if not script_path.exists():
                return json.dumps({"success": False, "error": "Script not found"})

            # Load and process script
            from tools.podcast.tts_synthesizer import strip_script_metadata
            script_text = script_path.read_text(encoding="utf-8")
            script_text = strip_script_metadata(script_text)

            # Apply pronunciation fixes to get the actual text
            from tools.podcast.pronunciation import load_pronunciation_dict, apply_pronunciation_fixes
            pron_dict = load_pronunciation_dict()
            state_path = episode_dir / "state.json"
            one_off_fixes = {}
            if state_path.exists():
                with open(state_path) as f:
                    state = json.load(f)
                    one_off_fixes = state.get("pronunciation_fixes", {})

            script_text, _ = apply_pronunciation_fixes(script_text, pron_dict, one_off_fixes)

            # Split into paragraphs and search
            paragraphs_text = script_text.split('\n\n')
            for i, para_text in enumerate(paragraphs_text):
                if search_term.lower() in para_text.lower():
                    # Find matching paragraph in metadata
                    for para in metadata["paragraphs"]:
                        if para["number"] == i:
                            target_paragraph = para
                            break
                    break

        if not target_paragraph:
            return json.dumps({"success": False, "error": f"Paragraph not found (number={paragraph_number}, search='{search_term}')"})

        # Store one-off pronunciation fixes if provided
        if pronunciation_fixes:
            state_path = episode_dir / "state.json"
            if state_path.exists():
                with open(state_path) as f:
                    state = json.load(f)
                state["pronunciation_fixes"] = pronunciation_fixes
                with open(state_path, "w") as f:
                    json.dump(state, f, indent=2)

    except Exception as e:
        logger.exception("Failed to load paragraph metadata")
        return json.dumps({"success": False, "error": f"Failed to load metadata: {str(e)}"})

    # Trigger paragraph regeneration via tts_synthesizer
    script = REPO_ROOT / "tools" / "podcast" / "regenerate_paragraph.py"
    if not script.exists():
        # For now, use tts_synthesizer with special flag (we'll create dedicated script later)
        logger.warning("regenerate_paragraph.py not found, using full regeneration")
        return _podcast_regenerate_voice({"episode_id": episode_id, "pronunciation_fixes": pronunciation_fixes})

    args = [
        sys.executable,
        str(script),
        "--episode-id", episode_id,
        "--paragraph-number", str(target_paragraph["number"])
    ]

    # Run with envchain for API keys
    envchain_args = ["/opt/homebrew/bin/envchain", "atlas"] + args
    result = _run(envchain_args, cwd=REPO_ROOT)

    if result.returncode != 0:
        logger.warning("podcast_regenerate_paragraph failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": "Paragraph regeneration failed", "output": result.stderr.strip()})

    return json.dumps({
        "success": True,
        "message": f"Paragraph {target_paragraph['number']} regenerated! Audio remixed and sent to Telegram.",
        "episode_id": episode_id,
        "paragraph_number": target_paragraph["number"]
    })


def _schedule_read(inp: dict) -> str:
    """Read the podcast schedule for a given podcast."""
    from datetime import datetime
    from pathlib import Path

    podcast_id = inp.get("podcast_id")
    if not podcast_id:
        return json.dumps({"success": False, "error": "podcast_id required"})

    podcast_configs = {
        "sololaw": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Solo Law Club"),
        "832weekends": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/832 Weekends"),
        "explore": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Explore with Tony")
    }

    if podcast_id not in podcast_configs:
        return json.dumps({"success": False, "error": f"Unknown podcast: {podcast_id}"})

    schedule_file = podcast_configs[podcast_id] / "Schedule.md"
    if not schedule_file.exists():
        return json.dumps({"success": False, "error": f"No schedule found for {podcast_id}"})

    content = schedule_file.read_text()
    return json.dumps({
        "success": True,
        "podcast_id": podcast_id,
        "content": content,
        "message": f"Schedule for {podcast_id} loaded successfully"
    })


def _schedule_preview(inp: dict) -> str:
    """Preview what the schedule will look like with proposed episodes."""
    from datetime import datetime

    podcast_id = inp.get("podcast_id")
    episodes = inp.get("episodes", [])

    if not podcast_id or not episodes:
        return json.dumps({"success": False, "error": "podcast_id and episodes required"})

    # Format episodes based on podcast type
    preview_lines = []

    for ep in episodes:
        date_str = ep.get("date", "")
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%B %d, %Y")
            friday_date = f"Friday, {formatted_date}"
        except:
            formatted_date = date_str
            friday_date = date_str

        title = ep.get("title", "Untitled")
        theme = ep.get("theme")
        key_points = ep.get("key_points", [])
        show_notes = ep.get("show_notes", "")

        if podcast_id == "sololaw":
            preview_lines.append(f"## {friday_date}\n")
            preview_lines.append(f"### {title}\n")
            preview_lines.append("#### Key Discussion Points\n")
            for point in key_points:
                preview_lines.append(f"-   {point}")
            preview_lines.append("\n#### Show Notes\n")
            preview_lines.append(f"{show_notes}\n")
            preview_lines.append("\n" + "-" * 72 + "\n")

        elif podcast_id == "832weekends":
            preview_lines.append(f"## {formatted_date} — {title}")
            if theme:
                preview_lines.append(f"**Theme:** {theme}")
            preview_lines.append("**Key Discussion Points:**")
            for point in key_points:
                preview_lines.append(f"- {point}")
            preview_lines.append("**Show Notes:**")
            preview_lines.append(f"{show_notes}\n")

        elif podcast_id == "explore":
            preview_lines.append(f"### {friday_date}")
            preview_lines.append(f"## Episode: {title}\n")
            preview_lines.append("### Key Discussion Points")
            for point in key_points:
                preview_lines.append(f"- {point}")
            preview_lines.append("\n### Show Notes")
            preview_lines.append(f"{show_notes}\n")
            preview_lines.append("---\n")

    preview = "\n".join(preview_lines)

    return json.dumps({
        "success": True,
        "podcast_id": podcast_id,
        "episode_count": len(episodes),
        "preview": preview,
        "message": f"Preview of {len(episodes)} episodes for {podcast_id}"
    })


def _schedule_add(inp: dict) -> str:
    """Add episodes to the podcast schedule."""
    from datetime import datetime
    from pathlib import Path

    podcast_id = inp.get("podcast_id")
    episodes = inp.get("episodes", [])

    if not podcast_id or not episodes:
        return json.dumps({"success": False, "error": "podcast_id and episodes required"})

    podcast_configs = {
        "sololaw": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Solo Law Club"),
        "832weekends": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/832 Weekends"),
        "explore": Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Explore with Tony")
    }

    if podcast_id not in podcast_configs:
        return json.dumps({"success": False, "error": f"Unknown podcast: {podcast_id}"})

    schedule_file = podcast_configs[podcast_id] / "Schedule.md"

    # Read existing content (or create header if file doesn't exist)
    if schedule_file.exists():
        existing_content = schedule_file.read_text()
        # Remove trailing newlines
        existing_content = existing_content.rstrip()
    else:
        if podcast_id == "sololaw":
            existing_content = "# Solo Law Club -- 12 Week Roadmap\n\nPublishing Day: Fridays"
        elif podcast_id == "832weekends":
            existing_content = "# 12-Week Podcast Schedule: Eight Hundred and Thirty-Two Weekends"
        elif podcast_id == "explore":
            existing_content = "# Explore with Tony – 12 Week Content Plan\n\n---"

    # Format new episodes
    new_lines = []

    for ep in episodes:
        date_str = ep.get("date", "")
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%B %d, %Y")
            friday_date = f"Friday, {formatted_date}"
        except:
            formatted_date = date_str
            friday_date = date_str

        title = ep.get("title", "Untitled")
        theme = ep.get("theme")
        key_points = ep.get("key_points", [])
        show_notes = ep.get("show_notes", "")

        if podcast_id == "sololaw":
            new_lines.append(f"\n## {friday_date}\n")
            new_lines.append(f"### {title}\n")
            new_lines.append("#### Key Discussion Points\n")
            for point in key_points:
                new_lines.append(f"-   {point}")
            new_lines.append("\n#### Show Notes\n")
            new_lines.append(f"{show_notes}\n")
            new_lines.append("\n" + "-" * 72 + "\n")

        elif podcast_id == "832weekends":
            new_lines.append(f"\n## {formatted_date} — {title}")
            if theme:
                new_lines.append(f"**Theme:** {theme}")
            new_lines.append("**Key Discussion Points:**")
            for point in key_points:
                new_lines.append(f"- {point}")
            new_lines.append("**Show Notes:**")
            new_lines.append(f"{show_notes}\n")

        elif podcast_id == "explore":
            new_lines.append(f"\n### {friday_date}")
            new_lines.append(f"## Episode: {title}\n")
            new_lines.append("### Key Discussion Points")
            for point in key_points:
                new_lines.append(f"- {point}")
            new_lines.append("\n### Show Notes")
            new_lines.append(f"{show_notes}\n")
            new_lines.append("---\n")

    # Append to existing content
    updated_content = existing_content + "\n" + "\n".join(new_lines)

    # Write back
    schedule_file.write_text(updated_content)

    return json.dumps({
        "success": True,
        "podcast_id": podcast_id,
        "episode_count": len(episodes),
        "file": str(schedule_file),
        "message": f"Added {len(episodes)} episodes to {podcast_id} schedule!"
    })


def _script_writer(inp: dict) -> str:
    """Generate, save, or validate Python scripts."""
    script_path = REPO_ROOT / "tools" / "system" / "script_writer.py"
    if not script_path.exists():
        logger.warning("script_writer.py not found at %s", script_path)
        return json.dumps({"status": "error", "message": "Script writer tool not found"})

    action = inp.get("action")
    if not action:
        return json.dumps({"status": "error", "message": "action parameter required"})

    args = [sys.executable, str(script_path), action]

    if action == "generate":
        description = inp.get("description", "")
        if not description:
            return json.dumps({"status": "error", "message": "description required for generate action"})

        args.append(description)

        # Add optional imports
        imports = inp.get("imports", [])
        if imports:
            args.extend(["--imports", ",".join(imports)])

        # Add envchain flag if needed
        if inp.get("use_envchain", False):
            args.append("--envchain")

    elif action == "save":
        filename = inp.get("filename")
        code = inp.get("code")

        if not filename or not code:
            return json.dumps({"status": "error", "message": "filename and code required for save action"})

        args.extend([filename, code])

    elif action == "validate":
        code = inp.get("code")
        if not code:
            return json.dumps({"status": "error", "message": "code required for validate action"})

        args.append(code)

    else:
        return json.dumps({"status": "error", "message": f"Unknown action: {action}"})

    result = _run(args)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()

    if result.returncode != 0:
        logger.warning("script_writer %s failed (exit %s): %s", action, result.returncode, err)
        try:
            # Try to parse error from stdout
            error_data = json.loads(out)
            return json.dumps(error_data)
        except:
            return json.dumps({"status": "error", "message": f"Script writer failed: {err or 'unknown error'}"})

    return out or "{}"


def _launchd_manager(inp: dict) -> str:
    """Create, load, unload, or list launchd jobs."""
    manager_path = REPO_ROOT / "tools" / "system" / "launchd_manager.py"
    if not manager_path.exists():
        logger.warning("launchd_manager.py not found at %s", manager_path)
        return json.dumps({"status": "error", "message": "Launchd manager tool not found"})

    action = inp.get("action")
    if not action:
        return json.dumps({"status": "error", "message": "action parameter required"})

    args = [sys.executable, str(manager_path), action]

    if action == "create":
        script_path = inp.get("script_path")
        label = inp.get("label")

        if not script_path or not label:
            return json.dumps({"status": "error", "message": "script_path and label required for create action"})

        args.extend(["--script", script_path, "--label", label])

        # Add optional schedule
        schedule = inp.get("schedule")
        if schedule:
            args.extend(["--schedule", schedule])

        # Add optional description
        description = inp.get("description", "")
        if description:
            args.extend(["--description", description])

        # Add run-at-load flag
        if inp.get("run_at_load", False):
            args.append("--run-at-load")

    elif action in ["load", "unload"]:
        label = inp.get("label")
        if not label:
            return json.dumps({"status": "error", "message": f"label required for {action} action"})

        args.append(label)

    elif action == "list":
        # No additional args needed
        pass

    else:
        return json.dumps({"status": "error", "message": f"Unknown action: {action}"})

    result = _run(args)
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()

    if result.returncode != 0:
        logger.warning("launchd_manager %s failed (exit %s): %s", action, result.returncode, err)
        try:
            # Try to parse error from stdout
            error_data = json.loads(out)
            return json.dumps(error_data)
        except:
            return json.dumps({"status": "error", "message": f"Launchd manager failed: {err or 'unknown error'}"})

    return out or "{}"


def _zapier(tool_name: str, inp: dict) -> str:
    """Route a Zapier tool call to zapier_runner.py via subprocess."""
    runner_path = REPO_ROOT / "tools" / "zapier" / "zapier_runner.py"
    if not runner_path.exists():
        logger.warning("zapier_runner.py not found at %s", runner_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    result = _run([sys.executable, str(runner_path), "--tool", tool_name, "--input", json.dumps(inp)])
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        logger.warning("zapier %s failed (exit %s): %s", tool_name, result.returncode, err)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return out or "(no output)"
