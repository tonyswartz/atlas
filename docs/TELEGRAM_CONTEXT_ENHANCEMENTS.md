# Telegram Bot Context Enhancements

Ideas to make JeevesAtlas more contextual and aware of what it has access to (same spirit as priorities + journal + kanban).

---

## Done

- **Priorities / “what’s on my plate”** — System prompt tells the bot to use MEMORY + USER.md + kanban_read + journal_read_recent + calendar, and to answer from data first.
- **kanban_read** — Read-only To-Do / In Progress / Backlog from `clawd/kanban/tasks.json`.
- **journal_read_recent** — Last N days of journal entries from Obsidian journal CSV; used for “what I need to do” and “what’s on my mind.”
- **reminders_read** — Read Tony Reminders.md (Today, Later This Week, Shopping, etc.). Prompt: “what do I need to remember” / “my reminders” / “what’s today” → use reminders_read and/or daily_brief/calendar.
- **Prefetch for “priorities” and “what’s today”** — When the user says “my priorities,” “what should I focus on,” “what’s on my plate,” etc., we pre-inject kanban_read + journal_read_recent + reminders_read so the first reply is always data-backed. When they say “what’s today” / “what do I have today,” we prefetch reminders_read.
- **“What’s today”** — Prompt section: use run_tool(daily_brief), google_calendar_find_events, reminders_read; prefetch reminders on that intent.
- **Explicit “what you have access to”** — System prompt now includes a bullet list: memory, USER.md, Kanban, journal entries, reminders, heartbeat, calendar, Gmail drafts, daily brief, trial prep, web search, browser. “When the user asks about any of these, use the corresponding tool — don’t ask them to tell you what you can look up.”
- **heartbeat_read** — New tool: reads HEARTBEAT.md and heartbeat-state.json, returns checklist and state. Prompt: “am I on track?” / “how’s my week?” → call heartbeat_read and summarize.
- **Configurable paths** — `args/telegram.yaml` has a `paths` section: `journal_csv`, `kanban`, `reminders`. Set to a path (absolute or relative to repo root) to override defaults; omit or set to null to use built-in paths.
- **Trial prep in prompt** — When the user asks about trial prep or which case to work on, call trial_list_cases and trial_list_templates and use that in the answer.

---

## Larger / future

### Generic vault-note read

- **Idea:** One tool `vault_note_read` with an allowlisted list of paths (Tony Reminders.md, HEARTBEAT.md, Travel Profile, Rotary Log, etc.). Avoids N separate “read_foo” tools; add new notes via config.

### Gmail read / search

- **Gap:** Only gmail_create_draft is exposed.
- **Idea:** Would require Gmail read scope and either a new Zapier action or Gmail API integration.

### Calendar prefetch for “this week”

- **Idea:** When the user says “my week” / “this week,” prefetch google_calendar_find_events for the week. Optional; can be noisy if calendar is busy.

---

*Last updated: 2026-02-03*
