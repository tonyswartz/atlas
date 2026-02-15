# Bambu Notification System - Session Summary (2026-02-09)

## What We Built Today

### 1. Bambu Telegram Group Integration ✅
- **Created**: Telegram group "Bambu" (chat ID: -5286539940)
- **Configured**: [args/bambu_group.yaml](../args/bambu_group.yaml) with group chat ID
- **Updated**: [bambu_prompt_poller.py](../tools/bambu/bambu_prompt_poller.py) to send notifications to group
- **Updated**: [bambu_reply_handler.py](../tools/bambu/bambu_reply_handler.py) to process group replies
- **Added**: Confirmation message feature after successful print logging

### 2. Telegram Bot Silence Mode ✅
- **Updated**: [bot.py](../tools/telegram/bot.py) to NOT respond to messages in Bambu group
- Bot now stays silent when you reply to Bambu print notifications
- Prevents confusing responses like "Could you clarify what '27' and '1' refer to?"

### 3. Envchain Migration (All Cron Jobs) ✅
- **Updated**: 14 cron jobs to use `envchain atlas` for Keychain access
- All jobs needing TELEGRAM_BOT_TOKEN now have envchain
- All jobs needing MINDSETLOG_DB_URL now have envchain
- See: [CRON.md](CRON.md) for complete list

### 4. Launchd Migration (Reply Handler) ✅
- **Created**: [com.atlas.bambu-reply-handler.plist](../../Library/LaunchAgents/com.atlas.bambu-reply-handler.plist)
- **Removed**: Cron job for reply handler
- **Reason**: Cron can't access macOS Keychain; launchd runs in user session

### 5. Documentation Created ✅
- [BAMBU_GROUP_SETUP.md](BAMBU_GROUP_SETUP.md) - Complete setup guide
- [BAMBU_NOTIFICATION_STATUS.md](BAMBU_NOTIFICATION_STATUS.md) - Root cause analysis
- This summary document

## What Works ✅

1. **Print Detection**: BambuBuddy watcher detects ALL prints (BambuStudio, Handy app, SD card)
2. **Notification Sending**: Prompt poller sends to Bambu group with spool options
3. **Print Logging**: Reply handler successfully logs prints to JeevesUI
4. **Bot Silence**: Bot no longer responds to Bambu replies with confused messages
5. **Group Separation**: Bambu tracking completely separate from general bot chat

## What's Not Working ❌

### Confirmation Messages
**Status**: Not sending
**Cause**: Envchain access issue in launchd context
**Evidence**: Logs show "WARNING: namespace `atlas` not defined" from envchain
**Impact**: Users don't get feedback that print was logged

**Tested Solutions**:
- ✅ Added envchain to reply handler cron job → Still failed (cron can't access Keychain)
- ✅ Migrated to launchd → Still failing (envchain warning persists)
- ❓ Next step: Investigate why envchain works for daily-brief but not reply-handler

**Current Behavior**:
1. You reply "5, 42g, Tony" in Bambu group
2. Reply handler logs print to JeevesUI ✅
3. Bot stays silent ✅
4. **Confirmation message never sent** ❌

## Test Results

### Test #1 (13:19-13:20)
- **Notification**: Sent to Bambu group ✅
- **Reply**: "27, 1, Tony"
- **Logging**: Print logged to JeevesUI ✅
- **Confirmation**: Failed (TELEGRAM_BOT_TOKEN not found) ❌
- **Bot Response**: Confused message about case IDs ❌ (FIXED AFTER)

### Test #2 (13:25-13:27)
- **Notification**: Sent to Bambu group ✅
- **Reply**: "5, 1, Tony"
- **Logging**: Print logged to JeevesUI ✅
- **Confirmation**: Failed (envchain namespace warning) ❌
- **Bot Response**: SILENT ✅ (fix working!)

## File Changes Summary

**Modified Files**:
- tools/bambu/bambu_prompt_poller.py
- tools/bambu/bambu_reply_handler.py
- tools/telegram/bot.py
- All cron jobs (via crontab)

**Created Files**:
- args/bambu_group.yaml
- docs/BAMBU_GROUP_SETUP.md
- docs/BAMBU_NOTIFICATION_STATUS.md
- docs/BAMBU_SESSION_SUMMARY_2026-02-09.md
- ~/Library/LaunchAgents/com.atlas.bambu-reply-handler.plist
- /tmp/get_group_id.py

**Data Files**:
- data/telegram_groups.json (auto-created by bot)
- memory/bambu-last-options.json (created by prompt poller)

## Next Steps to Fix Confirmations

### Option A: Use Different Auth Method
Instead of envchain, store token in launchd plist EnvironmentVariables:
```xml
<key>EnvironmentVariables</key>
<dict>
    <key>TELEGRAM_BOT_TOKEN</key>
    <string>8339414604:AAHH7VUG0BkjnQsR84wmAtJ6LV6VAEvGTZ0</string>
</dict>
```
**Pros**: Guaranteed to work
**Cons**: Token in plain text in plist file

### Option B: Debug Envchain Launchd Issue
Compare daily-brief (working) vs reply-handler (not working):
- Check if timing matters (daily-brief runs once/day, reply-handler runs every minute)
- Check if there's a race condition with Keychain access
- Review macOS Keychain access logs

### Option C: Use Telegram Bot for Confirmations
Instead of reply-handler sending confirmations, have the Telegram bot send them:
- Bot detects successful log in JeevesUI
- Bot sends confirmation message
**Pros**: Bot already has token access
**Cons**: More complex architecture

## Recommended Immediate Fix

**Use Option A** (environment variable in plist) to get confirmations working NOW, then investigate Option B later as an improvement.

Update `com.atlas.bambu-reply-handler.plist`:
```xml
<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>TELEGRAM_BOT_TOKEN</key>
    <string>8339414604:AAHH7VUG0BkjnQsR84wmAtJ6LV6VAEvGTZ0</string>
</dict>
```

Then:
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.bambu-reply-handler.plist
launchctl load ~/Library/LaunchAgents/com.atlas.bambu-reply-handler.plist
```

## Current System State

**Cron Jobs** (17 total):
- All using envchain where needed ✅
- Reply handler REMOVED (migrated to launchd) ✅

**Launchd Agents** (6 total):
- com.atlas.daily-brief ✅ (working with envchain)
- com.atlas.watchdog ✅ (working with envchain)
- com.atlas.legalkanban-sync ✅ (working with envchain)
- com.atlas.telegram-bot ✅ (working with run_with_envchain.sh)
- com.atlas.browser-server ✅
- com.atlas.bambu-reply-handler ⚠️ (running but confirmations failing)

**Bambu Workflow**:
```
Print completes
    ↓
BambuBuddy watcher (every 5 min via cron)
    ↓
Pending prompts file
    ↓
Prompt poller (every 5 min via cron) → Bambu GROUP
    ↓
User replies in group
    ↓
Bot STAYS SILENT ✅
    ↓
Reply handler (every 60 sec via launchd)
    ↓
JeevesUI logging ✅ + Confirmation ❌
```

## Key Learnings

1. **macOS Keychain + Automation**:
   - Cron CANNOT access Keychain (even with envchain)
   - Launchd CAN access Keychain (runs in user session)
   - But envchain in launchd is inconsistent (works for daily-brief, not reply-handler)

2. **Telegram Group Management**:
   - Bot auto-registers groups in `data/telegram_groups.json`
   - Group chat IDs are negative numbers
   - Bot can selectively ignore groups by chat ID

3. **Bambu Print Tracking**:
   - BambuBuddy SQLite is more reliable than FTP watching
   - Catches ALL prints regardless of source
   - Multi-color print support works well

## Files to Update in Memory

Add to `~/.claude/projects/-Users-printer-atlas/memory/MEMORY.md`:

```markdown
## Bambu Group Integration (2026-02-09)
- **Bambu group**: Chat ID -5286539940, bot stays silent on messages
- **Notifications**: Send to group via bambu_prompt_poller.py (reads args/bambu_group.yaml)
- **Reply handler**: Launchd agent (com.atlas.bambu-reply-handler), runs every 60s
- **Issue**: Confirmations failing due to envchain access in launchd
- **Workaround**: Add TELEGRAM_BOT_TOKEN to plist EnvironmentVariables
- **Bot silence**: tools/telegram/bot.py lines 91-93 check for Bambu group chat ID

## Envchain Launchd Issue (2026-02-09)
- **Problem**: envchain works in daily-brief launchd but not bambu-reply-handler
- **Symptom**: "WARNING: namespace `atlas` not defined" from envchain
- **Impact**: Can't send Telegram confirmations
- **Workaround**: Use plist EnvironmentVariables instead of envchain
- **TODO**: Investigate why inconsistent between different launchd agents
```
