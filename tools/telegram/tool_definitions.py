"""
OpenAI-compatible tool schema definitions.

Passed as the `tools` parameter to openai.chat.completions.create().
Ollama's OpenAI-compatible endpoint uses this same format.
The names and parameter schemas here must match what tool_runner.execute() expects.
"""

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "memory_read",
            "description": "Load persistent memory context (MEMORY.md, daily logs, and optionally database entries). Use at conversation start or when the user asks about stored memories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown", "summary"],
                        "description": "Output format. json for structured data, markdown for readable text.",
                        "default": "json"
                    },
                    "include_db": {
                        "type": "boolean",
                        "description": "Include SQLite database entries in output.",
                        "default": False
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days of logs to include.",
                        "default": 2
                    },
                    "memory_only": {
                        "type": "boolean",
                        "description": "Only load MEMORY.md, skip logs.",
                        "default": False
                    },
                    "logs_only": {
                        "type": "boolean",
                        "description": "Only load daily logs, skip MEMORY.md.",
                        "default": False
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_write",
            "description": "Save something to persistent memory. Use when the user tells you something worth remembering, or when you learn something useful during conversation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The content to save."
                    },
                    "type": {
                        "type": "string",
                        "enum": ["fact", "preference", "event", "insight", "task", "relationship", "note"],
                        "description": "Category of the memory entry.",
                        "default": "fact"
                    },
                    "importance": {
                        "type": "integer",
                        "description": "Importance level 1-10. Use 7-10 for things explicitly asked to remember, 3-6 for useful-but-not-flagged.",
                        "default": 5
                    },
                    "source": {
                        "type": "string",
                        "enum": ["user", "inferred", "session", "external", "system"],
                        "default": "session"
                    },
                    "tags": {
                        "type": "string",
                        "description": "Comma-separated tags for searchability."
                    },
                    "update_memory_md": {
                        "type": "boolean",
                        "description": "If true, appends to MEMORY.md (permanent) instead of just the daily log.",
                        "default": False
                    },
                    "section": {
                        "type": "string",
                        "enum": ["key_facts", "user_preferences", "learned_behaviors", "current_projects"],
                        "description": "Which section of MEMORY.md to append to. Only used if update_memory_md is true.",
                        "default": "key_facts"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search stored memories by query. Use when the user asks about something that might be in memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results.",
                        "default": 5
                    },
                    "keyword_only": {
                        "type": "boolean",
                        "description": "Use keyword-only search (no API cost). Set to false for semantic search if OPENAI_API_KEY is available.",
                        "default": True
                    },
                    "type": {
                        "type": "string",
                        "enum": ["fact", "preference", "event", "insight", "task", "relationship"],
                        "description": "Filter results by memory type."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_db",
            "description": "Direct database operations: list all entries, get a specific entry by ID, delete an entry, get stats, or get recent entries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "get", "delete", "stats", "recent", "search"],
                        "description": "The database operation to perform."
                    },
                    "id": {
                        "type": "integer",
                        "description": "Entry ID. Required for get and delete actions."
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query. Required for search action."
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by memory type."
                    },
                    "hours": {
                        "type": "integer",
                        "description": "For recent action: how many hours back to look.",
                        "default": 24
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results for list/search/recent.",
                        "default": 20
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_goal",
            "description": "Read a goal definition file. Goals define process workflows in the GOTCHA framework. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Goal filename to read. Use 'manifest.md' to see all available goals, or a specific goal like 'build_app.md'."
                    }
                },
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "journal_read_recent",
            "description": "Read the user's recent journal entries (from Obsidian export CSV). Use when the user asks about their priorities, what they need to do, what's on their mind, or what they've been thinking — recent journal text often states goals and to-dos. Returns last N days of entries with date and entry text. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days of journal entries to return (default 7).",
                        "default": 7
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_read",
            "description": "Read the user's reminders (Tony Reminders.md: Today, Later This Week, Shopping, etc.). Use when the user asks what they need to remember, what their reminders are, or what's on their reminder list. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "heartbeat_read",
            "description": "Read the user's heartbeat checklist (HEARTBEAT.md) and state. Use when the user asks 'am I on track?', 'how's my week?', or how they're doing against their checklist. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Trial prep (Case Prep Guide + templates in Obsidian Trials/)
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "trial_read_guide",
            "description": "Read the DUI Case Prep Guide. Use at the start of trial prep to understand the workflow and template order.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trial_list_cases",
            "description": "List case folders under Trials/ (by year and last name). Use to confirm which case to prep or to show the user available cases.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trial_list_templates",
            "description": "List available DUI trial templates (Theme Document, Opening Statement, etc.). Use to know which template to work through next.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trial_read_template",
            "description": "Read one trial template by filename. Use to get the sections and questions to ask the user. Example: 'DUI - Theme Document.md'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_name": {
                        "type": "string",
                        "description": "Template filename, e.g. 'DUI - Theme Document.md', 'DUI - Opening Statement.md'."
                    }
                },
                "required": ["template_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trial_save_document",
            "description": "Save a filled trial document to the case folder. Use after completing one template with the user's answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "string", "description": "Case year folder, e.g. '2026'."},
                    "case_name": {"type": "string", "description": "Case folder name (last name), e.g. 'Nelson'."},
                    "document_name": {"type": "string", "description": "Document filename to save, e.g. 'Theme Document.md' or 'Motion in Limine - HGN Testimony.md'."},
                    "content": {"type": "string", "description": "Full markdown content of the filled document."}
                },
                "required": ["year", "case_name", "document_name", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the atlas repo. Use when the user asks you to look at, compare, or inspect a script or config file. Path is relative to the repo root (e.g. 'tools/briefings/daily_brief.py', 'tools/manifest.md', 'args/telegram.yaml'). Only files inside the repo are accessible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the repo root, e.g. 'tools/briefings/daily_brief.py'."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory inside the atlas repo. Use when the user asks what scripts or files exist in a folder, or when you need to discover what's available before reading. Path is relative to repo root (e.g. 'tools/briefings', 'tools/legal'). Omit path to list the repo root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to repo root. Omit or set to '' for repo root.",
                        "default": ""
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reminder_add",
            "description": "Add a reminder to Tony Reminders.md. Use when the user says 'remind me to...', 'add a reminder', or similar. Supports scheduling: weekly <day>, daily, monthly, tomorrow, in N days, next <weekday>, specific dates (2/15, feb 15). Omit schedule for today.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "What to be reminded about, e.g. 'call dentist' or 'review agenda'."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "When: 'tomorrow', 'weekly thu', 'in 3 days', 'monday', '2/15', 'feb 20', 'monthly', 'daily'. Omit or empty for today.",
                        "default": ""
                    }
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tool",
            "description": "Run an allowlisted briefing or heartbeat script. Use when the user asks for a daily brief, research brief, news briefing, local news, or a heartbeat check. Script output is returned as the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_name": {
                        "type": "string",
                        "enum": ["daily_brief", "research_brief", "local_news", "news_briefing", "run_heartbeat"],
                        "description": "Which script to run: daily_brief (6am brief with case law), research_brief (3pm tech+Kraken), local_news, news_briefing, run_heartbeat (heartbeat checklist)."
                    }
                },
                "required": ["script_name"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Web search (Brave API)
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Use when the user asks to look something up, browse the internet, or find facts that are not in memory. Returns titles, URLs, and snippets. Requires BRAVE_API_KEY in .env.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'DUI Washington public parking lot not on road')."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Maximum number of results to return (1-20). Default 5.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Bambu 3D printer (bambu-cli; local network)
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "bambu",
            "description": "Query or control the Bambu 3D printer on the local network. Use for status checks, AMS filament info, print control, and light toggle. Confirm with the user before pausing or stopping a print.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["status", "ams", "pause", "resume", "stop", "light_on", "light_off"],
                        "description": "status: current state + progress + temps. ams: AMS tray filament info. pause/resume/stop: print control (confirm first). light_on/light_off: toggle chamber light."
                    }
                },
                "required": ["action"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Browser search (DuckDuckGo HTML — no API key, no Selenium)
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": "Search the web via DuckDuckGo. No API key required — works as a fallback when Brave search is unavailable. Returns titles, URLs, and snippets just like web_search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Maximum number of results to return (1-10). Default 5.",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Browser (Safari via Selenium; requires browser server running)
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": "Control Safari for web research: navigate to a URL, get a snapshot of the page (title + content), click elements, type into fields, or take a screenshot. Start the browser server first (python tools/browser/browser_server.py).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["navigate", "snapshot", "click", "type", "screenshot", "close", "status"],
                        "description": "navigate: open a URL. snapshot: get page title and content. click: click an element. type: type text into an element. screenshot: capture screen. close: close browser. status: check if browser is open and current URL."
                    },
                    "url": {
                        "type": "string",
                        "description": "For navigate: URL to open (e.g. https://example.com)."
                    },
                    "selector": {
                        "type": "string",
                        "description": "For click or type: CSS selector (e.g. 'button#submit', 'input[name=q]') or XPath if by is xpath."
                    },
                    "by": {
                        "type": "string",
                        "enum": ["css", "xpath", "id", "name"],
                        "description": "How to find the element. Default: css.",
                        "default": "css"
                    },
                    "text": {
                        "type": "string",
                        "description": "For type: text to type into the element."
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "For snapshot: maximum characters of page content to return (default 50000).",
                        "default": 50000
                    }
                },
                "required": ["action"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Google / Gmail via Zapier MCP
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "gmail_create_draft",
            "description": "Create a draft email in Gmail. Provide the recipient, subject, and body. The draft will appear in the user's Gmail for review before sending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Natural-language description of the email to draft, including who it's to, the tone, and what it should say."
                    },
                    "to": {
                        "type": "string",
                        "description": "Recipient email address."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line."
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body text."
                    },
                    "cc": {
                        "type": "string",
                        "description": "CC email address(es), comma-separated."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_find_calendars",
            "description": "List all Google Calendars the user has access to. Call this first if the user wants to create or search events on a specific (non-primary) calendar, to get the calendar ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Describe what you need, e.g. 'list all my calendars'."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_find_events",
            "description": "Search for events in Google Calendar by time range or keyword. Use when the user asks about upcoming events or wants to find a specific event. NOTE: Zapier's field naming is inverted — end_time is the EARLIER boundary and start_time is the LATER boundary. Example: to find events on Feb 3, set end_time='2026-02-03T00:00:00' and start_time='2026-02-03T23:59:00'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Describe what events you're looking for and when."
                    },
                    "calendarid": {
                        "type": "string",
                        "description": "Calendar ID. Omit to use the primary calendar."
                    },
                    "search_term": {
                        "type": "string",
                        "description": "Keyword to filter events by title or description."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "LATER time boundary (upper bound). ISO 8601, e.g. '2026-02-04T23:59:00'."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "EARLIER time boundary (lower bound). ISO 8601, e.g. '2026-02-03T00:00:00'."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_create_detailed_event",
            "description": "Create an event in Google Calendar with full details: title, time, location, attendees, recurrence, etc. Note: date/time fields use double underscores (start__dateTime, end__dateTime).",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Describe the event to create, including date, time, title, and any other details."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Event title."
                    },
                    "start__dateTime": {
                        "type": "string",
                        "description": "Start date/time, ISO 8601. e.g. '2026-02-04T10:00:00'."
                    },
                    "end__dateTime": {
                        "type": "string",
                        "description": "End date/time, ISO 8601. e.g. '2026-02-04T11:00:00'."
                    },
                    "description": {
                        "type": "string",
                        "description": "Event description or notes."
                    },
                    "location": {
                        "type": "string",
                        "description": "Event location."
                    },
                    "calendarid": {
                        "type": "string",
                        "description": "Calendar ID. Omit for primary calendar."
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "If true, creates an all-day event."
                    },
                    "attendees": {
                        "type": "string",
                        "description": "Comma-separated attendee email addresses."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_retrieve_event_by_id",
            "description": "Get full details of a specific Google Calendar event by its ID. Use after find_events to get the complete event data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Describe which event you want to retrieve."
                    },
                    "event_id": {
                        "type": "string",
                        "description": "The event ID (returned by find_events)."
                    },
                    "calendarid": {
                        "type": "string",
                        "description": "Calendar ID containing the event."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_move_event_to_another_calendar",
            "description": "Move an existing event from one calendar to another. Requires the event ID and the destination calendar ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Describe which event to move and to which calendar."
                    },
                    "event_id": {
                        "type": "string",
                        "description": "The event ID to move."
                    },
                    "calendarid": {
                        "type": "string",
                        "description": "Source calendar ID."
                    },
                    "destination_calendar_id": {
                        "type": "string",
                        "description": "Target calendar ID."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "google_calendar_find_busy_periods_in_calendar",
            "description": "Find busy time slots in a Google Calendar within a date range. Useful for scheduling — shows when the user is already occupied. Same inverted time naming as find_events: end_time = earlier boundary, start_time = later boundary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": "Describe the time range to check for busy periods."
                    },
                    "calendarid": {
                        "type": "string",
                        "description": "Calendar ID. Omit for primary calendar."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "LATER time boundary (upper bound). ISO 8601."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "EARLIER time boundary (lower bound). ISO 8601."
                    }
                },
                "required": ["instructions"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Telegram groups
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "telegram_groups",
            "description": "Query known Telegram groups (autodetected when bot receives messages in groups). Use to find group chat IDs for routing briefings or messages. Returns list of groups with IDs, titles, and types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "find"],
                        "description": "list: return all known groups. find: search for a group by name."
                    },
                    "name": {
                        "type": "string",
                        "description": "For find action: group name or partial name to search for."
                    }
                },
                "required": ["action"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # System configuration and automation
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "system_config",
            "description": "Configure system automations: update chat IDs for briefings, manage cron schedules, create new monitors (YouTube, RSS). Use when the user wants to set up recurring automations, change when/where briefings are sent, or monitor external sources. IMPORTANT: Always explain what you're about to do and get confirmation before making changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["update_chat_id", "add_cron", "remove_cron", "update_cron_time", "create_youtube_monitor", "list_automations"],
                        "description": "update_chat_id: change where a briefing sends. add_cron: schedule a new automation. remove_cron: stop an automation. update_cron_time: change schedule. create_youtube_monitor: watch YouTube channel for new videos. list_automations: show all active automations."
                    },
                    "script_name": {
                        "type": "string",
                        "enum": ["daily_brief", "research_brief", "local_news", "weekly_review"],
                        "description": "For update_chat_id: which briefing to update."
                    },
                    "chat_id": {
                        "type": "string",
                        "description": "Telegram chat ID (group or individual). For groups, the bot must be a member. User should provide this ID."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Cron schedule. Examples: '0 6 * * *' (6am daily), '0 17 * * *' (5pm daily), '0 12 * * 1' (noon Mondays), '*/15 * * * *' (every 15 min)."
                    },
                    "script_path": {
                        "type": "string",
                        "description": "For add_cron: path to script relative to repo root (e.g., 'tools/briefings/daily_brief.py')."
                    },
                    "pattern": {
                        "type": "string",
                        "description": "For remove_cron or update_cron_time: substring to match in cron job command (e.g., 'daily_brief.py')."
                    },
                    "youtube_url": {
                        "type": "string",
                        "description": "For create_youtube_monitor: YouTube channel URL (e.g., 'https://youtube.com/@username')."
                    },
                    "comment": {
                        "type": "string",
                        "description": "Optional comment for cron job entry."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "script_writer",
            "description": "Generate a Python script from natural language description. Use when the user asks for custom automation, a one-off task, or wants you to write a script. Creates a working Python script with proper error handling, logging, and integration with atlas patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Natural language description of what the script should do. Be detailed about inputs, outputs, and behavior."
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Where to save the script relative to repo root. E.g., 'tools/custom/my_script.py' or 'tools/monitors/check_website.py'."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Optional cron schedule if this should run automatically. E.g., '0 17 * * *' for 5pm daily."
                    }
                },
                "required": ["task_description", "output_path"]
            }
        }
    },
    # ---------------------------------------------------------------------------
    # Conversation intelligence & learning
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "conversation_context",
            "description": "Get recent conversation history and detected patterns. Use to maintain context across messages, understand what user meant by 'that' or 'it', and learn from past interactions. Call this when user references previous conversation or when you need to understand repeated patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["recent", "patterns", "corrections"],
                        "description": "recent: get last N conversation turns. patterns: get detected behavioral patterns. corrections: get summary of times user corrected you."
                    },
                    "hours": {
                        "type": "integer",
                        "description": "For recent action: how many hours of history to fetch (default 24).",
                        "default": 24
                    },
                    "limit": {
                        "type": "integer",
                        "description": "For recent action: max conversation turns to return (default 20).",
                        "default": 20
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "proactive_intelligence",
            "description": "Get proactive suggestions and insights based on patterns, context, and time. Use when you want to anticipate user needs, surface relevant information before being asked, or provide context-aware nudges. Call this at start of conversation or when user asks open-ended questions like 'what should I focus on?'",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["suggestions", "brief", "intent"],
                        "description": "suggestions: get list of proactive suggestions. brief: get formatted brief for display. intent: predict intent from partial message."
                    },
                    "text": {
                        "type": "string",
                        "description": "For intent action: partial user message to analyze."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_correction",
            "description": "Log when user corrects your response. Use when user says you're wrong, provides a correction, or clarifies something you misunderstood. This helps you learn and improve over time. IMPORTANT: Always call this when corrected so the system learns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "original_response": {
                        "type": "string",
                        "description": "What you said that was wrong or unclear."
                    },
                    "correction": {
                        "type": "string",
                        "description": "What the user said to correct you."
                    },
                    "learned_pattern": {
                        "type": "string",
                        "description": "Brief description of what to remember (e.g., 'User prefers metric units' or 'Client name is Smith not Smyth')."
                    }
                },
                "required": ["original_response", "correction", "learned_pattern"]
            }
        }
    }
]
