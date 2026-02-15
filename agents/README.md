# Atlas Subagent Architecture

## Overview

The Atlas GOTCHA framework now uses **specialized subagents** to manage complex workflows. Each agent focuses on a specific domain, with its own goals, context, and configuration.

## Why Subagents?

**Problem:** A single orchestrator juggling 17 different tool domains (Telegram, Bambu, LegalKanban, briefings, etc.) leads to:
- Context confusion and mixing
- Tool loop bugs (hitting limits while juggling multiple concerns)
- Difficult debugging (which domain caused the error?)
- High cognitive load

**Solution:** Domain-isolated agents with focused responsibilities
- Each agent specializes in one workflow area
- Clear boundaries prevent context bleeding
- Errors contained to specific agents
- Parallel execution of independent workflows

## Available Agents

### 🤖 Telegram Agent (`agents/telegram/`)
**Purpose:** Conversation management, tool routing, session handling

**Responsibilities:**
- Process user messages
- Route to appropriate tools
- Manage conversation state
- Prevent tool loops
- Handle timeouts

**Key Files:**
- `goals/conversation_management.md` — Conversation workflow
- `context/tool_safeguards.md` — Tool loop prevention
- `args/telegram.yaml` — Bot configuration

**Tools Used:** telegram, memory, zapier, research, browser, legalkanban, capture

---

### 🖨️ Bambu Agent (`agents/bambu/`)
**Purpose:** 3D print tracking, spool management, JeevesUI logging

**Responsibilities:**
- Detect completed prints (BambuBuddy + FTP)
- Prompt user for spool usage
- Parse replies and log to JeevesUI
- Monitor printer health

**Key Files:**
- `goals/print_tracking.md` — Print tracking workflow
- `context/printer_specs.md` — Printer and filament specs
- `args/bambu.yaml` — Polling and integration config

**Tools Used:** bambu, memory

---

### ⚖️ LegalKanban Agent (`agents/legalkanban/`)
**Purpose:** Case management, task sync, deadline tracking

**Responsibilities:**
- Pull incomplete tasks from LegalKanban
- Push completions and due date changes
- Search cases by name
- Create case-related tasks

**Key Files:**
- `goals/task_sync.md` — Bidirectional sync workflow
- `context/task_format.md` — Task format specifications
- `args/legalkanban.yaml` — Sync configuration

**Tools Used:** legalkanban, memory

---

### 📰 Briefings Agent (`agents/briefings/`)
**Purpose:** News aggregation, weather, reminders, health monitoring

**Responsibilities:**
- Daily brief (6 AM): weather, reminders, calendar, case law
- Research brief (3 PM): tech news
- Weekly review (Friday 5 PM): journal stats, fitness, kanban health
- Health monitoring: Oura data anomalies
- Wellness coaching: Recovery-aware fitness advice

**Key Files:**
- `goals/daily_operations.md` — Briefing workflows
- `args/briefings.yaml` — Schedule and component config

**Tools Used:** briefings, memory

---

### ⚙️ System Agent (`agents/system/`)
**Purpose:** Automation config, health checks, backups, monitoring

**Responsibilities:**
- Configure cron and launchd jobs
- Monitor service health
- Generate Python scripts from descriptions
- Scan logs for errors (watchdog)
- Manage backups

**Key Files:**
- `goals/automation_management.md` — Automation workflows
- `context/launchd_vs_cron.md` — Scheduling guidance
- `args/system.yaml` — Health check config

**Tools Used:** system, heartbeat, memory

---

## Agent Structure

Each agent has the same directory structure:

```
agents/{agent_name}/
├── goals/          # What this agent needs to achieve
├── context/        # Domain knowledge (specs, formats, patterns)
└── args/           # Behavior configuration (schedules, thresholds)
```

**Tools remain shared** in the main `tools/` directory. Agents use subsets of tools relevant to their domain.

## Using Agents

### Automatic Routing

The **router.py** script analyzes task descriptions and routes to the appropriate agent:

```bash
# Auto-routes to Telegram agent
python router.py "Fix Telegram bot tool loop"

# Auto-routes to Bambu agent
python router.py "Why aren't prints being detected?"

# Auto-routes to LegalKanban agent
python router.py "Debug task sync with LegalKanban"
```

### Explicit Agent Selection

Specify an agent directly:

```bash
python router.py --agent telegram "Debug conversation.py"
python router.py --agent bambu "Test BambuBuddy watcher"
python router.py --agent legalkanban "Check task format parsing"
```

### List Available Agents

```bash
python router.py --list-agents
```

### Dry Run (See Which Agent Would Be Selected)

```bash
python router.py --dry-run "Task description here"
```

## Routing Logic

Agents are selected based on **keyword matching**:

| Agent | Keywords |
|-------|----------|
| telegram | telegram, bot, conversation, message, chat, jeeves |
| bambu | bambu, print, 3d, printer, filament, spool, ams |
| legalkanban | case, legalkanban, task sync, deadline, trial, client |
| briefings | brief, news, weather, reminder, health, wellness, weekly, review |
| system | cron, launchd, config, monitor, health, backup, service |

**Default:** If no keywords match, routes to **system** agent.

## Agent Invocation Flow

1. **User invokes router:**
   ```bash
   python router.py "Fix Telegram bot tool loop"
   ```

2. **Router analyzes keywords:**
   - "telegram" → scores +1 for Telegram agent
   - "bot" → scores +1 for Telegram agent
   - Result: Route to **telegram** agent

3. **Router invokes Claude with agent context:**
   ```bash
   claude -p \
     --permission-mode dontAsk \
     --disallowed-tools "Bash(git:*)" \
     "Fix Telegram bot tool loop"
   ```

   Environment variables set:
   - `ATLAS_AGENT=telegram`
   - `ATLAS_AGENT_DIR=/Users/printer/atlas/agents/telegram`

4. **Claude reads agent-specific context:**
   - `agents/telegram/goals/conversation_management.md`
   - `agents/telegram/context/tool_safeguards.md`
   - `agents/telegram/args/telegram.yaml`
   - Plus global `CLAUDE.md` and `MEMORY.md`

5. **Agent focuses on domain-specific task:**
   - No Bambu context to distract
   - No LegalKanban patterns to juggle
   - Pure focus on Telegram bot

## Benefits of This Architecture

### 1. Context Isolation
Each agent maintains **focused context**:
- Telegram Agent knows conversation patterns, not 3D printer FTP protocols
- Bambu Agent knows filament tracking, not case management task formats
- No mental overhead from unrelated domains

### 2. Error Containment
Failures are isolated:
- Telegram bot tool loop → doesn't affect Bambu tracking
- LegalKanban sync error → doesn't corrupt briefing generation
- Each agent debugs independently

### 3. Parallel Execution
Independent workflows run concurrently:
- Briefing Agent sends morning digest
- Bambu Agent polls for prints
- LegalKanban Agent syncs tasks
- All happening simultaneously, no coordination needed

### 4. Easier Debugging
When something breaks:
- Clear which agent to examine
- Logs separated by domain
- No mixed concerns in error traces

### 5. Goal Organization
Instead of flat `goals/` directory, now:
```
agents/telegram/goals/conversation_management.md
agents/bambu/goals/print_tracking.md
agents/legalkanban/goals/task_sync.md
```

**Easy to find** the relevant workflow documentation.

### 6. Specialized Knowledge
Each agent has domain-specific context:
- `agents/bambu/context/printer_specs.md` — Filament types, reply formats
- `agents/telegram/context/tool_safeguards.md` — Tool loop prevention
- `agents/legalkanban/context/task_format.md` — Task format specifications

## When NOT to Use Subagents

Keep some tasks in the **main orchestrator** (no agent):

1. **One-off scripts** — Don't need dedicated agent
2. **Cross-domain coordination** — Main orchestrator routes between agents
3. **Initial exploration** — New domains start in main, migrate to agent when stable
4. **Simple file operations** — No need for agent overhead

**Rule of thumb:** If a task touches multiple agent domains, use main orchestrator to coordinate.

## Extending the System

### Adding a New Agent

1. **Create directory structure:**
   ```bash
   mkdir -p agents/new_agent/{goals,context,args}
   ```

2. **Write agent files:**
   - `goals/workflow_name.md` — Process definitions
   - `context/domain_knowledge.md` — Specs, patterns, examples
   - `args/new_agent.yaml` — Configuration

3. **Update router.py:**
   ```python
   AGENTS = {
       # ... existing agents
       "new_agent": {
           "description": "Agent purpose",
           "keywords": ["keyword1", "keyword2"],
           "tools": ["tool_category1", "tool_category2"],
       },
   }
   ```

4. **Test routing:**
   ```bash
   python router.py --dry-run "Task with keyword1"
   ```

5. **Document in this README**

### Creating Agent-Specific Goals

Follow GOTCHA goal structure:
- **Objective** — What needs to happen
- **Agent Focus** — This agent's specialization
- **Key Tools** — Which tools it uses
- **Process** — Step-by-step workflow
- **Edge Cases** — Known failure modes
- **Success Criteria** — How to verify it works
- **Known Issues** — Current limitations
- **References** — Related docs

See existing agent goals for examples.

## Migration Status

**Completed:**
- ✅ Agent directory structure created
- ✅ Router.py implemented with keyword matching
- ✅ Telegram agent (goals, context, args)
- ✅ Bambu agent (goals, context, args)
- ✅ LegalKanban agent (goals, context, args)
- ✅ Briefings agent (goals, context, args)
- ✅ System agent (goals, context, args)
- ✅ Documentation (this README)

**Next Steps:**
- [ ] Test routing with real tasks
- [ ] Migrate existing goals to appropriate agents
- [ ] Update tool scripts to read agent-specific args
- [ ] Create agent invocation helper scripts
- [ ] Add agent health monitoring
- [ ] Build inter-agent messaging (if needed)

## Troubleshooting

**Router not finding agent:**
- Check keywords in task description
- Use `--dry-run` to see routing decision
- Add keywords to agent definition in `router.py`

**Agent not loading context:**
- Verify `ATLAS_AGENT` and `ATLAS_AGENT_DIR` env vars set
- Check agent directory structure matches expectations
- Ensure goal/context files exist

**Claude using wrong agent:**
- Use `--agent` flag to force specific agent
- Update router keywords for better matching

**Tools failing in agent context:**
- Tools are shared, not agent-specific
- Check tool requirements (credentials, paths)
- Verify args files have correct paths

## Philosophy

> **"One agent, one focus, one job done right."**

Subagents aren't about adding complexity — they're about **removing it**.

By giving each workflow its own focused agent, we reduce cognitive load, prevent errors, and make the system easier to maintain and extend.

**The router handles coordination. Each agent handles execution.**

That's the power of specialization.
