# Goal: Telegram Conversation Management

## Objective
Manage Telegram bot conversations with context retention, tool routing, and intelligent responses.

## Agent Focus
The **Telegram Agent** specializes in:
- Conversation state management
- Tool routing and execution
- Session persistence
- Error handling in tool loops
- User preference learning

## Key Tools
- `tools/telegram/bot.py` — Entry point, message routing
- `tools/telegram/conversation.py` — Claude tool_use loop
- `tools/telegram/tool_runner.py` — Execute memory/journal/reminder/kanban tools
- `tools/telegram/tool_definitions.py` — Anthropic tool schemas
- `tools/telegram/config.py` — Load args/telegram.yaml

## Process

### 1. Receive Message
- Bot polls Telegram API
- Validates user against allowlist
- Loads user session from `data/sessions.json`
- Checks for slash commands (routes to `commands.py` if match)

### 2. Load Context
- Read MEMORY.md for persistent facts
- Load user's conversation history
- Apply persona from args/telegram.yaml

### 3. Tool Loop Management
**Critical: Prevent tool loops**
- Max 3 calls per tool per conversation turn
- Force text response every 4 tool rounds
- Only use tools with clear purposes and required params
- Never add "meta" tools (proactive_intelligence, log_correction)

### 4. Tool Execution
- Parse tool requests from Claude
- Route to appropriate tool script via subprocess
- Handle timeouts (Ollama: 120s, Telegram API: 30s)
- Return results to conversation context

### 5. Response Generation
- Use MiniMax (reliable) or Ollama qwen2.5:14b
- Strip `<think>...</think>` tags from MiniMax responses
- Convert system role → user role for MiniMax compatibility
- Keep responses concise per hardprompts/telegram_system_prompt.md

### 6. Session Persistence
- Save conversation history to `data/sessions.json`
- Track tool calls for debugging
- Store model preferences per user

## Edge Cases

### Tool Loop Prevention
If bot enters infinite tool loop:
1. Check `data/sessions.json` — clear stuck session
2. Review tool_definitions.py — ensure clear purposes
3. Check conversation.py safeguards:
   - Max 3 calls per tool enforced
   - Text response forced every 4 rounds
4. Never re-add removed problematic tools

### Timeout Handling
- Ollama qwen2.5:14b takes time to load → 120s timeout
- Telegram API can be slow → 30s send timeout
- Fallback to MiniMax if Ollama consistently times out

### MiniMax Compatibility
- No "system" role support → convert to "user" role
- Includes `<think>...</think>` → strip via `_strip_think()`
- Works reliably, use as fallback

## Testing
**Manual testing only** — automated tests don't work (bot can't reply to itself)
- Send test messages in Telegram
- Verify tool calls via logs
- Check session persistence
- See `tools/telegram/MANUAL_TEST_CHECKLIST.md`

## Success Criteria
- User messages processed within 5 seconds (text) / 120 seconds (tools)
- No tool loops (max 3 calls per tool enforced)
- Sessions persist across restarts
- Errors logged but don't crash bot

## Known Issues
- memory_search ValueError in hybrid_search.py:166 (BM25 score comparison)
- kanban_read occasionally called when not needed
- qwen2.5:14b slower than MiniMax

## References
- `hardprompts/telegram_system_prompt.md` — Bot personality and voice
- `docs/TELEGRAM_BOT_SAFEGUARDS.md` — Full safeguard documentation
- `args/telegram.yaml` — Bot configuration
