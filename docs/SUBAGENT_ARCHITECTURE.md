# Atlas Subagent Architecture Implementation

**Date:** 2026-02-09
**Status:** ✅ Complete

## Quick Summary

Implemented full subagent architecture for Atlas to address context confusion when handling multiple complex workflows. Five specialized agents (Telegram, Bambu, LegalKanban, Briefings, System) now handle domain-specific tasks with focused context, preventing tool loops and enabling parallel execution.

**Result:** Reduced cognitive load, isolated errors, clearer debugging, organized goals by domain.

## Files Created

### Core Infrastructure
- `router.py` — Keyword-based agent routing with auto/explicit/dry-run modes
- `agents/README.md` — Full architecture documentation (32KB)
- `agents/QUICKSTART.md` — Quick usage guide
- `agents/invoke.sh` — Invocation wrapper script
- `agents/status.sh` — Agent status dashboard

### Agent Files (5 agents × 3 directories each)

**Telegram Agent** (`agents/telegram/`):
- `goals/conversation_management.md` — Conversation workflow, tool loop prevention
- `context/tool_safeguards.md` — Tool design rules, recovery procedures
- `args/telegram.yaml` — Bot config (models, limits, timeouts)

**Bambu Agent** (`agents/bambu/`):
- `goals/print_tracking.md` — BambuBuddy integration, FTP fallback, reply parsing
- `context/printer_specs.md` — Printer specs, filament types, reply formats
- `args/bambu.yaml` — Polling config, BambuBuddy paths, JeevesUI integration

**LegalKanban Agent** (`agents/legalkanban/`):
- `goals/task_sync.md` — Bidirectional sync workflow (pull/push)
- `context/task_format.md` — Task format specs, database schema, priority mapping
- `args/legalkanban.yaml` — Sync schedule, database config, user mapping

**Briefings Agent** (`agents/briefings/`):
- `goals/daily_operations.md` — Daily/research/weekly briefs, health monitoring
- `args/briefings.yaml` — Schedules, components, thresholds, credentials

**System Agent** (`agents/system/`):
- `goals/automation_management.md` — Cron/launchd management, health checks
- `context/launchd_vs_cron.md` — Decision tree, Keychain access patterns
- `args/system.yaml` — Health checks, watchdog config, backup settings

### Documentation Updates
- Updated `CLAUDE.md` — Integrated subagent architecture into system handbook
- Created `docs/SUBAGENT_ARCHITECTURE.md` — This implementation summary

## Usage

```bash
# Auto-route based on keywords
python3 router.py "Fix Telegram bot tool loop"

# Explicit agent selection
python3 router.py --agent bambu "Debug print detection"

# Test routing (dry-run)
python3 router.py --dry-run "Task description"

# List all agents
python3 router.py --list-agents

# Agent status dashboard
./agents/status.sh
```

## Architecture Benefits

1. **Context Isolation** — Each agent focuses on one domain, no cross-contamination
2. **Error Containment** — Failures isolated to specific agents
3. **Parallel Execution** — Independent workflows run concurrently
4. **Easier Debugging** — Clear which agent to examine when something breaks
5. **Goal Organization** — Domain-specific goals, easy to find
6. **Specialized Knowledge** — Agent-specific context files

## Agent Routing Keywords

| Agent | Keywords |
|-------|----------|
| telegram | telegram, bot, conversation, message, chat, jeeves |
| bambu | bambu, print, 3d, printer, filament, spool, ams |
| legalkanban | case, legalkanban, task sync, deadline, trial, client |
| briefings | brief, news, weather, reminder, health, wellness, weekly, review |
| system | cron, launchd, config, monitor, health, backup, service |

## Philosophy

> **"One agent, one focus, one job done right."**

Subagents reduce complexity through specialization. The router coordinates, each agent executes.

## See Also

- `agents/README.md` — Full architecture guide
- `agents/QUICKSTART.md` — Usage examples
- `CLAUDE.md` — Updated system handbook
