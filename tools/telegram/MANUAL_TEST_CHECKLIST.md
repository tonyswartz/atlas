# Telegram Bot Manual Test Checklist

## Why Manual Testing?

The automated test approach using `sendMessage` doesn't work because:
- `sendMessage` makes the **bot send messages**, not receive them
- The bot only responds to messages it receives via `getUpdates` (from users in the Telegram app)
- The bot cannot respond to its own messages

**Verified Working:**
- ✅ Direct bot test passed (session persistence works)
- ✅ Bot responds to real Telegram messages (confirmed in logs)
- ✅ Sessions are saved correctly
- ✅ MiniMax integration working
- ✅ Tool loop prevention active
- ✅ Timeout handling configured

## Test Categories

### 1. Simple Interactions

Test that basic queries work without deflection or errors.

- [ ] Send: "Hi" → Expect: Friendly greeting (not deflection)
- [ ] Send: "How are you?" → Expect: Brief response
- [ ] Send: "What's 2+2?" → Expect: "4" or simple calculation

### 2. Memory Queries

Test that the bot uses stored memory instead of asking for clarification.

- [ ] Send: "What do you know about me?" → Expect: Concrete facts from memory (not "could you specify")
- [ ] Send: "What are my preferences?" → Expect: List of preferences from MEMORY.md
- [ ] Send: "What have I told you recently?" → Expect: Recent log entries

### 3. Context Questions

Test that the bot uses available context (memory, journal, reminders) to answer.

- [ ] Send: "What should I focus on this week?" → Expect: Answer based on USER.md, journal, reminders (not deflection)
- [ ] Send: "What's on my plate?" → Expect: Tasks/priorities from available context
- [ ] Send: "What am I working on?" → Expect: Current projects/case info from memory

### 4. Reminders

Test reminder functionality.

- [ ] Send: "What reminders do I have?" → Expect: List from Tony Reminders.md
- [ ] Send: "Remind me to test the bot tomorrow" → Expect: Confirmation, check if added to reminders
- [ ] Send: "Remind me to buy milk" → Expect: Saved to "Today" section

### 5. Tool Usage

Test that tools are called correctly without loops.

- [ ] Send: "What's my next to-do?" → Expect: Uses journal/reminders/memory (not kanban_read)
- [ ] Send: "Read my journal from yesterday" → Expect: Calls journal_read_recent
- [ ] Send: "What's the weather?" → Expect: Calls weather tool or reports unavailable

### 6. No Tool Loops

Verify loop prevention safeguards work.

- [ ] Monitor bot logs while testing → Expect: No tool called more than 3 times per message
- [ ] Send complex query → Expect: Text response within 4 tool rounds (forced text safeguard)
- [ ] Check logs for "Loop detected" warnings → Expect: None (unless genuinely stuck)

### 7. Response Quality

Test that responses are concise and don't include unwanted artifacts.

- [ ] All responses → Expect: No `<think>` tags visible
- [ ] All responses → Expect: Markdown formatted (bold, lists work)
- [ ] All responses → Expect: Short, direct answers (not verbose)

### 8. Error Handling

Test graceful degradation.

- [ ] Send: "Search the web for recent news" → Expect: Either search results OR "web search unavailable" message
- [ ] Send request for missing tool → Expect: Clear error message (not crash)

### 9. Session Persistence

Test that conversation history is maintained.

- [ ] Send 3-4 messages in sequence
- [ ] Check `data/sessions.json` → Expect: Messages saved with role/content
- [ ] Restart bot (see below)
- [ ] Send: "What did we just talk about?" → Expect: References previous messages

### 10. Model Switching

Test switching between Ollama and MiniMax.

- [ ] Send: "/models" → Expect: List of available models
- [ ] Send: "/models minimax" → Expect: Confirmation of switch
- [ ] Send a test query → Expect: Response from MiniMax (check logs)
- [ ] Send: "/models ollama" → Expect: Switch back confirmation

## How to Restart the Bot

If you need to restart the bot for testing:

```bash
# Stop the bot
launchctl stop com.atlas.telegram-bot

# Start the bot
launchctl start com.atlas.telegram-bot

# Check if it's running
launchctl list | grep telegram-bot

# View logs
tail -f ~/Library/Logs/telegram-bot.err.log
```

## Monitoring During Tests

Watch the bot logs in real-time:

```bash
tail -f ~/Library/Logs/telegram-bot.err.log
```

Look for:
- `[INFO] Message from user ...` → Bot received your message
- `[INFO] Tool call round N: tool_name(...)` → Bot calling tools
- `[WARNING] Loop detected` → Loop prevention triggered
- `[WARNING] Forcing text response` → Forced text safeguard triggered
- `HTTP Request: POST https://api.telegram.org/.../sendMessage` → Bot sent response

## Expected Behavior

**✅ Good Signs:**
- Responses arrive within 5-30 seconds (depending on model/tools)
- No deflection phrases ("could you specify", "to better understand")
- Tool calls are purposeful (memory_read for "what do you know", etc.)
- Sessions.json updates after each message
- No crashes or timeout errors

**❌ Warning Signs:**
- Bot asks for clarification on straightforward questions
- Same tool called 3+ times in one message
- Responses take longer than 60 seconds
- `<think>` tags visible in responses
- "kanban_read" or "kanban_write" tool calls (these don't exist)
- Bot crashes or stops responding

## Test Results

Record results here:

| Test Category | Status | Notes |
|--------------|--------|-------|
| Simple Interactions | ⬜ |  |
| Memory Queries | ⬜ |  |
| Context Questions | ⬜ |  |
| Reminders | ⬜ |  |
| Tool Usage | ⬜ |  |
| No Tool Loops | ⬜ |  |
| Response Quality | ⬜ |  |
| Error Handling | ⬜ |  |
| Session Persistence | ⬜ |  |
| Model Switching | ⬜ |  |

**Overall Status:** ⬜ All tests passed | ⬜ Some issues found

## Issues Found

Document any issues here with:
1. Test message sent
2. Expected behavior
3. Actual behavior
4. Relevant log lines
