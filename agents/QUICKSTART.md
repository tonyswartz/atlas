# Agent Quickstart Guide

## What Are Agents?

Agents are **specialized orchestrators** that focus on specific domains (Telegram, Bambu, LegalKanban, etc.) with their own goals, context, and configuration.

**Why?** Prevents context confusion, isolates errors, enables parallel execution.

## Available Agents

| Agent | Purpose | Keywords |
|-------|---------|----------|
| **telegram** | Bot conversation management | telegram, bot, message, chat |
| **bambu** | 3D print tracking | bambu, print, 3d, printer, filament |
| **legalkanban** | Case management, task sync | case, legalkanban, task sync, trial |
| **briefings** | News, weather, reminders, health | brief, news, weather, reminder, health |
| **system** | Automation, health checks, backups | cron, launchd, config, monitor, backup |

## Quick Usage

### Auto-Route (Recommended)

Let the router pick the right agent based on keywords:

```bash
# From repo root
python router.py "Fix Telegram bot tool loop"
python router.py "Why aren't Bambu prints being detected?"
python router.py "Check LegalKanban task sync status"
```

### Explicit Agent Selection

Force a specific agent:

```bash
python router.py --agent telegram "Debug conversation.py"
python router.py --agent bambu "Test BambuBuddy watcher"
python router.py --agent system "List all cron jobs"
```

### List All Agents

```bash
python router.py --list-agents
```

### Dry Run (Test Routing)

See which agent would be selected without invoking:

```bash
python router.py --dry-run "Task description here"
```

## Examples

### Telegram Agent

```bash
# Auto-routed (contains "telegram" and "bot")
python router.py "Telegram bot is hitting tool loop limit"

# Explicit
python router.py --agent telegram "Add new tool to tool_definitions.py"

# What it does:
# - Loads agents/telegram/goals/conversation_management.md
# - Loads agents/telegram/context/tool_safeguards.md
# - Loads agents/telegram/args/telegram.yaml
# - Focuses ONLY on Telegram bot context
```

### Bambu Agent

```bash
# Auto-routed
python router.py "Bambu prints not being detected from Handy app"

# Explicit
python router.py --agent bambu "Debug bambu_buddy_watcher.py"

# What it does:
# - Loads agents/bambu/goals/print_tracking.md
# - Loads agents/bambu/context/printer_specs.md
# - Loads agents/bambu/args/bambu.yaml
# - Focuses on 3D printer tracking
```

### LegalKanban Agent

```bash
# Auto-routed
python router.py "LegalKanban tasks not syncing to Tony Tasks"

# Explicit
python router.py --agent legalkanban "Create new task for Nelson case"

# What it does:
# - Loads agents/legalkanban/goals/task_sync.md
# - Loads agents/legalkanban/context/task_format.md
# - Loads agents/legalkanban/args/legalkanban.yaml
# - Focuses on case management and task sync
```

### Briefings Agent

```bash
# Auto-routed
python router.py "Daily brief not sending weather data"

# Explicit
python router.py --agent briefings "Add new RSS feed to research brief"

# What it does:
# - Loads agents/briefings/goals/daily_operations.md
# - Loads agents/briefings/args/briefings.yaml
# - Focuses on news aggregation and monitoring
```

### System Agent

```bash
# Auto-routed
python router.py "Add new launchd job for health monitoring"

# Explicit
python router.py --agent system "Generate script to monitor disk space"

# What it does:
# - Loads agents/system/goals/automation_management.md
# - Loads agents/system/context/launchd_vs_cron.md
# - Loads agents/system/args/system.yaml
# - Focuses on automation configuration
```

## When to Use Main Orchestrator (No Agent)

Skip agent routing for:
- **Cross-domain tasks** — "Set up workflow that reads calendar, creates tasks in LegalKanban, and sends Telegram notification"
- **One-off exploration** — "Search codebase for all uses of memory_write"
- **Simple file operations** — "Read CLAUDE.md and explain the GOTCHA framework"

Just invoke Claude directly:
```bash
claude -p "Explain the GOTCHA framework from CLAUDE.md"
```

## Troubleshooting

### "Agent not found"
- Check agent name: `python router.py --list-agents`
- Valid names: telegram, bambu, legalkanban, briefings, system

### "Wrong agent selected"
- Use explicit routing: `--agent telegram`
- Or add keywords to task: "Fix Telegram bot tool loop"

### "Agent not loading context"
- Verify agent directory exists: `ls agents/telegram/`
- Check for goals/context/args subdirectories

### "Tools not working in agent context"
- Tools are shared across agents
- Check tool requirements (credentials, paths)
- Verify args files have correct paths

## Advanced: Creating New Agents

See `agents/README.md` for full guide on extending the agent system.

Quick steps:
1. Create `agents/new_agent/{goals,context,args}/`
2. Write agent-specific files
3. Update `router.py` with keywords
4. Test routing: `python router.py --dry-run "task with keywords"`

## Philosophy

> **One agent, one focus, one job done right.**

Agents reduce complexity through specialization.

The router coordinates.
Each agent executes.

That's the power of focused context.
