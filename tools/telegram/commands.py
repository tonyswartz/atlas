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
    """Load key from environment (envchain) or .env, fall back to legacy clawdbot auth profile."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
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
# /rotary — interactive agenda creation (directive for LLM)
# ---------------------------------------------------------------------------
ROTARY_AGENDA_DIRECTIVE = """You are helping the user with Rotary meeting agendas.

**If the user says "/rotary add" followed by content:**
- This is a QUICK EDIT to an existing agenda
- Extract the date (e.g., "2/10" → "2026-02-10") and the announcement text
- CRITICAL WORKFLOW (you MUST follow these steps in order):
  1. Call rotary_read_agenda with the meeting_date to get existing content
  2. Parse the full content you received
  3. Find the appropriate section (President Announcements or Member Announcements)
  4. Add a bullet point (- New announcement text) to that section
  5. Call rotary_save_agenda with the COMPLETE updated content (all sections intact)
- NEVER call rotary_save_agenda without reading the existing content first
- NEVER save partial content - you must preserve ALL sections of the agenda
- Reply with the actual meeting date you used, e.g. "Added to 2/17 agenda ✓" (use the real date from meeting_date, never a hardcoded 2/10)

**If the user says just "/rotary" or "/rotary create" (no "add", no other content):**
- This is FULL INTERACTIVE workflow — do NOT reply "Added to ...". Instead:
  1. Call rotary_read_log to get next meeting date, spotlight, speaker
  2. Confirm: "Creating agenda for [date]. Member spotlight: [name]. Speaker: [name] — [topic]. Sound good?"
  3. Collect only PRE-SCHEDULED items. Ask one by one: president announcements? speaker bio? (Member spotlight and speaker come from the log; don't ask about guests or club/member announcements — those are fluid and handled real-time at the meeting, not pre-planned.)
  4. **Speaker LinkedIn:** When you have the speaker's name (from the log or from the user): (a) Call browser_search with a query that prefers local profiles, e.g. "[Speaker full name] LinkedIn Ellensburg" or "[Speaker full name] LinkedIn Yakima". Prefer results that mention Ellensburg, Yakima, or Central Washington. (b) When you find a likely profile URL (linkedin.com/in/...), use the browser tool (it uses Safari; the user is logged into LinkedIn there): navigate to that URL, then snapshot to scrape the page. Extract headline, about, or role from the scraped content and add both the profile URL and a short bio to the speaker bio section of the agenda.
  5. Call rotary_read_template to get template
  6. Fill template with all collected info (including speaker LinkedIn URL and scraped bio if found)
  7. Call rotary_save_agenda with complete content
  8. Reply: "Agenda saved ✓ → [path]"

Keep it conversational. For quick adds, just do it - don't ask for confirmation."""


def get_rotary_directive(text: str) -> str | None:
    """If text is /rotary [optional args], return the directive; else None."""
    t = text.strip()
    if not t.lower().startswith("/rotary"):
        return None
    rest = t[7:].strip()
    user_hint = f"\n\nThe user typed: /rotary {rest}" if rest else ""
    return ROTARY_AGENDA_DIRECTIVE + user_hint


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
/code — Create a coding task
/task <desc> [$budget] [@project] — Create task
/tasks [filter] — List tasks
/approve <id> — Approve task
/cancel <id> — Cancel task
/status <id> — Task status

🛠️ Script Builder
/build [description] — Create & schedule custom scripts

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
# Task Management Commands
# ---------------------------------------------------------------------------
JEEVESUI_URL = "http://localhost:6001"

def _api_request(method: str, endpoint: str, data: dict = None) -> dict | None:
    """Make API request to JeevesUI."""
    import urllib.request
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
        return None

def _cmd_task(arg: str) -> str:
    """Create a new task: /task description [$budget] [@project]"""
    if not arg:
        return "Usage: /task <description> [$budget] [@project]\nExample: /task Add dark mode $5 @jeevesui"

    # Parse budget and project from arg
    budget = 5.0
    project = "atlas"
    description = arg

    # Extract $budget
    import re
    budget_match = re.search(r'\$(\d+(?:\.\d+)?)', arg)
    if budget_match:
        budget = float(budget_match.group(1))
        description = description.replace(budget_match.group(0), "").strip()

    # Extract @project
    project_match = re.search(r'@(\w+)', arg)
    if project_match:
        project = project_match.group(1)
        description = description.replace(project_match.group(0), "").strip()

    # Create task
    result = _api_request("POST", "/api/tasks", {
        "title": description,
        "project": project,
        "budgetUsd": budget,
        "createdBy": "telegram",
    })

    if result and "id" in result:
        task_id = result["id"][:8]
        return f"✅ Task created (#{task_id})\n\nProject: {project}\nBudget: ${budget:.2f}\n\nReply `/approve {task_id}` to start"
    else:
        return "❌ Failed to create task - JeevesUI may be down"

def _cmd_tasks(arg: str) -> str:
    """List tasks: /tasks [pending|running|completed|all]"""
    filter_status = arg.strip().upper() if arg else None
    valid_statuses = ["PENDING", "APPROVED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]

    endpoint = "/api/tasks?limit=10"
    if filter_status and filter_status in valid_statuses:
        endpoint += f"&status={filter_status}"

    result = _api_request("GET", endpoint)

    if not result or "tasks" not in result:
        return "❌ Failed to fetch tasks - JeevesUI may be down"

    tasks = result["tasks"]
    if not tasks:
        return "No tasks found"

    # Format task list
    lines = ["*📋 Tasks*\n"]
    for task in tasks:
        task_id = task["id"][:8]
        title = task["title"][:40]
        status = task["status"]
        budget = task["budgetUsd"]
        spent = task.get("spentUsd", 0)

        status_emoji = {
            "PENDING": "🟡",
            "APPROVED": "🟢",
            "RUNNING": "⚡",
            "COMPLETED": "✅",
            "FAILED": "❌",
            "CANCELLED": "🚫",
        }.get(status, "⚪")

        lines.append(f"{status_emoji} #{task_id}: {title}")
        lines.append(f"   {status} • ${spent:.2f}/${budget:.2f}\n")

    return "\n".join(lines)

def _cmd_approve(arg: str) -> str:
    """Approve a task: /approve <id>"""
    if not arg:
        return "Usage: /approve <task_id>\nExample: /approve abc123"

    task_id = arg.strip()
    result = _api_request("POST", f"/api/tasks/{task_id}/approve", {"approvedBy": "telegram"})

    if result and "id" in result:
        return f"✅ Task #{task_id[:8]} approved!\n\nWill execute on next poll cycle (~5 min)"
    else:
        return f"❌ Failed to approve task #{task_id[:8]}"

def _cmd_cancel(arg: str) -> str:
    """Cancel a task: /cancel <id>"""
    if not arg:
        return "Usage: /cancel <task_id>"

    task_id = arg.strip()
    result = _api_request("POST", f"/api/tasks/{task_id}/cancel", {})

    if result and "id" in result:
        return f"🚫 Task #{task_id[:8]} cancelled"
    else:
        return f"❌ Failed to cancel task #{task_id[:8]}"

def _cmd_status(arg: str) -> str:
    """Get task status: /status <id>"""
    if not arg:
        return "Usage: /status <task_id>"

    task_id = arg.strip()
    result = _api_request("GET", f"/api/tasks/{task_id}")

    if not result or "id" not in result:
        return f"❌ Task #{task_id[:8]} not found"

    task = result
    status = task["status"]
    title = task["title"]
    budget = task["budgetUsd"]
    spent = task.get("spentUsd", 0)

    status_emoji = {
        "PENDING": "🟡",
        "APPROVED": "🟢",
        "RUNNING": "⚡",
        "COMPLETED": "✅",
        "FAILED": "❌",
        "CANCELLED": "🚫",
    }.get(status, "⚪")

    lines = [
        f"*{status_emoji} Task #{task_id[:8]}*",
        f"\n{title}",
        f"\nStatus: {status}",
        f"Budget: ${spent:.2f} / ${budget:.2f}",
    ]

    # Add recent updates
    if task.get("updates"):
        lines.append("\n*Recent updates:*")
        for update in task["updates"][:3]:
            lines.append(f"• {update['message']}")

    # Add error if failed
    if status == "FAILED" and task.get("errorMessage"):
        lines.append(f"\n*Error:* {task['errorMessage'][:200]}")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
# Maps command name → handler.  Capture commands are handled generically.
_DISPATCH: dict[str, callable] = {
    "reminder":  lambda arg: _cmd_reminder(arg),
    "reminders": lambda arg: _cmd_reminder(arg),
    "task":      lambda arg: _cmd_task(arg),
    "tasks":     lambda arg: _cmd_tasks(arg),
    "approve":   lambda arg: _cmd_approve(arg),
    "cancel":    lambda arg: _cmd_cancel(arg),
    "status":    lambda arg: _cmd_status(arg),
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
The task will be added to Atlas Tasks and picked up automatically.

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


# ---------------------------------------------------------------------------
# /schedule — conversational podcast schedule planning
# ---------------------------------------------------------------------------
SCHEDULE_DIRECTIVE = """You are helping the user plan a month of podcast episodes around a common theme.

Available podcasts:
- **sololaw** (Solo Law Club) - Weekly Friday episodes for solo lawyers
- **832weekends** (832 Weekends) - Weekly episodes about parenting journey
- **explore** (Explore with Tony) - Weekly Friday episodes about travel

Tools available:
- schedule_read: Read current schedule for a podcast
- schedule_add: Add episodes to the schedule (takes JSON array of episodes)
- schedule_preview: Show what the schedule will look like

Steps:
1. If user specified a podcast (e.g. /schedule sololaw), use that. Otherwise ask which podcast they want to plan.
2. Ask what month and theme they want to plan around. Example: "March 2026 focused on Kanban practices for solo law firms"
3. Ask how many episodes (typically 4 weeks = 4 episodes for monthly planning)
4. Based on the theme, brainstorm episode topics. Use your knowledge of the podcast's style and tone:
   - **Solo Law Club**: Practical, actionable advice for solo practitioners. Conversational tone. Framework-driven.
   - **832 Weekends**: Reflective parenting stories. Vulnerable, honest. Focus on ordinary moments.
   - **Explore with Tony**: Personal travel stories with sensory details. Practical resources + inspiration.
5. For each episode, create:
   - Title (concise, descriptive)
   - Key Discussion Points (3-7 bullet points)
   - Show Notes (2-3 sentences summarizing the episode)
   - Date (Fridays for Solo Law Club and Explore, flexible for 832 Weekends)
6. Show the user a preview of all episodes using schedule_preview
7. Ask if they want any edits:
   - Can edit titles, points, dates, or order
   - Can add/remove episodes
   - Iterate until they're happy
8. Once approved, use schedule_add to save all episodes to the Schedule.md file
9. Confirm: "Added 4 episodes to [podcast] schedule! You'll see these when it's time to create episodes."

Be conversational and creative. Help them think through the theme and how to break it into compelling episodes. One or two questions at a time. Keep it tight."""


def get_schedule_directive(text: str) -> str | None:
    """If text is /schedule [podcast], return the directive; else None."""
    t = text.strip()
    if not t.lower().startswith("/schedule"):
        return None
    rest = t[9:].strip()  # after "/schedule"
    podcast_part = f"\n\nThe user specified podcast: {rest}" if rest else ""
    return SCHEDULE_DIRECTIVE + podcast_part


# ---------------------------------------------------------------------------
# /solo, /832, /explore — conversational episode editing
# ---------------------------------------------------------------------------
EPISODE_DIRECTIVE = """You are helping the user work on a specific podcast episode. The user can edit the script, regenerate audio, remix with different music settings, or make other changes.

Available tools:
- read_file: Read the episode's script, state, or metadata
- podcast_regenerate_voice: Regenerate entire episode audio after script edits
- podcast_regenerate_paragraph: Regenerate a specific paragraph (faster, cheaper)
- edit_file: Edit the script directly (use carefully - prefer showing preview first)

Steps:
1. Determine the podcast and episode number from context
2. Use read_file to load the current script from the episode's script_approved.md file
   - Path: /Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/<Podcast Name>/<episode_number>/script_approved.md
3. Show the user what's currently in the episode (or relevant section)
4. Ask what they want to change:
   - Edit the script text (specific paragraphs or whole script)
   - Regenerate audio for specific paragraphs (cheaper, faster)
   - Regenerate entire episode voice
   - Fix pronunciation issues
5. For script edits:
   - Show them the before/after
   - Ask for confirmation
   - Use edit_file to update script_approved.md
   - Then offer to regenerate audio
6. For audio regeneration:
   - **Paragraph-level**: Use podcast_regenerate_paragraph (faster, ~$0.50-1.00)
     - Can find by paragraph number or search term
   - **Full episode**: Use podcast_regenerate_voice (slower, ~$3-5)
   - Always check if script was edited first
7. For pronunciation fixes:
   - Can pass pronunciation_fixes parameter to regenerate functions
   - Example: {"Kanban": "kahn-bahn", "WIP": "whip"}

Be conversational. Ask what they want to change. Show previews before making changes. Confirm before regenerating audio (costs money).

Podcast names:
- sololaw → "Solo Law Club"
- 832weekends → "832 Weekends"
- explore → "Explore with Tony"

Episode ID format: `<podcast_id>-<episode_number>` (e.g., "sololaw-030", "832weekends-001", "explore-005")"""


def get_episode_directive(text: str) -> str | None:
    """If text is /solo NNN, /832 NNN, or /explore NNN, return the directive with episode context."""
    import re

    t = text.strip()

    # Check for /solo NNN
    solo_match = re.match(r'/solo\s+(\d+)', t, re.IGNORECASE)
    if solo_match:
        episode_num = solo_match.group(1)
        return EPISODE_DIRECTIVE + f"\n\nThe user wants to work on Solo Law Club episode {episode_num} (episode_id: sololaw-{episode_num})"

    # Check for /832 NNN
    eight32_match = re.match(r'/832\s+(\d+)', t, re.IGNORECASE)
    if eight32_match:
        episode_num = eight32_match.group(1)
        return EPISODE_DIRECTIVE + f"\n\nThe user wants to work on 832 Weekends episode {episode_num} (episode_id: 832weekends-{episode_num})"

    # Check for /explore NNN
    explore_match = re.match(r'/explore\s+(\d+)', t, re.IGNORECASE)
    if explore_match:
        episode_num = explore_match.group(1)
        return EPISODE_DIRECTIVE + f"\n\nThe user wants to work on Explore with Tony episode {episode_num} (episode_id: explore-{episode_num})"

    return None


# ---------------------------------------------------------------------------
# /build — conversational script builder with launchd scheduling
# ---------------------------------------------------------------------------
BUILD_DIRECTIVE = """You are helping the user build or modify a Python script and optionally schedule it to run automatically.

**Available tools:**
- read_file: Read existing scripts (ALWAYS check if modifying existing script)
- list_files: Browse tools/scripts/ or tools/briefings/ directories
- script_writer: Generate/save Python scripts based on natural language descriptions
- launchd_manager: Create launchd jobs to schedule scripts automatically

**IMPORTANT: Detect modification vs creation**

If the user mentions:
- "modify the <script_name> script"
- "update <script_name>"
- "fix the <script_name>"
- "change <script_name> to..."
- References a specific script by name

Then this is a **MODIFICATION** — follow the modification workflow below.

Otherwise, this is **NEW SCRIPT CREATION** — follow the creation workflow.

---

## Modification Workflow (for existing scripts)

**CRITICAL: Read the existing script FIRST before asking questions!**

1. **Identify the script**
   - Extract script name from user's request
   - Common locations:
     * tools/briefings/<script_name>.py (daily_brief, research_brief, etc.)
     * tools/system/<script_name>.py
     * tools/scripts/<script_name>.py
   - Use read_file to load the current version

2. **Understand the current implementation**
   - Read the entire script
   - Identify: data sources, output format, dependencies, configuration
   - Answer questions yourself from the code:
     * Where does data come from? (API, RSS, file, database)
     * What's the output? (Telegram, file, console)
     * What credentials are needed? (check imports and env vars)
     * How is it currently scheduled? (check CLAUDE.md or git log for cron/launchd)

3. **Make the modification**
   - Understand what the user wants changed
   - Make MINIMAL changes (don't refactor unrelated code)
   - Preserve existing patterns and style
   - Use read_file and then describe the changes you'll make

4. **Show the changes**
   - Explain what you're changing and why
   - Show the relevant before/after code snippets
   - Get user approval

5. **Save the updated script**
   - Use read_file to get current content, make edits, then save
   - Confirm: "Updated <script_name>.py ✅"

**Example modification flow:**
```
User: "/build the research brief script pulls old stories..."

You (internally): This mentions "research brief script" → modification workflow
  1. Read tools/briefings/research_brief.py
  2. Analyze: uses Google News RSS, parses <item> tags, no date filtering
  3. Understand the issue: no pubDate extraction → shows old articles
  4. Draft solution: add date parsing, filter to last 24 hours
  5. Show user the changes
  6. User approves → save updated script
```

---

## Creation Workflow (for new scripts)

1. **Understand the requirement**
   - Ask what the script should do
   - Clarify: inputs, outputs, frequency, notifications needed
   - Determine if it needs credentials (Telegram token, API keys, etc.)
   - Examples:
     * "Check my calendar every morning at 7am and text me today's events"
     * "Monitor a website for changes every hour and notify me"
     * "Process files in a folder daily at 5pm"

2. **Draft the script**
   - Call script_writer with:
     * task_description: Clear description of what it does
     * imports: List of needed imports (e.g., ["import requests", "import json"])
     * use_envchain: true if needs credentials from Keychain
   - Show the user the generated code
   - Explain what it does in plain language

3. **Iterate on the code**
   - User may request changes: "add error handling", "send a Telegram notification", etc.
   - Regenerate with updated requirements
   - Keep iterating until user approves

4. **Save the script**
   - Ask for a filename (e.g., "calendar_morning_brief")
   - Call script_writer to save to tools/scripts/
   - Script will be saved as executable (.py)

5. **Schedule (optional)**
   - Ask if they want it to run automatically
   - If yes, ask for schedule:
     * "every 5 minutes"
     * "daily at 9am"
     * "every weekday at 5pm"
     * "every hour"
   - Call launchd_manager to create and load the job:
     * Creates .plist file in ~/Library/LaunchAgents/
     * Automatically loads the job
     * Runs with envchain for credential access
     * Logs to logs/<job-name>.log

6. **Confirm completion**
   - Show summary:
     ✅ Script created: tools/scripts/<name>.py
     ✅ Scheduled: <schedule description>
     📋 Logs: logs/<job-name>.log

     To test manually: /run <script_name>
     To check status: launchctl list | grep atlas
     To stop: launchctl unload ~/Library/LaunchAgents/com.atlas.<name>.plist

**Important patterns:**
- **Telegram notifications**: Use the standard send_telegram() pattern (see tools/briefings/daily_brief.py)
- **File processing**: Save state to data/ directory (see tools/bambu/bambu_watcher.py)
- **API polling**: Use state file pattern (see script_writer.py templates)
- **Credentials**: Always use envchain for sensitive data, never hardcode
- **Logging**: Print to stdout/stderr - launchd captures to log files automatically

**Safety:**
- Always show code before saving
- Validate syntax before scheduling
- Explain what the script will do in plain language
- Confirm schedule before creating launchd job
- Remind user they can test with /run before scheduling

Be conversational. Ask clarifying questions. Show code previews. Confirm before creating/scheduling. Make it easy."""


def get_build_directive(text: str) -> str | None:
    """If text is /build [optional description], return the directive."""
    t = text.strip()

    if t.lower().startswith("/build"):
        # Extract any initial description
        description = t[6:].strip()  # Remove "/build"

        if description:
            # Check if this looks like a modification request
            modification_keywords = ["modify", "update", "fix", "change", "the script", "script pulls", "script shows"]
            is_modification = any(keyword in description.lower() for keyword in modification_keywords)

            if is_modification:
                return BUILD_DIRECTIVE + f"\n\n**MODIFICATION REQUEST**\n\nThe user wants to modify an existing script: {description}\n\nREMEMBER: Read the existing script FIRST using read_file before asking any questions. The script likely already exists in tools/briefings/, tools/system/, or tools/scripts/."
            else:
                return BUILD_DIRECTIVE + f"\n\nThe user wants to build: {description}"
        else:
            return BUILD_DIRECTIVE + "\n\nStart by asking the user what they want to build."

    return None
