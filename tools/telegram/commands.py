"""
Slash-command router.

All /commands are intercepted here BEFORE the message reaches the LLM.
Returns a reply string if the command was handled, or None to fall through
to the conversation handler.

Adding a new command:
  1. Write a _cmd_foo(arg) -> str handler below.
  2. Add "foo" to the DISPATCH dict.
  3. Add a line to HELP_TEXT.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Default admin chat ID (can restart when bot allowlist is empty). Same as briefing target.
_RESTART_ALLOWED_DEFAULT_ID = 8241581699
LAUNCH_AGENT_LABEL = "com.atlas.telegram-bot"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # atlas/
VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
TZ = ZoneInfo("America/Los_Angeles")

# ---------------------------------------------------------------------------
# Capture targets  (slash-command name → Obsidian file)
# ---------------------------------------------------------------------------
CAPTURE_NOTES: dict[str, Path] = {
    "random": VAULT / "Saved" / "Random Ideas.md",
    "travel": VAULT / "Travel" / "Travel Ideas.md",
    "quote":  VAULT / "Saved" / "Quotes.md",
    "link":   VAULT / "Saved" / "Links.md",
    "gift":   VAULT / "Saved" / "Gifts.md",
    "food":   VAULT / "Saved" / "Foods.md",
}

# Plural → singular normalisation
_CAPTURE_ALIASES = {k + "s": k for k in CAPTURE_NOTES}

# ---------------------------------------------------------------------------
# Allowlisted scripts for /run  (mirrors tool_runner._RUN_TOOL_ALLOWLIST)
# ---------------------------------------------------------------------------
RUN_ALLOWLIST: dict[str, str] = {
    "daily_brief":          "tools/briefings/daily_brief.py",
    "research_brief":       "tools/briefings/research_brief.py",
    "weekly_review":        "tools/briefings/weekly_review.py",
    "local_news":           "tools/briefings/local_news.py",
    "news_briefing":        "tools/briefings/news_briefing.py",
    "run_heartbeat":        "tools/heartbeat/run_heartbeat.py",
}

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
_CMD_RE = re.compile(r"^\s*/(\w+)\b\s*(.*)$", re.S | re.I)


def _parse(text: str) -> tuple[str, str] | None:
    """Return (normalised command, arg text) or None."""
    m = _CMD_RE.match(text.strip())
    if not m:
        return None
    cmd = m.group(1).lower()
    arg = (m.group(2) or "").strip()
    cmd = _CAPTURE_ALIASES.get(cmd, cmd)
    return cmd, arg


# ---------------------------------------------------------------------------
# OpenRouter categorisation  (for /random and /travel only)
# ---------------------------------------------------------------------------
def _openrouter_key() -> str | None:
    """Load key from .env, fall back to legacy clawdbot auth profile."""
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.upper().startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    legacy = Path.home() / ".clawdbot/agents/main/agent/auth-profiles.json"
    if legacy.exists():
        try:
            prof = json.loads(legacy.read_text()).get("profiles", {}).get("openrouter:default", {})
            if prof.get("type") == "api_key":
                return prof.get("key")
        except Exception:
            pass
    return None


def _openrouter_chat(system: str, user_text: str) -> str | None:
    import urllib.request
    key = _openrouter_key()
    if not key:
        return None
    payload = json.dumps({
        "model": "openrouter/devstral-2-2512:free",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_text},
        ],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return (((json.loads(resp.read()).get("choices") or [{}])[0].get("message") or {}).get("content"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Capture logic  (/random /travel /quote /link /gift /food)
# ---------------------------------------------------------------------------
_TRAVEL_SYSTEM = (
    'You categorize travel ideas by country. '
    'Return ONLY valid JSON: {"country": string, "clean": string}. '
    'country must be one of: USA, Canada, Mexico, Japan, UK, France, Italy, Spain, '
    'Portugal, Germany, Iceland, Australia / NZ, Europe (general), Other / Unknown. '
    'clean should be a concise bullet text (keep any links).'
)

_RANDOM_SYSTEM = (
    'You categorize general random ideas aggressively. '
    'Return ONLY valid JSON: {"category": string, "clean": string}. '
    'category must be one of: Business / Work, Systems / Automation, Personal, '
    'Writing / Content, Legal / Swartz Law, Rotary / Community, Health / Fitness, '
    'Tech / Gear, Money, Questions to revisit. '
    'clean should be a concise bullet text (keep any links).'
)


def _insert_bullet(note: str, section: str, bullet: str) -> str:
    """Insert `- bullet` under the first `## section` heading. Appends section if missing."""
    lines = note.splitlines(True)
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip() == f"## {section}":
            out.append(f"- {bullet}\n")
            inserted = True
    if not inserted:
        if note and not note.endswith("\n"):
            out.append("\n")
        out.append(f"\n## {section}\n- {bullet}\n")
    return "".join(out)


def _cmd_capture(kind: str, raw: str) -> str:
    path = CAPTURE_NOTES[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# {path.stem}\n\n## Inbox\n- \n")

    today = datetime.now(TZ).strftime("%y-%m-%d")
    section, bullet_text = "Inbox", raw

    # AI categorisation for travel and random only
    if kind == "travel":
        resp = _openrouter_chat(_TRAVEL_SYSTEM, raw)
        if resp:
            try:
                obj = json.loads(resp)
                section    = str(obj.get("country") or "Other / Unknown")
                bullet_text = str(obj.get("clean")    or raw).strip()
            except Exception:
                pass
    elif kind == "random":
        resp = _openrouter_chat(_RANDOM_SYSTEM, raw)
        if resp:
            try:
                obj = json.loads(resp)
                section    = str(obj.get("category") or "Inbox")
                bullet_text = str(obj.get("clean")    or raw).strip()
            except Exception:
                pass

    existing = path.read_text()
    path.write_text(_insert_bullet(existing, section, f"{today} — {bullet_text}"))
    return f"Saved ✓ → {path.relative_to(VAULT)} [{section}]"


# ---------------------------------------------------------------------------
# /rotary — generate next meeting agenda
# ---------------------------------------------------------------------------
_ROTARY_DIR      = VAULT / "Rotary"
_ROTARY_LOG      = _ROTARY_DIR / "Rotary Log.md"
_ROTARY_TEMPLATE = _ROTARY_DIR / "Templates" / "Agenda Template.md"
_ROTARY_MEETINGS = _ROTARY_DIR / "Meetings"


def _parse_rotary_log(text: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Return (spotlights, speakers) keyed by 'M/D' date string."""
    spotlights: dict[str, str] = {}
    speakers:   dict[str, dict[str, str]] = {}
    current: str | None = None

    for line in text.splitlines():
        s = line.strip()
        if s == "## Member Spotlight Schedule":
            current = "spotlight"; continue
        if s == "## Speaker Schedule":
            current = "speaker"; continue
        if s.startswith("##"):
            current = None; continue

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


def _cmd_rotary() -> str:
    if not _ROTARY_LOG.exists():
        return "Rotary Log.md not found."
    if not _ROTARY_TEMPLATE.exists():
        return "Agenda Template.md not found."

    spotlights, speakers = _parse_rotary_log(_ROTARY_LOG.read_text())
    template = _ROTARY_TEMPLATE.read_text()
    today = datetime.now(TZ).date()

    # Find nearest upcoming (or today) meeting date from the schedule
    best_date = None
    best_key:  str | None = None
    for key in spotlights:
        try:
            month, day = (int(x) for x in key.split("/"))
            candidate = today.replace(month=month, day=day)
            if candidate < today:
                candidate = candidate.replace(year=today.year + 1)
            if best_date is None or candidate < best_date:
                best_date  = candidate
                best_key   = key
        except Exception:
            continue

    if not best_date or not best_key:
        return "No upcoming meeting dates found in Rotary Log."

    spotlight = spotlights.get(best_key, "[TBD]")
    speaker   = speakers.get(best_key, {"name": "[TBD]", "topic": "[TBD]"})

    agenda = template.replace("{{DATE}}",              best_date.strftime("%A, %B %d, %Y"))
    agenda = agenda.replace("[insert member name]",    spotlight)
    agenda = agenda.replace("[insert speaker name]",   speaker["name"])
    agenda = agenda.replace("[insert speaker topic]",  speaker["topic"])

    # Save to Meetings/YY/MM/DD Agenda.md  (matches existing structure)
    out_dir  = _ROTARY_MEETINGS / best_date.strftime("%y") / best_date.strftime("%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{best_date.strftime('%d')} Agenda.md"
    out_file.write_text(agenda)

    rel = out_file.relative_to(VAULT)
    return f"Agenda saved → {rel}\n\n{agenda}"


# ---------------------------------------------------------------------------
# /run — execute an allowlisted script
# ---------------------------------------------------------------------------
def _cmd_run(script_name: str) -> str:
    if not script_name:
        return "Usage: /run <script>\nAvailable: " + ", ".join(sorted(RUN_ALLOWLIST))
    if script_name not in RUN_ALLOWLIST:
        return f"Unknown script: {script_name}\nAvailable: " + ", ".join(sorted(RUN_ALLOWLIST))

    path = REPO_ROOT / RUN_ALLOWLIST[script_name]
    if not path.exists():
        return f"Script not found: {path}"

    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True,
            cwd=str(REPO_ROOT), timeout=120,
        )
    except subprocess.TimeoutExpired:
        return f"{script_name} timed out (120 s)."

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode != 0:
        return f"{script_name} failed:\n{err or out or '(no output)'}"
    return out or "(no output)"


# ---------------------------------------------------------------------------
# /reminder — add reminder to Tony Reminders.md with optional due/recurrence
# ---------------------------------------------------------------------------
_REMINDER_BRACKET_RE = re.compile(r"^(.*?)\s*\[([^\]]+)\]\s*$")


def _cmd_reminder(arg: str) -> str:
    if not arg:
        return (
            "Usage: /reminder <task> [schedule]\n"
            "Examples:\n"
            "  /reminder get mail [weekly thu]\n"
            "  /reminder call dentist [tomorrow]\n"
            "  /reminder review doc [monday]\n"
            "  /reminder pay rent [monthly]\n"
            "  /reminder follow up [in 3 days]\n"
            "  /reminder meeting [2/15] or [feb 20]\n"
            "Schedule: weekly <day>, daily, monthly, tomorrow, in N days/weeks, <weekday>, 2/15, feb 15, or omit for today."
        )
    m = _REMINDER_BRACKET_RE.match(arg.strip())
    if m:
        task, schedule = m.group(1).strip(), m.group(2).strip()
    else:
        task, schedule = arg.strip(), ""
    if not task:
        return "Reminder task cannot be empty. Use: /reminder <task> [schedule]"
    script = REPO_ROOT / "tools" / "briefings" / "reminder_add.py"
    if not script.exists():
        return "reminder_add.py not found."
    try:
        result = subprocess.run(
            [sys.executable, str(script), task, schedule],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=15,
        )
        if result.returncode != 0:
            return (result.stderr or result.stdout or "Reminder script failed.").strip()
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return "Reminder timed out."
    except Exception as e:
        return f"Reminder error: {e}"


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------
HELP_TEXT = """\
🤖 Available Commands

💡 Capture Ideas
/random <text> — General ideas
/travel <text> — Travel ideas
/quote <text>  — Save a quote
/link <text>   — Save a link
/gift <text>   — Gift ideas
/food <text>   — Food/Restaurant ideas

📅 Planning & Tasks
/reminder <task> [schedule] — Add to Reminders
/rotary — Generate next Rotary agenda
/trial [name] — Start DUI trial prep

⚙️ System & Tools
/run <script> — Run daily brief, news, etc.
/models [id] — List/switch AI models
/reset — Clear conversation context
/restart — Restart the bot (Admin only)
/help — Show this menu
"""

START_TEXT = """\
👋 Hello! I'm your AI Assistant.

I can help you capture ideas, manage tasks, and run tools.
Type /help to see what I can do, or just start chatting!
"""


# ---------------------------------------------------------------------------
# Restart (LaunchAgent kickstart; only allowlisted users — see bot.py)
# ---------------------------------------------------------------------------
def trigger_restart() -> str:
    """Schedule a restart in 2s via launchctl kickstart. Returns reply text."""
    uid = os.getuid()
    target = f"gui/{uid}/{LAUNCH_AGENT_LABEL}"
    cmd = ["sh", "-c", f"sleep 2; launchctl kickstart -k {target}"]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        cwd=REPO_ROOT,
    )
    return "Restarting in 2 seconds…"


def can_restart(user_id: int, allowed_user_ids: list) -> bool:
    """True if this user is allowed to run /restart."""
    if allowed_user_ids:
        return user_id in allowed_user_ids
    return user_id == _RESTART_ALLOWED_DEFAULT_ID


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
# Maps command name → handler.  Capture commands are handled generically.
_DISPATCH: dict[str, callable] = {
    "reminder":  lambda arg: _cmd_reminder(arg),
    "reminders": lambda arg: _cmd_reminder(arg),
    "rotary":    lambda _:  _cmd_rotary(),
    "run":       lambda arg: _cmd_run(arg),
    "help":      lambda _:  HELP_TEXT,
    "start":     lambda _:  START_TEXT,
}


def route(text: str) -> str | None:
    """
    Route a slash command.  Returns reply text if handled, None to fall
    through to the LLM.
    """
    parsed = _parse(text)
    if not parsed:
        return None

    cmd, arg = parsed

    # Capture group
    if cmd in CAPTURE_NOTES:
        if not arg:
            return f"/{cmd} needs content. Example: /{cmd} your idea here"
        try:
            return _cmd_capture(cmd, arg)
        except Exception as e:
            return f"Error saving /{cmd}: {e}"

    # Dispatch table
    if cmd in _DISPATCH:
        return _DISPATCH[cmd](arg)

    # Unknown slash — fall through to LLM (might be a natural-language intent)
    return None


# ---------------------------------------------------------------------------
# /code — create a Claude CLI coding task via conversation
# ---------------------------------------------------------------------------
CODE_TASK_DIRECTIVE = """\
You are helping the user create a coding task for the Claude CLI task runner. \
The task will be added to ClawdBot Kanban and picked up automatically.

Steps:
1. Call read_file with path "args/projects.yaml" to get available projects and their budgets.
2. Ask the user which project they want to work on. Show the available options.
3. Ask what they want done — get enough detail for a clear, actionable task.
4. Draft a single-sentence description. Keep it tight.
5. Confirm before adding: "I'll add this → [project] description. Sound good?"
6. On confirmation, call kanban_write: action=add, title="[project] description", status=todo.
7. Reply: "Added ✓ — picks up on the next poll."

Keep it short. One or two questions at a time. Don't explain the system unless asked."""


def get_code_directive(text: str) -> str | None:
    """If text is /code [optional args], return the directive; else None."""
    t = text.strip()
    if not t.lower().startswith("/code"):
        return None
    rest = t[5:].strip()
    user_hint = f"\n\nThe user typed: /code {rest}" if rest else ""
    return CODE_TASK_DIRECTIVE + user_hint


# ---------------------------------------------------------------------------
# Trial prep: substitute /trial [case] with a directive for the LLM
# ---------------------------------------------------------------------------
TRIAL_PREP_DIRECTIVE = """You are starting DUI trial prep. Follow the Case Prep Guide and templates.

Steps:
1) Use trial_read_guide to load the Case Prep Guide.
2) Use trial_list_cases to see available case folders. If the user gave a case name (e.g. after /trial Smith), use that; otherwise ask which case to prep.
3) Work through templates in this order: Theme Document, Opening Statement, Cross-Examination, Motion in Limine, Closing Argument. Use trial_list_templates and trial_read_template to get each template.
4) For each template: ask the user the questions or section prompts one by one (e.g. case number, court, story, theme). Keep it conversational; ask one or two things at a time. Fill in their answers.
5) When you finish a template, use trial_save_document to save it to the case folder. Then move to the next template.

Be conversational. Ask detailed questions based on each template section. Do not skip sections."""


def get_trial_prep_message(text: str) -> str | None:
    """If text is /trial or /trial <case>, return the directive (with optional case name); else None."""
    t = text.strip()
    if not t.lower().startswith("/trial"):
        return None
    rest = t[6:].strip()  # after "/trial"
    case_part = f" The user specified case name: {rest}." if rest else ""
    return TRIAL_PREP_DIRECTIVE + case_part
