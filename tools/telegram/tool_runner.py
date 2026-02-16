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


async def _run(args: list, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    """Run a subprocess with the given args. Returns the CompletedProcess."""
    return await asyncio.to_thread(
        subprocess.run,
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


async def execute(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool by name with the given input dict from Claude's tool_use block.

    Returns a string result to feed back to Claude as a tool_result.
    """
    try:
        if tool_name == "memory_read":
            return await _memory_read(tool_input)
        elif tool_name == "memory_write":
            return await _memory_write(tool_input)
        elif tool_name == "memory_search":
            return await _memory_search(tool_input)
        elif tool_name == "memory_db":
            return await _memory_db(tool_input)
        elif tool_name == "read_goal":
            return await _read_goal(tool_input)
        elif tool_name == "journal_read_recent":
            return await _journal_read_recent(tool_input)
        elif tool_name == "reminders_read":
            return await _reminders_read()
        elif tool_name == "heartbeat_read":
            return await _heartbeat_read()
        elif tool_name == "trial_read_guide":
            return await _trial_read_guide()
        elif tool_name == "trial_list_cases":
            return await _trial_list_cases()
        elif tool_name == "trial_list_templates":
            return await _trial_list_templates()
        elif tool_name == "trial_read_template":
            return await _trial_read_template(tool_input)
        elif tool_name == "trial_save_document":
            return await _trial_save_document(tool_input)
        elif tool_name == "read_file":
            return await _read_file(tool_input)
        elif tool_name == "list_files":
            return await _list_files(tool_input)
        elif tool_name == "reminder_add":
            return await _reminder_add(tool_input)
        elif tool_name == "bambu":
            return await _bambu(tool_input)
        elif tool_name == "browser_search":
            return await _browser_search(tool_input)
        elif tool_name == "run_tool":
            return await _run_tool(tool_input)
        elif tool_name == "browser":
            return await _browser(tool_input)
        elif tool_name == "web_search":
            return await _web_search(tool_input)
        elif tool_name == "system_config":
            return await _system_config(tool_input)
        elif tool_name == "telegram_groups":
            return await _telegram_groups(tool_input)
        elif tool_name == "conversation_context":
            return await _conversation_context(tool_input)
        elif tool_name == "proactive_intelligence":
            return await _proactive_intelligence(tool_input)
        elif tool_name == "log_correction":
            return await _log_correction(tool_input)
        elif tool_name in _ZAPIER_TOOLS:
            return await _zapier(tool_name, tool_input)
        else:
            return json.dumps({"success": False, "error": USER_FACING_ERROR})
    except Exception as e:
        logger.exception("Tool runner exception")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


# ---------------------------------------------------------------------------
# Individual tool translators
# ---------------------------------------------------------------------------

async def _memory_read(inp: dict) -> str:
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
        # Use asyncio.to_thread because load_all_memory does blocking I/O
        context = await asyncio.to_thread(
            memory.memory_read.load_all_memory,
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


async def _memory_write(inp: dict) -> str:
    """
    Directly call memory.memory_write functions to avoid subprocess overhead.
    """
    def write_op():
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

    return await asyncio.to_thread(write_op)


async def _memory_search(inp: dict) -> str:
    args = [sys.executable, "memory/hybrid_search.py"]

    args.extend(["--query", inp["query"]])

    if "limit" in inp:
        args.extend(["--limit", str(inp["limit"])])
    if inp.get("keyword_only", True):
        args.append("--keyword-only")
    if "type" in inp:
        args.extend(["--type", inp["type"]])

    result = await _run(args)
    if result.returncode != 0:
        logger.warning("memory_search failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return _parse_output(result.stdout)


async def _memory_db(inp: dict) -> str:
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

    result = await _run(args)
    if result.returncode != 0:
        logger.warning("memory_db failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return _parse_output(result.stdout)


async def _read_goal(inp: dict) -> str:
    filename = inp.get("filename", "")
    goals_dir = REPO_ROOT / "goals"

    # Path traversal guard: resolve and check it stays inside goals/
    target = (goals_dir / filename).resolve()
    if not target.is_relative_to(goals_dir.resolve()):
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    if not target.exists():
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    return await asyncio.to_thread(target.read_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Journal (read-only; Obsidian export CSV)
# ---------------------------------------------------------------------------

_DEFAULT_JOURNAL_CSV_PATH = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Journals/journal-entries-2025-01-01-to-2026-01-31.csv")


async def _journal_read_recent(inp: dict) -> str:
    """Read the last N days of journal entries from the Obsidian journal CSV. Read-only."""
    path = _resolve_path("journal_csv", _DEFAULT_JOURNAL_CSV_PATH)
    if not path.exists():
        return json.dumps({"success": False, "error": "Journal export not found.", "entries": []})

    days = max(1, min(31, int(inp.get("days", 7))))

    try:
        def read_csv():
            with path.open(newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))

        rows = await asyncio.to_thread(read_csv)
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


async def _reminders_read() -> str:
    """Read Tony Reminders.md by section. Read-only; same sections as reminder_add."""
    path = _resolve_path("reminders", _DEFAULT_REMINDERS_PATH)
    if not path.exists():
        return json.dumps({"success": True, "message": "Reminders file not found.", "sections": {}})

    try:
        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
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


async def _heartbeat_read() -> str:
    """Read HEARTBEAT.md checklist and heartbeat-state.json. Read-only."""
    checklist = []
    if HEARTBEAT_MD.exists():
        try:
            content = await asyncio.to_thread(HEARTBEAT_MD.read_text, encoding="utf-8")
            lines = content.strip().splitlines()
            checklist = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        except OSError as e:
            logger.warning("heartbeat_read HEARTBEAT.md failed: %s", e)

    state = {}
    if HEARTBEAT_STATE.exists():
        try:
            content = await asyncio.to_thread(HEARTBEAT_STATE.read_text, encoding="utf-8")
            state = json.loads(content)
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


async def _trial_read_guide() -> str:
    path = _trial_safe_path("Case Prep Guide.md")
    if not path or not path.is_file():
        return json.dumps({"success": False, "error": "Case Prep Guide not found."})
    return await asyncio.to_thread(path.read_text, encoding="utf-8")


async def _trial_list_cases() -> str:
    if not TRIALS_ROOT.exists():
        return json.dumps({"success": False, "error": "Trials folder not found."})

    def list_cases():
        out: dict[str, list[str]] = {}
        for year_dir in sorted(TRIALS_ROOT.iterdir()):
            if year_dir.is_dir() and year_dir.name.isdigit() and len(year_dir.name) == 4:
                cases = [d.name for d in year_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
                if cases:
                    out[year_dir.name] = sorted(cases)
        return out

    out = await asyncio.to_thread(list_cases)
    return json.dumps(out, indent=2)


async def _trial_list_templates() -> str:
    templates_dir = _trial_safe_path("Templates")
    if not templates_dir or not templates_dir.is_dir():
        return json.dumps({"success": False, "error": "Templates folder not found."})

    def list_tmpl():
        names = [f.name for f in templates_dir.iterdir() if f.suffix == ".md"]
        return names

    names = await asyncio.to_thread(list_tmpl)
    return json.dumps({"templates": sorted(names)})


async def _trial_read_template(inp: dict) -> str:
    name = (inp.get("template_name") or "").strip()
    if not name:
        return json.dumps({"success": False, "error": "template_name required."})
    # No path traversal: only basename
    if "/" in name or "\\" in name or name.startswith("."):
        return json.dumps({"success": False, "error": "Invalid template name."})
    path = _trial_safe_path("Templates", name)
    if not path or not path.is_file():
        return json.dumps({"success": False, "error": f"Template not found: {name}"})
    return await asyncio.to_thread(path.read_text, encoding="utf-8")


async def _trial_save_document(inp: dict) -> str:
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
        def save():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        await asyncio.to_thread(save)
        return json.dumps({"success": True, "path": str(path)})
    except Exception as e:
        logger.warning("trial_save_document failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


async def _bambu(inp: dict) -> str:
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
        # Note: using subprocess.run with timeout=15 in thread
        def run_cli():
            return subprocess.run(_CMD_MAP[action], capture_output=True, text=True, timeout=15)

        result = await asyncio.to_thread(run_cli)
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


async def _browser_search(inp: dict) -> str:
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

    def fetch():
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.read().decode("utf-8")

    try:
        body = await asyncio.to_thread(fetch)
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


async def _browser(inp: dict) -> str:
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
    result = await _run(args)
    if result.returncode != 0:
        logger.warning("browser failed: %s", result.stderr.strip())
    return _parse_output(result.stdout)


async def _web_search(inp: dict) -> str:
    """Search the web via Brave Search API. Requires BRAVE_API_KEY in .env."""
    script_path = REPO_ROOT / "tools" / "research" / "web_search.py"
    if not script_path.exists():
        logger.warning("web_search.py not found at %s", script_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    args = [sys.executable, str(script_path), "--query", inp["query"]]
    if inp.get("count") is not None:
        args.extend(["--count", str(inp["count"])])
    result = await _run(args)
    if result.returncode != 0:
        logger.warning("web_search failed: %s", result.stderr.strip())
    return _parse_output(result.stdout)


async def _read_file(inp: dict) -> str:
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
        return json.dumps({"success": False, "error": f"File not found: {raw}"})
    try:
        return await asyncio.to_thread(target.read_text, encoding="utf-8")
    except OSError as e:
        logger.warning("read_file failed: %s", e)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})


async def _list_files(inp: dict) -> str:
    """List directory contents inside the repo. Path traversal guarded to REPO_ROOT."""
    raw = (inp.get("path") or "").strip()
    target = (REPO_ROOT / raw).resolve() if raw else REPO_ROOT.resolve()
    try:
        target.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return json.dumps({"success": False, "error": "Path is outside the repo."})
    if not target.is_dir():
        return json.dumps({"success": False, "error": f"Directory not found: {raw or '(root)'}"})

    def list_dir():
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        items = []
        for p in entries:
            if p.name.startswith("."):
                continue
            items.append({"name": p.name, "type": "dir" if p.is_dir() else "file"})
        return items

    items = await asyncio.to_thread(list_dir)
    return json.dumps({"success": True, "path": raw or ".", "entries": items}, indent=2)


async def _reminder_add(inp: dict) -> str:
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
    result = await _run(args)
    if result.returncode != 0:
        logger.warning("reminder_add failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    msg = result.stdout.strip() or "Reminder added."
    return json.dumps({"success": True, "message": msg})


# Allowlisted scripts for run_tool: script_name -> path relative to REPO_ROOT
_RUN_TOOL_ALLOWLIST = {
    "daily_brief": "tools/briefings/daily_brief.py",
    "research_brief": "tools/briefings/research_brief.py",
    "local_news": "tools/briefings/local_news.py",
    "news_briefing": "tools/briefings/news_briefing.py",
    "run_heartbeat": "tools/heartbeat/run_heartbeat.py",
}


async def _run_tool(inp: dict) -> str:
    script_name = inp.get("script_name", "")
    if script_name not in _RUN_TOOL_ALLOWLIST:
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    script_path = REPO_ROOT / _RUN_TOOL_ALLOWLIST[script_name]
    if not script_path.exists():
        logger.warning("run_tool script not found: %s", script_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    result = await _run([sys.executable, str(script_path)])
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        logger.warning("run_tool %s failed (exit %s): %s", script_name, result.returncode, err)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return out or "(no output)"


# ---------------------------------------------------------------------------
# System configuration and automation
# ---------------------------------------------------------------------------

async def _telegram_groups(inp: dict) -> str:
    """Query known Telegram groups (autodetected from incoming messages)."""

    # Offload import and execution to thread
    def run_groups():
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

    return await asyncio.to_thread(run_groups)


async def _script_writer(inp: dict) -> str:
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
    result = await _run(args)
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


async def _conversation_context(inp: dict) -> str:
    """Get conversation history and patterns."""
    tracker_path = REPO_ROOT / "tools" / "memory" / "conversation_tracker.py"
    if not tracker_path.exists():
        logger.warning("conversation_tracker.py not found")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    action = inp.get("action", "recent")
    args = [sys.executable, str(tracker_path), "--action", action]

    if action == "recent":
        if "hours" in inp:
            args.extend(["--hours", str(inp["hours"])])
        if "limit" in inp:
            args.extend(["--limit", str(inp["limit"])])

    result = await _run(args)
    if result.returncode != 0:
        logger.warning("conversation_tracker failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    return result.stdout.strip() or json.dumps({"success": True})


async def _proactive_intelligence(inp: dict) -> str:
    """Get proactive suggestions and insights."""
    engine_path = REPO_ROOT / "tools" / "intelligence" / "proactive_engine.py"
    if not engine_path.exists():
        logger.warning("proactive_engine.py not found")
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    action = inp.get("action", "suggestions")
    args = [sys.executable, str(engine_path), "--action", action]

    if action == "intent" and "text" in inp:
        args.extend(["--text", inp["text"]])

    result = await _run(args)
    if result.returncode != 0:
        logger.warning("proactive_engine failed: %s", result.stderr.strip())
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    return result.stdout.strip() or json.dumps({"success": True})


async def _log_correction(inp: dict) -> str:
    """Log a user correction for learning."""
    try:
        original = inp.get("original_response", "")
        correction = inp.get("correction", "")
        pattern = inp.get("learned_pattern", "")

        if not original or not correction:
            return json.dumps({"success": False, "error": "original_response and correction required"})

        def log():
            sys.path.insert(0, str(REPO_ROOT / "tools" / "memory"))
            from conversation_tracker import log_correction
            log_correction(original, correction, learned_pattern=pattern)

        await asyncio.to_thread(log)

        # Also save to memory for long-term retention
        memory_write_path = REPO_ROOT / "memory" / "memory_write.py"
        if memory_write_path.exists():
            content = f"Correction learned: {pattern}" if pattern else f"User corrected: {correction}"
            await _run([
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


async def _system_config(inp: dict) -> str:
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
    result = await _run(args)
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


async def _zapier(tool_name: str, inp: dict) -> str:
    """Route a Zapier tool call to zapier_runner.py via subprocess."""
    runner_path = REPO_ROOT / "tools" / "zapier" / "zapier_runner.py"
    if not runner_path.exists():
        logger.warning("zapier_runner.py not found at %s", runner_path)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})

    result = await _run([sys.executable, str(runner_path), "--tool", tool_name, "--input", json.dumps(inp)])
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        logger.warning("zapier %s failed (exit %s): %s", tool_name, result.returncode, err)
        return json.dumps({"success": False, "error": USER_FACING_ERROR})
    return out or "(no output)"
