# System Fix Summary - February 9, 2026

## Problems Identified

### 1. Research Brief (3pm) - NOT SENT ❌
- **Root cause**: Running from cron, envchain namespace inaccessible from cron
- **Error**: `WARNING: namespace 'atlas' not defined` → No Telegram token → messages not sent
- **Impact**: User missed daily research brief at 3pm

### 2. Bambu Print Notifications - NOT SENT ❌
- **Root cause**: Prompt poller running from cron, envchain namespace inaccessible
- **Error**: `TELEGRAM_BOT_TOKEN not found in .env`
- **Impact**: Prints completed at 1:48pm and 1:50pm but no Telegram notifications sent
- **State**: Pending prompts sat in queue from 1:50pm to 4:55pm (3+ hours)

### 3. Bambu Reply Handler - INCONSISTENT CONFIGURATION ⚠️
- **Issue**: Launchd plist had token hardcoded instead of using envchain
- **Impact**: Inconsistent with other Atlas services, potential security issue

### 4. Telegram Bot Behavior - POOR TOOL CHOICES ⚠️
- **Issue**: Bot making suboptimal tool choices (browser tool navigating to wrong sites)
- **Examples**:
  - User asked for YouTube stats for "TonySwartz1" → Bot navigated to WSDOT website
  - Bot asked for full URL instead of inferring youtube.com/@TonySwartz1
- **Impact**: Frustrating user experience, "Got empty response from API" errors

## Fixes Applied

### 1. Migrated Research Brief to Launchd ✅
- Created `/Users/printer/Library/LaunchAgents/com.atlas.research-brief.plist`
- Configured to run at 3pm daily via `StartCalendarInterval`
- Uses `envchain atlas` to access Telegram token from Keychain
- Removed duplicate cron entry

### 2. Migrated Bambu Prompt Poller to Launchd ✅
- Created `/Users/printer/Library/LaunchAgents/com.atlas.bambu-prompt-poller.plist`
- Configured to run every 5 minutes (300 seconds)
- Uses `envchain atlas` to access Telegram token from Keychain
- Removed duplicate cron entry
- **Result**: Pending prompts successfully sent at 4:55pm (log shows both prints sent to group chat -5286539940)

### 3. Fixed Bambu Reply Handler Configuration ✅
- Updated `/Users/printer/Library/LaunchAgents/com.atlas.bambu-reply-handler.plist`
- Removed hardcoded TELEGRAM_BOT_TOKEN from EnvironmentVariables
- Now uses `envchain atlas` like all other Atlas services
- Reloaded launchd job

### 4. Updated Crontab ✅
- Backed up crontab to `/tmp/crontab_backup.txt`
- Removed entries for `research_brief.py` and `bambu_prompt_poller.py`
- These jobs now exclusively run via launchd

## Current Status

### Launchd Jobs (All Atlas Services)
```
com.atlas.bambu-prompt-poller    ✅ Running (PID 27906)
com.atlas.daily-brief            ✅ Loaded (interval-based)
com.atlas.telegram-bot           ✅ Running (PID 14569)
com.atlas.watchdog               ✅ Loaded (interval-based)
com.atlas.bambu-reply-handler    ✅ Loaded (interval-based)
com.atlas.legalkanban-sync       ✅ Loaded (hourly)
com.atlas.research-brief         ✅ Loaded (daily 3pm)
com.atlas.browser-server         ✅ Running (PID 8162, port 19527)
```

### Verification
- ✅ Bambu pending prompts file is now empty (all pending items processed)
- ✅ Research brief will run tomorrow at 3pm with working Telegram token
- ✅ All Atlas jobs now consistently use `envchain atlas` pattern
- ⚠️ Telegram bot tool selection needs improvement (not fixed in this session)

## Key Lessons Reinforced

1. **macOS Keychain + cron = BROKEN** (documented 2026-02-08, re-confirmed today)
   - Cron cannot access Keychain → envchain fails → tokens unavailable
   - Solution: ALWAYS use launchd for jobs needing OAuth/Keychain access
   - Launchd runs in user session → full Keychain access

2. **Consistency is Critical**
   - All Atlas services should use the same credential access pattern
   - Hardcoded tokens in plist files are a security risk and maintenance burden
   - The `envchain atlas` pattern is now standard across all services

3. **Monitoring Gaps**
   - Watchdog should have detected these failures earlier
   - TODO: Enhance watchdog to detect when expected Telegram messages aren't sent

## Updated Memory

Added to `/Users/printer/.claude/projects/-Users-printer-atlas/memory/MEMORY.md`:

```markdown
## Launchd Migration (2026-02-09)
- **Problem**: Cron jobs couldn't access envchain → services failing silently
- **Solution**: Migrated research_brief and bambu_prompt_poller from cron to launchd
- **Pattern**: ALL Atlas services now use launchd + `envchain atlas` (no exceptions)
- **Services**: daily-brief, watchdog, research-brief, bambu-prompt-poller, bambu-reply-handler, legalkanban-sync, telegram-bot, browser-server
- **RULE**: Never use cron for jobs needing Keychain/OAuth. Always use launchd.
```

## Files Modified

1. `/Users/printer/Library/LaunchAgents/com.atlas.research-brief.plist` (created)
2. `/Users/printer/Library/LaunchAgents/com.atlas.bambu-prompt-poller.plist` (created)
3. `/Users/printer/Library/LaunchAgents/com.atlas.bambu-reply-handler.plist` (edited)
4. User crontab (removed 2 entries)

## Testing Performed

1. ✅ Loaded all new launchd jobs
2. ✅ Verified jobs appear in `launchctl list`
3. ✅ Manually triggered prompt poller → pending prompts sent successfully
4. ✅ Verified browser server running on port 19527
5. ✅ Confirmed envchain namespace accessible from launchd context

## Outstanding Issues

### Telegram Bot Tool Selection
- Bot occasionally makes poor tool choices
- Example: YouTube username → should infer URL, not ask repeatedly
- Browser tool works but model doesn't always use it correctly
- Sessions.json shows user's session using "openrouter" model_id
- Consider: Better tool descriptions, prompt engineering, or model selection

### Recommended Next Steps
1. Review tool descriptions in `tool_definitions.py` for clarity
2. Add example usage to complex tools (browser, zapier_run)
3. Consider system prompt updates for better tool selection
4. Test bot behavior with different models (minimax vs openrouter vs qwen)
