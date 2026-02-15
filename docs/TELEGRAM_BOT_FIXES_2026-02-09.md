# Telegram Bot Fixes - February 9, 2026

## Problems Identified

### 1. OpenRouter API Failures
- **User session**: Using `model_id: "openrouter"`
- **Provider**: Nvidia (via OpenRouter)
- **Errors**:
  - `Got empty response from API`
  - `Error code: 400 - Expecting ',' delimiter` (JSON parsing error)
- **Impact**: Bot unable to process requests reliably

### 2. Rotary Command Behavior
- **Issue**: `/rotary add` commands were treated as full interactive workflows
- **Expected**: Quick edits should just add content without confirmation
- **Actual**: Bot asked for full agenda creation confirmation
- **Root cause**: Directive didn't distinguish between `/rotary` and `/rotary add`

## Fixes Applied

### 1. Switched User Session to MiniMax ✅
- Changed `model_id` from `"openrouter"` to `"minimax"`
- Cleared conversation history to start fresh
- MiniMax has proven reliable (no API failures observed)

### 2. Updated Rotary Directive ✅
Updated `/rotary` command handler in [commands.py](tools/telegram/commands.py:205):

**Before:**
- All `/rotary` commands triggered full interactive workflow
- Bot would ask for confirmation even on quick edits

**After:**
- `/rotary add [content]` → Quick edit (no confirmation)
- `/rotary` or `/rotary create` → Full interactive workflow
- Better parsing of user intent

### 3. Restarted Telegram Bot ✅
- Kicked and reloaded launchd job
- New PID: 806 (was 14569)
- Changes now active

## Testing Recommendations

Try these commands in Telegram to verify:

1. **Quick add test:**
   ```
   /rotary add president announcement to 2/10 agenda - Testing quick adds
   ```
   Expected: "Added to 2/10 agenda ✓" (no confirmation prompt)

2. **Full workflow test:**
   ```
   /rotary create
   ```
   Expected: Interactive workflow with questions

3. **General query test:**
   ```
   What's on my calendar tomorrow?
   ```
   Expected: Should use Zapier calendar tool, return events

## Model Comparison

| Model | Status | Notes |
|-------|--------|-------|
| **MiniMax** | ✅ Reliable | Chosen for user session, handles tools well |
| **qwen2.5:14b** | ✅ Works | Local Ollama, slower to load (9GB) |
| **OpenRouter/Nvidia** | ❌ Unreliable | JSON parsing errors, empty responses |
| **deepseek-r1** | ❌ No tools | Doesn't support tool use |
| **llama3.2:3b** | ❌ No tools | Doesn't support tool use |

## Files Modified

1. `/Users/printer/atlas/data/sessions.json` - Switched user to MiniMax
2. `/Users/printer/atlas/tools/telegram/commands.py` - Updated rotary directive
3. Restarted: `com.atlas.telegram-bot` launchd service

## Outstanding Issues

### Browser Tool Navigation
- Bot occasionally navigates to wrong sites (e.g., WSDOT instead of YouTube)
- Browser server is working (port 19527)
- Issue appears to be model tool selection, not tool implementation
- **Recommendation**: Monitor behavior with MiniMax model

### Bambu Message Deletion
- User requested deletion of Telegram message from 1:48pm print
- Not currently possible (message IDs not stored)
- **Recommendation**: Add message_id tracking to future sends for programmatic deletion

## Next Steps

1. **Monitor**: Watch bot behavior with MiniMax over next 24 hours
2. **Test**: Try the test commands above to verify improvements
3. **Consider**: If MiniMax has issues, try qwen2.5:14b as alternative
4. **Document**: Add any new failure patterns to [TELEGRAM_BOT_SAFEGUARDS.md](TELEGRAM_BOT_SAFEGUARDS.md)

## Related Documentation

- [TELEGRAM_BOT_SAFEGUARDS.md](TELEGRAM_BOT_SAFEGUARDS.md) - Bot design principles
- [FIX_SUMMARY_2026-02-09.md](FIX_SUMMARY_2026-02-09.md) - Today's other fixes (launchd migration)
- [ENVCHAIN.md](ENVCHAIN.md) - Keychain access pattern
