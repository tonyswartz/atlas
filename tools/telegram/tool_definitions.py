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
            "name": "kanban_read",
            "description": "Read the user's task list (Tony Tasks.md), including LegalKanban-synced case tasks. Use when the user asks about their tasks, what they need to do, priorities, or what's on their plate. Read-only.",
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
    # Rotary agenda (interactive agenda creation)
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "rotary_read_log",
            "description": "Read the Rotary Log to get the next scheduled meeting date, member spotlight, and speaker info. Use at the start of agenda creation.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rotary_read_template",
            "description": "Read the Rotary agenda template. Use this to get the template structure before filling it in with user-provided details.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rotary_read_agenda",
            "description": "Read an existing Rotary agenda by date. Use this to fetch an agenda so you can add content to it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_date": {
                        "type": "string",
                        "description": "Meeting date in YYYY-MM-DD format (e.g., '2026-02-10')."
                    }
                },
                "required": ["meeting_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rotary_save_agenda",
            "description": "Save a completed Rotary meeting agenda. Use after collecting all details from the user and filling in the template.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The complete agenda content (markdown) with all fields filled in."
                    },
                    "meeting_date": {
                        "type": "string",
                        "description": "Meeting date in YYYY-MM-DD format (e.g., '2026-02-10'). Used to determine save path."
                    }
                },
                "required": ["content", "meeting_date"]
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
            "name": "edit_file",
            "description": "Edit a podcast episode script in the repo. Use when the user approves script changes. Only works for paths under data/podcast_episodes/<episode_id>/ (e.g. data/podcast_episodes/sololaw-031/script_approved.md). Changes are synced to Obsidian automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repo-relative path, e.g. 'data/podcast_episodes/sololaw-031/script_approved.md' or '.../script_draft.md'."
                    },
                    "content": {
                        "type": "string",
                        "description": "Full new content of the file (replaces entire file)."
                    }
                },
                "required": ["path", "content"]
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
            "name": "reminder_mark_done",
            "description": "Mark one or more reminders as done in Tony Reminders.md. Use when the user says 'mark X as done', 'done with X', 'completed X', or lists reminders to check off. Matches by reminder text; include date tag like [26-02-03] if there are multiple (e.g. 'Garbage/Recycling [26-02-03]').",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of reminder text to mark done, e.g. ['Bins to curb', 'Garbage/Recycling [26-02-03]']. Match by substring; optional [YY-MM-DD] to target a specific occurrence."
                    }
                },
                "required": ["items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "legalkanban_search_cases",
            "description": "Search open LegalKanban cases by name (e.g. last name). Use when the user says which case a task is for and gives a name — search to get case ID for legalkanban_create_task. Returns list of { id, name }.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search string, e.g. last name like 'Nelson' or 'Smith'."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "legalkanban_create_task",
            "description": "Create a task in LegalKanban (syncs to Tony Tasks.md). Use only after user confirmed the task should go in LegalKanban and you have case_id (from legalkanban_search_cases when user gave a case name). Result includes case_name — use it in your reply (e.g. 'Added to Nelson'), not the case ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Task title."
                    },
                    "case_id": {
                        "type": "integer",
                        "description": "LegalKanban case ID (from legalkanban_search_cases). Omit only if task is not tied to a case."
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority. Default medium.",
                        "default": "medium"
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date YYYY-MM-DD."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional task description."
                    }
                },
                "required": ["title"]
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
    # Web search (Brave API) - FALLBACK ONLY
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "FALLBACK search API (Brave). Only use if browser_search fails. Requires API key and has rate limits. Prefer browser_search instead.",
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
    # Browser search (DuckDuckGo HTML — no API key, no Selenium) - PRIMARY SEARCH
    # ---------------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": "PRIMARY web search tool. Search the web via DuckDuckGo (no API key needed, no rate limits). Returns titles, URLs, and snippets. Use this for any web search query including road conditions, weather, news, or general questions. Fast and reliable.",
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
            "description": "Controls Safari to navigate to websites and scrape content. IMPORTANT: Always provide the FULL, CORRECT URL (e.g., https://youtube.com/@username NOT youtube.com/c/username). Use when you know the exact URL. Steps: 1) navigate to URL with full https://... 2) snapshot to get content. If you don't know the exact URL, use browser_search first to find it, then use this tool with the correct URL.",
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
            "description": "Search for events in Google Calendar by time range or keyword. Use when the user asks about upcoming events or wants to find a specific event. Use start_time for the beginning of the range and end_time for the end of the range (normal conventions - zapier_runner handles the Zapier inversion automatically).",
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
                        "description": "Start of time range (lower bound). ISO 8601, e.g. '2026-02-03T00:00:00'."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End of time range (upper bound). ISO 8601, e.g. '2026-02-04T23:59:00'."
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
            "description": "Find busy time slots in a Google Calendar within a date range. Useful for scheduling — shows when the user is already occupied. Use start_time for the beginning of the range and end_time for the end (zapier_runner handles the Zapier inversion automatically).",
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
                        "description": "Start of time range (lower bound). ISO 8601."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End of time range (upper bound). ISO 8601."
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
            "name": "podcast_create_episode",
            "description": "Create a new podcast episode from an idea. This triggers script generation, which will send a preview to Telegram for approval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "podcast": {
                        "type": "string",
                        "enum": ["explore", "sololaw", "832weekends"],
                        "description": "Which podcast this episode is for (explore=Explore with Tony, sololaw=Solo Law Club, 832weekends=832 Weekends)"
                    },
                    "idea": {
                        "type": "string",
                        "description": "The episode idea, topic, or outline provided by the user"
                    }
                },
                "required": ["podcast", "idea"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "podcast_approve_script",
            "description": "Approve a podcast script and trigger voice synthesis + audio mixing. Only call this when the user explicitly approves a script.",
            "parameters": {
                "type": "object",
                "properties": {
                    "episode_id": {
                        "type": "string",
                        "description": "The episode ID to approve (e.g., 'sololaw-030')"
                    },
                    "pronunciation_fixes": {
                        "type": "object",
                        "description": "Optional one-off pronunciation fixes for this episode (word -> pronunciation mapping)",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["episode_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "podcast_regenerate_voice",
            "description": "Regenerate voice and audio for an existing episode after the user has manually edited the script. Reads the approved script from Obsidian and re-runs TTS synthesis and mixing. Use when user says 'regenerate', 'redo', 'create new version', 'i edited the script', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "episode_id": {
                        "type": "string",
                        "description": "The episode ID to regenerate (e.g., 'sololaw-030')"
                    },
                    "pronunciation_fixes": {
                        "type": "object",
                        "description": "Optional one-off pronunciation fixes for this episode (word -> pronunciation mapping)",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["episode_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "podcast_regenerate_paragraph",
            "description": "Regenerate a specific paragraph of an episode after editing. Much faster and cheaper than regenerating the entire episode. Use when user says 'regenerate paragraph 3', 'redo the part about X', 'fix paragraph with cadence issue', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "episode_id": {
                        "type": "string",
                        "description": "The episode ID (e.g., 'sololaw-030')"
                    },
                    "paragraph_number": {
                        "type": "integer",
                        "description": "The paragraph number to regenerate (0-based index). Use this if user specifies a number."
                    },
                    "search_term": {
                        "type": "string",
                        "description": "Search term to find the paragraph (e.g., 'Kanban system'). Use this if user describes the content rather than number."
                    },
                    "pronunciation_fixes": {
                        "type": "object",
                        "description": "Optional one-off pronunciation fixes for this paragraph (word -> pronunciation mapping)",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["episode_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_read",
            "description": "Read the current podcast schedule from Schedule.md file. Shows all scheduled episodes with dates, titles, and details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "podcast_id": {
                        "type": "string",
                        "enum": ["sololaw", "832weekends", "explore"],
                        "description": "The podcast to read the schedule for"
                    }
                },
                "required": ["podcast_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_preview",
            "description": "Preview what the schedule will look like with the proposed episodes. Shows formatted markdown preview before saving.",
            "parameters": {
                "type": "object",
                "properties": {
                    "podcast_id": {
                        "type": "string",
                        "enum": ["sololaw", "832weekends", "explore"],
                        "description": "The podcast for the schedule"
                    },
                    "episodes": {
                        "type": "array",
                        "description": "Array of episode objects to preview",
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {
                                    "type": "string",
                                    "description": "Episode date in YYYY-MM-DD format"
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Episode title"
                                },
                                "theme": {
                                    "type": "string",
                                    "description": "Episode theme (for 832weekends)"
                                },
                                "key_points": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Key discussion points for the episode"
                                },
                                "show_notes": {
                                    "type": "string",
                                    "description": "Show notes (2-3 sentences)"
                                }
                            },
                            "required": ["date", "title", "key_points", "show_notes"]
                        }
                    }
                },
                "required": ["podcast_id", "episodes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_add",
            "description": "Add episodes to the podcast schedule. Appends to the existing Schedule.md file. Use after user approves the preview.",
            "parameters": {
                "type": "object",
                "properties": {
                    "podcast_id": {
                        "type": "string",
                        "enum": ["sololaw", "832weekends", "explore"],
                        "description": "The podcast to add episodes to"
                    },
                    "episodes": {
                        "type": "array",
                        "description": "Array of episode objects to add",
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {
                                    "type": "string",
                                    "description": "Episode date in YYYY-MM-DD format"
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Episode title"
                                },
                                "theme": {
                                    "type": "string",
                                    "description": "Episode theme (for 832weekends)"
                                },
                                "key_points": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Key discussion points for the episode"
                                },
                                "show_notes": {
                                    "type": "string",
                                    "description": "Show notes (2-3 sentences)"
                                }
                            },
                            "required": ["date", "title", "key_points", "show_notes"]
                        }
                    }
                },
                "required": ["podcast_id", "episodes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "script_writer",
            "description": "Generate and save Python scripts from natural language descriptions. Can create templates or save custom code. Use this when building automation scripts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["generate", "save", "validate"],
                        "description": "Action to perform: generate (create script template), save (write script to file), validate (check syntax)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Natural language description of what the script should do (for generate action)"
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code to save or validate (for save/validate actions)"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Script filename without path (saved to tools/scripts/). For save action."
                    },
                    "imports": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of import statements to include (for generate action). Example: ['import requests', 'from pathlib import Path']"
                    },
                    "use_envchain": {
                        "type": "boolean",
                        "description": "Whether script needs credentials from envchain/Keychain (for generate action)",
                        "default": False
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "launchd_manager",
            "description": "Create, load, unload, or list launchd jobs for scheduling scripts. Use this to make scripts run automatically on a schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "load", "unload", "list"],
                        "description": "Action: create (make plist), load (start job), unload (stop job), list (show all jobs)"
                    },
                    "script_path": {
                        "type": "string",
                        "description": "Path to script relative to repo root (e.g., 'tools/scripts/my_script.py'). For create action."
                    },
                    "label": {
                        "type": "string",
                        "description": "Job label/name (e.g., 'daily-calendar-brief'). Will be prefixed with 'com.atlas.' automatically."
                    },
                    "schedule": {
                        "type": "string",
                        "description": "Human-readable schedule. Examples: 'every 5 minutes', 'daily at 9am', 'every weekday at 5pm', 'every hour'"
                    },
                    "run_at_load": {
                        "type": "boolean",
                        "description": "Whether to run script immediately when job loads",
                        "default": False
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of what this job does"
                    }
                },
                "required": ["action"]
            }
        }
    }
]
