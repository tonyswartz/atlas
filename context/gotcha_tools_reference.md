# GOTCHA Tools Reference

Static reference for the Telegram bot's system prompt. Describes available tools, their CLI flags, and output formats.

---

## Memory Tools

### memory_read
Loads persistent memory context (MEMORY.md + daily logs + optional DB entries).

- **CLI:** `python3 memory/memory_read.py`
- **Key flags:** `--format json|markdown|summary`, `--memory-only`, `--logs-only`, `--include-db`, `--days N`
- **Output:** JSON only when `--format json`. Otherwise: status line to stderr, content to stdout.
- **Returns:** `memory_file` (MEMORY.md content + parsed sections), `daily_logs` (recent log files), `db_entries` (if `--include-db`)

### memory_write
Saves to persistent memory: appends to today's daily log and/or adds a row to SQLite.

- **CLI:** `python3 memory/memory_write.py`
- **Required:** `--content "text"`
- **Key flags:** `--type fact|preference|event|insight|task|relationship|note`, `--importance 1-10`, `--source user|session|system`, `--tags "tag1,tag2"`, `--log-only`, `--db-only`
- **Persist to MEMORY.md:** `--update-memory --section key_facts|user_preferences|learned_behaviors`
- **Output:** `OK <message>` line, then JSON with success status.

### memory_search (hybrid_search.py)
Best general-purpose search. Combines BM25 keyword scoring with optional semantic vector scoring.

- **CLI:** `python3 memory/hybrid_search.py`
- **Required:** `--query "text"`
- **Key flags:** `--limit N`, `--keyword-only`, `--semantic-only`, `--type <type>`, `--min-score 0.1`
- **Output:** `OK Found N results...` line, then JSON with scored results array.
- **Note:** Use `--keyword-only` unless OPENAI_API_KEY is confirmed available. Semantic search calls the OpenAI embeddings API.

### memory_db
Direct SQLite CRUD and stats.

- **CLI:** `python3 memory/memory_db.py`
- **Required:** `--action add|get|list|search|delete|stats|recent`
- **Key flags:** `--id N`, `--query "text"`, `--type <type>`, `--hours N`, `--limit N`
- **Output:** `OK Success` line, then JSON.

---

## web_search

Search the web for current information. Use when the user asks to look something up, browse the internet, or find facts not in memory.

- **Required:** `query` (search string). Optional: `count` (1-20, default 5).
- **Requires:** BRAVE_API_KEY in .env (Brave Search API free tier: 2000 requests/month).
- **Output:** JSON with `ok`, `query`, and `results` array of `{ title, url, snippet }`. On failure: `ok: false`, `error`.

---

## browser

Controls Safari for web research. **Requires the browser server to be running:** `python3 tools/browser/browser_server.py` (run once in background). On macOS, one-time: `safaridriver --enable`.

- **Actions:** `navigate` (open URL), `snapshot` (get page title + content), `click` (click element by selector), `type` (type text into element), `screenshot`, `close`, `status`
- **For navigate:** pass `url`. For click/type: pass `selector` and optionally `by` (css|xpath|id|name). For type: also pass `text`. For snapshot: optional `max_chars` (default 50000).
- **Output:** JSON with `ok`, and on success: `url`, `title`, `content` (snapshot), or `message`. On failure: `error`.

---

## read_file

Read any file inside the atlas repo by relative path. Use when the user asks to look at, compare, or inspect a script or config file.

- **Required:** `path` (relative to repo root, e.g. `tools/briefings/daily_brief.py`).
- **Returns:** File contents as text. Errors if path is outside the repo or file doesn't exist.

---

## list_files

List directory contents inside the repo. Use when the user wants to browse the repo structure or find what scripts/files exist.

- **Optional:** `path` (directory relative to repo root; omit for root). Hidden files excluded.
- **Returns:** JSON: `{ "success", "path", "entries": [{ "name", "type": "dir"|"file" }] }`.

---

## reminder_add

Add a reminder to Tony Reminders.md. Use when the user says "remind me to…" or "set a reminder."

- **Required:** `task` (what to remember). **Optional:** `schedule` (e.g. "tomorrow", "weekly thu", "in 3 days").
- **Schedule parser handles:** weekly \<day\>, daily, monthly, tomorrow, in N days/weeks, next \<weekday\>, specific dates. Omit schedule to default to Today.
- **Returns:** JSON: `{ "success", "message" }`.

---

## kanban_write

Add or move a task in the Kanban board (tasks.json). **Confirm with user before adding** (per USER.md).

- **Required:** `action` ("add" or "move"), `status` ("todo", "in_progress", "backlog").
- **For add:** also `title` (task name).
- **For move:** also `task_id` — get it from kanban_read first.
- **Returns:** JSON: `{ "success", "message" }`.

---

## bambu

Query or control the Bambu 3D printer on the local network via `bambu-cli`. Use when the user asks about print status, filament, or wants to control the printer.

- **Required:** `action` — one of: `status`, `ams`, `pause`, `resume`, `stop`, `light_on`, `light_off`.
- `status` / `ams` — read-only, safe to call any time. Returns structured JSON.
- `pause` / `resume` / `stop` — print control. **Confirm with user before stopping.**
- `light_on` / `light_off` — chamber light toggle.
- **Returns:** JSON: `{ "success", "action", "data" | "message" }`.

---

## run_tool

Runs an allowlisted script and returns its stdout. Use when the user asks for a daily brief, research brief, news briefing, or heartbeat check.

- **Scripts:** `daily_brief`, `research_brief`, `local_news`, `news_briefing`, `run_heartbeat`
- **Returns:** Script stdout on success; JSON with `success: false` and `error` on failure.

---

## kanban_read

Read the user's task/Kanban list (read-only). Returns To-Do, In Progress, and Backlog as lists of task titles. Use when the user asks about priorities, what's on their plate, or what to focus on. Source: `clawd/kanban/tasks.json`.

- **No parameters.** Returns JSON: `{ "success", "todo", "in_progress", "backlog" }`.

---

## journal_read_recent

Read the user's recent journal entries from the Obsidian journal export CSV. Use when the user asks about their priorities, what they need to do, what's on their mind, or what they've been thinking — recent journal text often states goals and to-dos.

- **Optional:** `days` (default 7) — number of days of entries to return.
- **Returns:** JSON with `success`, `days_requested`, and `entries` (array of `{ date, entry_text, mood_rating }`). Read-only.

---

## reminders_read

Read the user's reminders from Tony Reminders.md (Obsidian vault). Use when the user asks what they need to remember, what their reminders are, or what's on their list.

- **No parameters.** Returns JSON: `{ "success", "sections" }` where `sections` is e.g. `{ "[Today]": ["- task [date]"], "[Later This Week]": [...] }`. Read-only.

---

## heartbeat_read

Read the user's heartbeat checklist (HEARTBEAT.md) and state (heartbeat-state.json). Use when the user asks "am I on track?", "how's my week?", or how they're doing against their checklist.

- **No parameters.** Returns JSON: `{ "success", "checklist", "state" }`. Read-only.

---

## Goal Files

Goals are process definitions. **Read-only.** Located at `goals/`.

- `goals/manifest.md` — index of all available goals
- `goals/build_app.md` — ATLAS 5-step app-building workflow (Architect → Trace → Link → Assemble → Stress-test)

---

## Output Parsing Notes

| Script | Status prefix | JSON follows |
|--------|--------------|--------------|
| memory_read (--format json) | None | Yes — stdout is pure JSON |
| memory_write | `OK ...` or `ERROR ...` | Yes |
| memory_db | `OK Success` or `ERROR ...` | Yes |
| hybrid_search | `OK Found N results...` or `ERROR ...` | Yes |
| web_search | None | Yes — stdout is pure JSON |
| browser | None | Yes — stdout is pure JSON |
| read_goal | None | No — returns raw markdown |
