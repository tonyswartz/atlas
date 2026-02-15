# Bambu Telegram Group Setup Guide

## What Changed

Your Bambu print tracking system now supports using a dedicated Telegram **group** instead of your 1-on-1 chat with JeevesAtlas. This means:

✅ Clean separation between Bambu tracking and general bot conversations
✅ Multiple people (you, Jacob) can track prints
✅ Bot automatically sends confirmation after logging prints
✅ No more confusion about whether "Tony" is a reply or general message

## Setup Instructions

### Step 1: Create Telegram Group

1. Open Telegram
2. Create a new group:
   - Tap the ✏️ pencil icon
   - Select "New Group"
   - Name it "Bambu Print Tracking" (or whatever you prefer)
   - Add yourself as the first member

### Step 2: Add the Bot

1. In the group, tap the group name at the top
2. Tap "Add Members"
3. Search for and add: **JeevesAtlas** (your bot's username)
4. The bot should now appear in the member list

### Step 3: Get the Group Chat ID

Send a test message in the group (like "test"), then run:

```bash
cd /Users/printer/atlas
envchain atlas python3 /tmp/get_group_id.py
```

This will show all recent chats. Look for your group - it will be type `group` and have a **negative number** as the chat ID (like `-1001234567890`).

### Step 4: Configure the System

Edit the config file:

```bash
code args/bambu_group.yaml
```

Or manually edit and update these fields:

```yaml
enabled: true
chat_id: "-1001234567890"  # Replace with your actual group chat ID (from Step 3)
```

Save the file.

### Step 5: Test It

Trigger a test notification manually:

```bash
cd /Users/printer/atlas
envchain atlas python3 tools/bambu/bambu_prompt_poller.py
```

If there's a pending print, you should see the notification in the **group** instead of your 1-on-1 chat.

### Step 6: Reply to Test

In the group, reply with the format:
```
2, 36g, Tony
```

or just:
```
Tony
```

The bot should respond with a confirmation like:
```
✅ Logged: filename.gcode
Sunlu Black 36g
User: Tony
```

## Troubleshooting

### "No recent chats" when getting group ID
- Make sure you sent a message in the group **after** adding the bot
- Wait a few seconds and try again

### Notifications still going to 1-on-1 chat
- Check that `enabled: true` in `args/bambu_group.yaml`
- Check that `chat_id` is set to the correct negative number
- Make sure you saved the file

### Bot not responding in group
- Check that the bot has permission to read messages in the group
- In group settings → Permissions, ensure members can send messages

### Confirmation messages not appearing
- Check that `send_confirmation: true` in `args/bambu_group.yaml`
- Check `/Users/printer/atlas/logs/bambu-reply-handler.log` for errors

## Reverting to 1-on-1 Chat

If you want to go back to using your 1-on-1 chat with the bot:

```yaml
enabled: false
```

The system will automatically use `fallback_chat_id` (your individual chat).

## Files Modified

The following files were updated to support group chat:

1. **args/bambu_group.yaml** - Configuration file (NEW)
2. **tools/bambu/bambu_prompt_poller.py** - Sends to group if enabled
3. **tools/bambu/bambu_reply_handler.py** - Monitors group and sends confirmations

## How It Works

### Before (1-on-1 Chat):
1. Bambu watcher detects print
2. Prompt poller sends notification to YOU
3. You reply "Tony"
4. Bot responds with unrelated message (confused about context)
5. Reply handler logs print (but bot doesn't confirm)

### After (Group Chat):
1. Bambu watcher detects print
2. Prompt poller sends notification to GROUP
3. You reply "Tony" in group
4. Reply handler logs print
5. **Bot sends confirmation**: "✅ Logged: filename, 36g, Tony"

## Customization

You can customize the messages in `args/bambu_group.yaml`:

```yaml
confirmations:
  success: "✅ Print logged!\n{spools}\n{user}"
  error: "❌ Failed to log. Check logs."
```

Available placeholders:
- `{filename}` - Print filename
- `{spools}` - Spool summary (e.g., "Sunlu Black 36g")
- `{user}` - User name (Tony or Jacob)
- `{timestamp}` - When the print completed
