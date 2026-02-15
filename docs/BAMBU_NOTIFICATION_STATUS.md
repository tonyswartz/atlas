# Bambu Notification System Status (2026-02-09)

## What Happened
- Print completed at 12:19 (first print)
- Second print completed at 12:20
- NO notifications sent until 13:07 (manual trigger)

## Root Cause Analysis

### Primary Issue: JeevesUI Timeouts
- bambu_prompt_poller.py requires JeevesUI spools endpoint to send notifications
- Around 12:45-13:00, JeevesUI was timing out (8s timeout insufficient)
- Poller logged: "Failed to fetch spools from JeevesUI: timed out" → "No spools from JeevesUI; cannot send prompt"
- **Resolution**: Increased timeout from 8s to 20s

### Secondary Issue: Telegram Bot Reply Handling
**Problem**: When user replies "Tony" to Bambu prompt, the Telegram bot treats it as a general chat message instead of recognizing it as a Bambu reply.

**Expected Flow**:
1. Bambu watcher detects print → writes to pending-prompts.md
2. Prompt poller sends Telegram notification → writes bambu-last-options.json
3. User replies "Tony" or "2, 36.34g, Tony"
4. Reply handler reads last_incoming_message.txt → logs to JeevesUI
5. **Telegram bot should NOT respond** (or send brief confirmation)

**Actual Flow**:
- Steps 1-4 work correctly ✓
- Step 5: Telegram bot responds with context-inappropriate message (treating "Tony" as a general chat)

**The Issue**:
- Reply handler successfully logged the print (verified in JeevesUI)
- But Telegram bot doesn't know to stay silent or send appropriate confirmation
- Bot response: "Tony, here. DUI attorney in Ellensburg, got it." (wrong context!)

## Current Status

### ✅ Working
1. **Bambu watcher**: Detecting prints from BambuBuddy database
2. **Prompt poller**: Sending notifications (when JeevesUI responsive)
3. **Reply handler**: Successfully logging prints to JeevesUI
4. **Cron jobs**: All now using envchain for credentials

### ❌ Broken
1. **Telegram bot reply detection**: Not recognizing Bambu replies vs general chat
2. **Missing bambu-last-options.json**: File doesn't persist after prompt sent
3. **No confirmation message**: User doesn't get feedback that print was logged

## Missing File Investigation

**bambu-last-options.json** should be written by prompt poller after sending notification (line 482 of bambu_prompt_poller.py), but file doesn't exist.

**Possible causes**:
- File is being deleted by another process
- Prompt poller's write operation is failing silently
- Permissions issue

**Need to add**: Logging to confirm file write succeeded

## Fixes Needed

### 1. Telegram Bot Bambu Reply Detection
**Options**:
- A) Add "Reply-To" tracking: Bot checks if incoming message is reply to a Bambu notification
- B) Add state machine: Track that we're waiting for Bambu reply
- C) Create separate Telegram group for Bambu prints (user suggested this)
- D) Add command prefix: User replies "/print Tony" instead of just "Tony"

**Recommended**: Option C (separate group) + state tracking for cleaner separation

### 2. Persist bambu-last-options.json
- Add error handling + logging around file write
- Verify file permissions
- Add atomic write (write to temp, then rename)

### 3. Send Confirmation Message
Options:
- A) Reply handler sends confirmation via Telegram API
- B) Telegram bot detects successful log and confirms
- C) Prompt poller re-checks if reply was processed and sends confirmation

**Recommended**: Option A (reply handler sends confirmation)

## Cron/Launchd Envchain Audit - COMPLETED ✓

All jobs now use envchain where needed:
- 9 jobs needed TELEGRAM_BOT_TOKEN → added envchain
- 4 jobs needed MINDSETLOG_DB_URL → added envchain
- 1 job needs multiple credentials → added envchain
- 5 jobs need no credentials → left as-is
- All 5 launchd agents already had envchain

## Manual Logging Required

**First print** needs manual logging:
- Print: "0.24mm layer, 2 walls, 15% infill" at 26-02-09 12:19
- User: Jacob
- Filament: Bambu Lab PLA Red Silk (ID: cmlfmwhnn0002pqbolee2jz9x)
- Grams used: TBD (BambuBuddy has no filament data for this print)

## Next Steps

1. Ask user: Create separate Telegram group for Bambu prints?
2. Fix Telegram bot to detect Bambu replies
3. Add confirmation messages after successful logging
4. Investigate bambu-last-options.json persistence
5. Get grams used for first print and log manually
