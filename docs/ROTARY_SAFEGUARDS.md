# Rotary Agenda Safeguards

**Implemented:** 2026-02-11
**Problem solved:** Bot overwrote entire agenda with partial content

---

## The Problem

When asked to "add to the rotary agenda", the Telegram bot called `rotary_save_agenda` with only the new content instead of:
1. Reading the existing agenda
2. Modifying it
3. Saving the complete updated content

This resulted in the entire agenda being replaced with just a few bullet points.

---

## Multi-Layer Safeguard System

### 1. Content Validation (Primary Defense)

**Location:** [tool_runner.py:623-680](../tools/telegram/tool_runner.py#L623-L680)

**How it works:**
- Before saving, checks if an agenda already exists
- Compares new content length vs existing content length
- **Blocks save** if new content is:
  - Less than 500 characters AND
  - Less than 50% of the original length

**Error message returned:**
```
Content too short (234 chars). Existing agenda is 712 chars.
Use rotary_read_agenda first to get the full content,
then modify and save the complete agenda.
```

This forces the bot to follow the correct workflow.

### 2. Automatic Backups (Recovery Mechanism)

**Backup location:** `Rotary/Meetings/backups/`

**How it works:**
- Before overwriting any existing agenda, creates a timestamped backup
- Format: `2026-02-10_backup_20260211_091500.md`
- All backups preserved indefinitely
- No user action required - fully automatic

**Example backup:**
```
Rotary/Meetings/backups/2026-02-10_backup_20260211_091500.md
```

### 3. Strengthened Directive (Prevention)

**Location:** [commands.py:205-226](../tools/telegram/commands.py#L205-L226)

**Updated workflow directive:**
```
CRITICAL WORKFLOW (you MUST follow these steps in order):
1. Call rotary_read_agenda with the meeting_date to get existing content
2. Parse the full content you received
3. Find the appropriate section (President Announcements or Member Announcements)
4. Add a bullet point (- New announcement text) to that section
5. Call rotary_save_agenda with the COMPLETE updated content (all sections intact)

NEVER call rotary_save_agenda without reading the existing content first
NEVER save partial content - you must preserve ALL sections of the agenda
```

---

## How to Test

### Test 1: Normal Add (Should Work)

Via Telegram bot:
```
/rotary add president announcement to 2/10 agenda - Test announcement
```

**Expected behavior:**
1. Bot calls `rotary_read_agenda(meeting_date="2026-02-10")`
2. Bot parses the full agenda
3. Bot adds bullet point to President announcements section
4. Bot calls `rotary_save_agenda` with complete content (all sections)
5. Backup created automatically
6. Bot replies: "Added to 2/10 agenda ✓"

### Test 2: Accidental Overwrite (Should Block)

Manually test the validation by trying to save truncated content:
```python
from tools.telegram.tool_runner import _rotary_save_agenda

result = _rotary_save_agenda({
    "meeting_date": "2026-02-10",
    "content": "**President Announcements**\n- Short content only"
})

# Should return:
# {"success": False, "error": "Content too short..."}
```

---

## Recovery from Overwrites

If an agenda does get overwritten despite safeguards:

1. **Check backups:**
   ```bash
   ls -la "~/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary/Meetings/backups/"
   ```

2. **Find latest backup for that date:**
   ```bash
   # Example: restore 2026-02-10
   cd "~/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary/Meetings/backups/"
   ls -t | grep "2026-02-10" | head -1
   ```

3. **Copy backup back:**
   ```bash
   cp "2026-02-10_backup_20260211_091500.md" "../2026-02-10 Agenda.md"
   ```

---

## Maintenance

### Backup Cleanup

Backups accumulate over time. Safe to delete after meeting is complete:

```bash
# Delete backups older than 60 days
find "~/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary/Meetings/backups/" \
  -name "*.md" -mtime +60 -delete
```

### Monitoring

Check logs for blocked save attempts:
```bash
grep "BLOCKED suspicious overwrite" logs/telegram-bot.log
```

---

## Technical Details

### Validation Thresholds

**Why 500 characters?**
- A minimal valid agenda (all sections present) is ~600-700 characters
- 500 chars catches partial content without false positives

**Why 50% threshold?**
- Adding content increases length (100%+)
- Editing slightly decreases length (90-100%)
- Overwriting with partial content drastically decreases length (10-30%)
- 50% is the sweet spot - real edits pass, overwrites blocked

### Backup Storage

**Location chosen:** `Meetings/backups/` (same directory)
- Easy to find when needed
- Synced via Dropbox alongside agendas
- Simple flat structure

**Filename format:** `YYYY-MM-DD_backup_YYYYMMDD_HHMMSS.md`
- Meeting date first for easy grouping
- Timestamp for uniqueness
- Multiple backups per meeting supported

---

## Related Issues

- Original bug report: User message 2026-02-11
- Rotary add feature docs: [ROTARY_ADD_FEATURE.md](ROTARY_ADD_FEATURE.md)
- Telegram bot safeguards: [TELEGRAM_BOT_SAFEGUARDS.md](TELEGRAM_BOT_SAFEGUARDS.md)
