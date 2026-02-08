# Tools Manifest

Master list of tools and their functions. Before writing new code, check this list. If you create a new tool, add it here with a one-sentence description.

## Memory (run from repo root: `python memory/<script>.py`)

| Tool | Description |
|------|-------------|
| `memory/memory_read.py` | Load persistent memory at session start (MEMORY.md + daily logs); supports markdown/JSON output. |
| `memory/memory_write.py` | Append to daily logs, add SQLite entries, or update MEMORY.md. |
| `memory/memory_db.py` | SQLite CRUD and keyword search for memory entries (add, search, list, get, delete, stats). |
| `memory/hybrid_search.py` | Hybrid keyword + semantic search over memory. |
| `memory/semantic_search.py` | Semantic search over memory entries (requires embeddings). |
| `memory/conversation_tracker.py` | Tracks conversation turns, user corrections, and behavioral patterns for context retention and learning. CLI: --action log/recent/patterns/corrections. Exposed as `conversation_context` tool to bot. |
| `tools/memory/vault_onboard.py` | One-time script: reads Obsidian vault (journals, Travel Profile, trial docs, Rotary) and seeds USER.md + memory_db with extracted facts. |

## Telegram Bot (run: `python3 tools/telegram/bot.py`)

| Tool | Description |
|------|-------------|
| `tools/telegram/bot.py` | Entry point — starts Telegram polling loop, routes messages, enforces allowlist. |
| `tools/telegram/conversation.py` | Claude tool_use loop — manages per-user history, loads memory on session start, returns final reply. |
| `tools/telegram/tool_runner.py` | Executes memory scripts as subprocesses, translates Claude tool inputs into CLI flags, parses JSON output. Exposes journal_read_recent, reminders_read, heartbeat_read (read-only). Paths configurable via args/telegram.yaml paths section. |
| `tools/telegram/tool_definitions.py` | Anthropic tool schemas (pure data) — defines what tools Claude can call and their argument shapes. |
| `tools/telegram/config.py` | Loads `args/telegram.yaml` and `.env` into a cached runtime config dict. |
| `tools/telegram/commands.py` | Slash-command router — intercepts /commands before the LLM. Captures (/random /travel /food etc), /rotary agenda gen, /run, /help. |

## Bambu / 3D Printing (`tools/bambu/`)

| Tool | Description |
|------|-------------|
| `tools/bambu/bambu_watcher.py` | Polls Bambu printer (cron every 5 min); detects job completion, queues prompt. On-demand status/AMS/control via the `bambu` tool in tool_runner uses bambu-cli directly. |
| `tools/bambu/bambu_prompt_poller.py` | Sends Telegram: "New print done" + full spool list (name \| remaining g) + 3 questions; reply format "N, Xg, Name". |
| `tools/bambu/bambu_reply_handler.py` | Parses reply "spool_number, grams, name" (e.g. 6, 39.25g, Tony); logs to JeevesUI + Obsidian. |
| `tools/bambu/bambu_login.py` | Interactive Bambu Cloud auth; saves token to secrets/. |
| `tools/bambu/import_spoolman.py` | One-time import of Spoolman filament inventory into JeevesUI. |
| `tools/bambu/update_spool_prices.py` | Syncs spool prices from Spoolman export to JeevesUI. |
| `tools/bambu/bambu_watcher_wrapper.sh` | Cron wrapper with flock; runs watcher then poller. |
| `tools/bambu/bambu_watcher_health.py` | Health check: if state file not updated in 20 min, sends Telegram alert (throttled). Run via cron every 30 min. |

## Briefings & News (`tools/briefings/`)

| Tool | Description |
|------|-------------|
| `tools/briefings/daily_brief.py` | 6 am briefing: weather, reminders (auto-rolls recurring), calendar, case law with PDF holdings, quote. Sends to Telegram, saves to Digest + Research/Briefs/ + Case Law/. |
| `tools/briefings/research_brief.py` | 3 pm digest: tech + Kraken news from Google RSS, sent via Telegram. |
| `tools/briefings/weekly_review.py` | Friday 5 pm review: journal stats, mood trend, fitness, kanban health, AI recap of week's entries, nudges for anything worth flagging. Backs up week's journals and sends to Telegram. |
| `tools/briefings/journal_backup.py` | Backs up the week's journal entries to dated CSV in Journals/Backups/ (called by weekly_review). |
| `tools/briefings/journal_recap.py` | Generates AI-powered summary of the week's journal entries using MiniMax (called by weekly_review). |
| `tools/briefings/mindsetlog_sync.py` | Syncs recent journal entries from MindsetLog API to Obsidian CSV (OAuth version - requires session cookie). |
| `tools/briefings/mindsetlog_db_sync.py` | Syncs journal entries directly from MindsetLog's PostgreSQL database (most secure - no OAuth needed). |
| `tools/briefings/health_stats.py` | Fetches Oura health data and cycling stats from MindsetLog database for weekly review integration. |
| `tools/briefings/health_monitor.py` | Daily proactive health monitoring - checks Oura data for anomalies (HRV, RHR, sleep patterns, workout gaps) and sends Telegram alerts. |
| `tools/briefings/wellness_coach.py` | Autonomous fitness advisor: recovery-aware recommendations, PR celebrations, pattern detection, long-term trend spotting (steps, HRV, workout frequency), goal tracking. Runs 7:30am daily. |
| `tools/briefings/monthly_fitness_review.py` | Comprehensive month-over-month and quarterly performance review: baseline health trends (HRV, RHR, readiness), training volume, consistency. Runs 8am on 1st of month. |
| `tools/briefings/local_news.py` | Aggregates local news (Ellensburg / Yakima / Seattle) with dedup and importance scoring. |
| `tools/briefings/news_briefing.py` | Thin wrapper around local_news.py. |
| `tools/briefings/garbage_reminder.py` | Weekly: sets next Thursday garbage/recycling line in Tony Reminders.md (1st/3rd Thu = both, 2nd/4th = garbage only). |
| `tools/briefings/reminder_add.py` | Add a reminder to Tony Reminders.md; parses due/recurrence (e.g. weekly every thursday, tomorrow, monday). Used by /reminder in Telegram. |

## Legal & Case Law (`tools/legal/`)

| Tool | Description |
|------|-------------|
| `tools/legal/wa_dui_bill_tracker.py` | Tracks WA legislature DUI bills; alerts via Telegram on status change. |
| `tools/legal/wa_opinions_to_obsidian.py` | Imports WA appellate opinions into Obsidian with optional AI summarisation. |
| `tools/legal/scrape_wa_opinions.py` | Standalone WA opinions scraper (legacy). |

## Task Automation (`tools/tasks/`)

| Tool | Description |
|------|-------------|
| `tools/tasks/claude_task_runner.py` | Polls Kanban for [project] tasks, runs them via `claude -p`, shows diff, commits on [approved]. Quota-aware with auto-resume. |

## Heartbeat (`tools/heartbeat/`)

| Tool | Description |
|------|-------------|
| `tools/heartbeat/run_heartbeat.py` | Reads HEARTBEAT.md and heartbeat-state.json; prints HEARTBEAT_OK or brief status. Call via Telegram run_tool or cron. |
| `tools/heartbeat/watchdog.py` | Post-cron error scanner: reads today's log files for errors/tracebacks and sends a Telegram alert if any are found. Runs at 6:05 AM via cron. |

## Research (`tools/research/`)

| Tool | Description |
|------|-------------|
| `tools/research/web_search.py` | Web search via Brave Search API. CLI: --query, --count. Requires BRAVE_API_KEY in .env. Used by Telegram tool_runner for "search the web" / "browse the internet" requests. |

## Browser — Safari (`tools/browser/`)

| Tool | Description |
|------|-------------|
| `tools/browser/browser_server.py` | HTTP server that holds a Selenium Safari session. Run once (e.g. in background) before using the browser tool. Requires `safaridriver --enable` once on macOS. |
| `tools/browser/browser.py` | CLI client: sends actions (navigate, snapshot, click, type, screenshot, close, status) to the server. Used by Telegram tool_runner. |
| `tools/browser/install-launch-agent.sh` | Installs a LaunchAgent so the browser server runs at login. Run from repo root: `bash tools/browser/install-launch-agent.sh`. |

## Zapier MCP — Gmail & Google Calendar (`tools/zapier/`)

| Tool | Description |
|------|-------------|
| `tools/zapier/zapier_runner.py` | Standalone MCP client for Zapier. Called by tool_runner via subprocess. Allowlisted tools: gmail_create_draft, google_calendar_find/create/move/busy. URL from `.env` MCP key. |

## Quick Capture (`tools/capture/`)

| Tool | Description |
|------|-------------|
| `tools/capture/quick_capture_handler.py` | Reads Telegram commands (/random, /travel, /quote, etc.) and appends to categorised Obsidian notes. |

## System Configuration & Automation (`tools/system/`)

| Tool | Description |
|------|-------------|
| `tools/system/system_config.py` | Configure automations: update chat IDs for briefings, manage cron schedules, create monitors (YouTube, RSS). CLI: --action update_chat_id/add_cron/remove_cron/update_cron_time/create_monitor/list_automations. Exposed as `system_config` tool to Telegram bot LLM. |
| `tools/system/cron_manager.py` | Cron job management utilities (list, add, remove, update schedules). Used by system_config.py. CLI: list/add/remove/update. |
| `tools/system/script_writer.py` | Generate Python scripts from natural language descriptions. Creates working scripts with error handling, logging, and atlas integration. CLI: --task "description" --output "path" --schedule "cron". Exposed as `script_writer` tool to Telegram bot LLM. |

## Intelligence & Learning (`tools/intelligence/`)

| Tool | Description |
|------|-------------|
| `tools/intelligence/proactive_engine.py` | Proactive intelligence: generates context-aware suggestions, detects patterns, predicts intent from partial messages. CLI: --action suggestions/brief/intent/triggers. Exposed as `proactive_intelligence` tool to bot. |

---

*Tools are the execution layer — deterministic scripts that do the work. They don't decide; they execute.*
