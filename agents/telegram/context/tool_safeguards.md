# Telegram Bot Tool Safeguards

## Critical Rules for Tool Design

### 1. Clear Purpose
Every tool must have a **single, specific purpose**. Avoid tools that:
- "Provide context-aware suggestions" (too vague)
- "Log corrections" (meta operation, not concrete action)
- "Proactive intelligence" (undefined scope)

**Good examples:**
- `journal_read_recent` — Read last N journal entries
- `reminder_add` — Add reminder with task and schedule
- `kanban_read` — Read Tony Tasks.md or LegalKanban

### 2. Required Parameters
Tools must have **required parameters** that force specificity:
- `journal_read_recent(days: int)` — REQUIRED
- `reminder_add(task: str, schedule: str)` — REQUIRED
- `memory_search(query: str)` — REQUIRED

Avoid optional-only params that let the LLM call with no real input.

### 3. Concrete Outputs
Tools return **specific, actionable data**, not open-ended context:
- ✅ "3 reminders found: [list]"
- ✅ "Journal entries for last 7 days: [entries]"
- ❌ "Here are some suggestions that might be relevant"
- ❌ "I've logged that correction"

### 4. No Meta Operations
Don't add tools that:
- Track what other tools did
- "Learn" from tool results
- Generate abstract suggestions
- Log arbitrary metadata

The LLM will call these endlessly because there's no termination condition.

### 5. Hard Limits
Enforce in conversation.py:
- Max 3 calls per tool per turn
- Max 10 tool rounds total
- Force text response every 4 tool rounds

### 6. Model Requirements
Not all Ollama models support tools:
- ✅ qwen2.5:14b, qwen2.5:7b
- ✅ llama3.1:8b, llama3.1:70b
- ✅ mistral:7b
- ❌ deepseek-r1 (no tool support)
- ❌ llama3.2:3b (no tool support)

## Tool Loop Symptoms
1. Same tool called repeatedly with slight variations
2. Hits 10-round limit before responding
3. Hallucinated parameters (making up data to pass validation)
4. Tool returns empty/null but keeps calling

## Recovery Process
1. Clear stuck session: edit `data/sessions.json`
2. Remove problematic tool from `tool_definitions.py` and `tool_runner.py`
3. Restart bot
4. Test with manual messages

## Prevention Checklist
Before adding a new tool:
- [ ] Does it have a single, specific purpose?
- [ ] Does it require concrete input parameters?
- [ ] Does it return specific, bounded output?
- [ ] Is it NOT a meta-operation?
- [ ] Can you write a test case with clear success criteria?

If any answer is NO, don't add the tool.
