# Telegram Bot Safeguards

## Tool Loop Prevention (2026-02-08)

### Problem
Bot hit 10-round tool loop limit by repeatedly calling tools without providing text responses. Specific issue: calling `log_correction` with hallucinated data.

### Root Causes
1. **Low-value tools with no side effects** - Tools that don't change state (like `proactive_intelligence`) encourage the bot to call them repeatedly "just in case"
2. **Vague tool descriptions** - Tools with descriptions like "Use when you want to anticipate user needs" are too broad
3. **No loop detection** - The bot doesn't detect when it's calling the same tool repeatedly with the same/similar args

### Solutions Implemented

#### 1. Removed Problematic Tools
- ❌ **Removed `proactive_intelligence`** - Always returned same mock suggestion, encouraged loops
- ❌ **Removed `log_correction`** - Bot hallucinated corrections that never happened

#### 2. Hardened Loop Detection (conversation.py)
```python
MAX_CALLS_PER_TOOL = 3  # No tool can be called more than 3 times
REQUIRE_TEXT_EVERY = 4  # Must provide text response every 4 rounds

# Track tool usage
tool_call_counts = {}
for tc in tool_calls:
    tool_call_counts[tc.function.name] = tool_call_counts.get(tc.function.name, 0) + 1
    if tool_call_counts[tc.function.name] > MAX_CALLS_PER_TOOL:
        return "I seem to be stuck in a loop calling the same tools repeatedly..."
```

✅ **Active Safeguards:**
- ✅ Max 3 calls per tool per conversation
- ✅ Forced text response every 4 rounds (prevents silent tool chains)
- ✅ Clear error message when loop detected
- ✅ Session saved before returning error (no data loss)

#### 3. Tool Design Guidelines
Tools should:
- ✅ Have **clear, narrow purposes** ("Get calendar events for today" not "Anticipate user needs")
- ✅ Produce **observable side effects** or **return concrete data** (file contents, API responses)
- ✅ Require **specific parameters** that force the bot to reason about what it's calling
- ❌ **NOT** be "meta" tools about the bot's own behavior (learning, correction logging, etc.)

#### 3. Future Safeguards to Add

**Option A: Loop Detection in Conversation Handler**
```python
# Track tool calls in current round
tool_call_history = []

for tool_call in tool_calls:
    # Detect if same tool called 3+ times in this conversation
    if tool_call_history.count(tool_call.function.name) >= 2:
        logger.warning(f"Loop detected: {tool_call.function.name} called 3+ times")
        return "I seem to be stuck in a loop. Could you rephrase your request?"
```

**Option B: Require Text Response Every N Rounds**
```python
# conversation.py line 639
MAX_TOOL_ROUNDS = 10
REQUIRE_TEXT_EVERY = 3  # Must provide text response every 3 rounds

for _round in range(MAX_TOOL_ROUNDS):
    # ... existing code ...

    if _round > 0 and _round % REQUIRE_TEXT_EVERY == 0 and not message.content:
        # Force a text response by not allowing tool calls
        logger.warning(f"Forcing text response at round {_round}")
        # Re-prompt with "Please provide a text response"
        api_messages.append({
            "role": "system",
            "content": "You must provide a text response now before making more tool calls."
        })
        continue
```

**Option C: Tool Call Limits Per Tool**
```python
# Track calls per tool
tool_counts = {}
MAX_CALLS_PER_TOOL = 3

for tool_call in tool_calls:
    tool_counts[tool_call.function.name] = tool_counts.get(tool_call.function.name, 0) + 1
    if tool_counts[tool_call.function.name] > MAX_CALLS_PER_TOOL:
        logger.warning(f"Tool {tool_call.function.name} called {MAX_CALLS_PER_TOOL}+ times")
        return f"I've called {tool_call.function.name} too many times. Let me try a different approach."
```

### Warning Signs of Bad Tools

A tool is problematic if:
1. It returns the same result every time (or mostly the same)
2. Its description uses words like "proactive", "anticipate", "learn", "improve"
3. It doesn't take required parameters
4. You see it called multiple times in a row in sessions.json

### How to Audit Tools

```bash
# Check for repeated tool calls in session history
jq '.[] | .messages[] | select(.tool_calls) | .tool_calls[].function.name' data/sessions.json | sort | uniq -c | sort -rn

# Find tools with no required parameters (often problematic)
grep -A 20 '"required": \[\]' tools/telegram/tool_definitions.py
```

### Emergency Response

If the bot gets stuck again:

```bash
# 1. Clear the stuck session
python3 -c "
import json
from pathlib import Path
sessions = json.loads(Path('data/sessions.json').read_text())
sessions['8241581699'] = {'messages': [], 'model_id': 'ollama'}
Path('data/sessions.json').write_text(json.dumps(sessions))
"

# 2. Identify the problematic tool from logs
tail -100 logs/bot.log | grep "Tool call"

# 3. Comment out the tool in tool_definitions.py and tool_runner.py
```

### Memory Update
Added to MEMORY.md:
- ✅ Tool loop fix (2026-02-08): Removed `proactive_intelligence` and `log_correction`
- ✅ Guideline: Tools must have clear purposes, concrete outputs, required params
- ✅ Warning: Avoid "meta" tools that reason about the bot's behavior
