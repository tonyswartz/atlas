"""
Tool runner.

Translates Claude's tool_use requests into subprocess calls against the existing
memory scripts and goal files. Parses their stdout back into strings for Claude.

All subprocess calls use arg lists (never shell=True) to prevent injection.
Tool failures return a generic user-facing message; real errors are logged.
"""

import csv
import json
import logging
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
logger = logging.getLogger(__name__)

USER_FACING_ERROR = "Operation failed. Please try again."


def _run(args: list, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    """Run a subprocess with the given args. Returns the CompletedProcess."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=cwd
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


def execute(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool by name with the given input dict from Claude's tool_use block.

    Returns a string result to feed back to Claude as a tool_result.
    """
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
        elif tool_name == "kanban_read":
            return _kanban_read()
        elif tool_name == "journal_read_recent":
            return _journal_read_recent(tool_input)
        elif tool_name == "reminders_read":
            return _reminders_read()
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
        elif tool_name == "read_file":
            return _read_file(tool_input)
        elif tool_name == "list_files":
            return _list_files(tool_input)
        elif tool_name == "reminder_add":
            return _reminder_add(tool_input)
        elif tool_name == "kanban_write":
            return _kanban_write(tool_input)
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
    args = [sys.executable, "memory/memory_write.py"]

    args.extend(["--content", inp["content"]])

    if "type" in inp:
        args.extend(["--type", inp["type"]])
    if "importance" in inp:
        args.extend(["--importance", str(inp["importance"])])
    if "source" in inp:
        args.extend(["--source", inp["source"]])
    if "tags" in inp:
        args.extend(["--tags", inp["tags"]])

    # Persist to MEMORY.md if requested
    if inp.get("update_memory_md"):
        args.append("--update-memory")
        if "section" in inp:
            args.extend(["--section", inp["section"]])

    result = _run(args)
    if result.returncode != 0:
        logger.warning("memory_write failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return _parse_output(result.stdout)


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
# Kanban (read-only; tasks live in clawd)
# ---------------------------------------------------------------------------

_DEFAULT_KANBAN_PATH = Path("/Users/printer/clawd/kanban/tasks.json")


def _kanban_read() -> str:
    """Read To-Do, In Progress, Backlog from tasks.json. Read-only."""
    path = _resolve_path("kanban", _DEFAULT_KANBAN_PATH)
    if not path.exists():
        return json.dumps({"success": True, "message": "No Kanban file found.", "todo": [], "in_progress": [], "backlog": []})

    try:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)
        tasks = obj["tasks"] if isinstance(obj, dict) and "tasks" in obj else (obj if isinstance(obj, list) else [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("kanban_read failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    def bucket(status: str) -> list[str]:
        s = status.lower()
        return [t.get("title") or t.get("id") or "Untitled" for t in tasks if (t.get("status") or "").lower() == s]

    out = {
        "success": True,
        "todo": bucket("todo"),
        "in_progress": bucket("in_progress"),
        "backlog": bucket("backlog"),
    }
    return json.dumps(out, indent=2)


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
    args = [sys.executable, str(script_path), "--query", inp["query"]]
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
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return json.dumps({"success": False, "error": "Path is outside the repo."})
    if not target.is_file():
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


def _kanban_write(inp: dict) -> str:
    """Add or move a task in tasks.json. Read-modify-write with atomic swap."""
    action = (inp.get("action") or "").strip().lower()
    status = (inp.get("status") or "").strip().lower()
    if action not in ("add", "move") or status not in ("todo", "in_progress", "backlog"):
        return json.dumps({"success": False, "error": "Invalid action or status."})

    path = _resolve_path("kanban", _DEFAULT_KANBAN_PATH)
    if not path.exists():
        # Bootstrap empty file on first add
        if action == "add":
            obj = {"tasks": []}
        else:
            return json.dumps({"success": False, "error": "Kanban file not found."})
    else:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("kanban_write read failed: %s", e)
            return json.dumps({"success": False, "error": USER_FACING_ERROR})

    tasks = obj.get("tasks", []) if isinstance(obj, dict) else []

    if action == "add":
        title = (inp.get("title") or "").strip()
        if not title:
            return json.dumps({"success": False, "error": "title is required for add."})
        import uuid
        new_task = {"id": str(uuid.uuid4())[:8], "title": title, "status": status}
        tasks.append(new_task)
        obj["tasks"] = tasks
        try:
            path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        except OSError as e:
            logger.warning("kanban_write write failed: %s", e)
            return json.dumps({"success": False, "error": USER_FACING_ERROR})
        return json.dumps({"success": True, "message": f"Added '{title}' to {status}.", "task": new_task})

    # action == "move"
    task_id = (inp.get("task_id") or "").strip()
    if not task_id:
        return json.dumps({"success": False, "error": "task_id is required for move."})
    matched = [t for t in tasks if t.get("id") == task_id]
    if not matched:
        return json.dumps({"success": False, "error": f"Task not found: {task_id}"})
    matched[0]["status"] = status
    obj["tasks"] = tasks
    try:
        path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("kanban_write write failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return json.dumps({"success": True, "message": f"Moved '{matched[0].get('title', task_id)}' to {status}."})


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
