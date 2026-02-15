# Rotary Add Feature - February 9, 2026

## New Capability: Edit Existing Agendas

The Telegram bot can now append to existing Rotary agendas without recreating them from scratch.

## What Changed

### New Tool: `rotary_read_agenda`

**Function**: Reads an existing agenda file by date
**Location**: [tool_runner.py](../tools/telegram/tool_runner.py:595)

**Parameters:**
- `meeting_date` (required): Date in YYYY-MM-DD format

**Returns:**
```json
{
  "success": true,
  "content": "<agenda content>",
  "date": "2026-02-10"
}
```

**File Path**: Agendas are stored at:
```
~/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary/Meetings/YYYY-MM-DD Agenda.md
```

## Usage

### Quick Add (New Feature)
```
/rotary add president announcement to 2/10 agenda - Funds available for service projects
```

**Bot behavior:**
1. Parses date "2/10" → "2026-02-10"
2. Calls `rotary_read_agenda(meeting_date="2026-02-10")`
3. Finds "President Announcements" section
4. Adds bullet point: `- Funds available for service projects`
5. Saves updated agenda
6. Replies: "Added to 2/10 agenda ✓"

### Full Workflow (Existing Feature)
```
/rotary
```

**Bot behavior:**
1. Interactive questions for all agenda sections
2. Uses template
3. Creates complete agenda from scratch

## Example: Adding Multiple Announcements

```
/rotary add president announcement to 2/10 agenda - 2 new members: Gemma Withrow and Rick Baker

/rotary add president announcement to 2/10 agenda - 250th year of USA celebrations - ideas on what we could do to join? Russell is point
```

Each command appends a new bullet point to the President Announcements section.

## Technical Details

### Date Parsing
The bot understands flexible date formats:
- `2/10` → assumes current year (2026)
- `02/10` → assumes current year
- `2026-02-10` → explicit year

### Section Detection
The bot looks for these headings in the agenda:
- `## President Announcements`
- `## Member Announcements`

And adds bullets under the appropriate section.

### Error Handling

**If agenda doesn't exist:**
```json
{
  "success": false,
  "error": "No agenda found for 2026-02-10."
}
```

**If date format is invalid:**
```json
{
  "success": false,
  "error": "Invalid meeting_date format. Use YYYY-MM-DD."
}
```

## Files Modified

1. **[tool_runner.py](../tools/telegram/tool_runner.py)**
   - Added `_rotary_read_agenda()` function (line 595)
   - Added dispatcher entry (line 141)

2. **[tool_definitions.py](../tools/telegram/tool_definitions.py)**
   - Added `rotary_read_agenda` tool definition (line 259)

3. **[commands.py](../tools/telegram/commands.py)**
   - Updated `ROTARY_AGENDA_DIRECTIVE` to use new tool (line 205)

## Testing

### Test 1: Add to Existing Agenda
```
/rotary add president announcement to 2/10 agenda - Test announcement
```

**Expected result:**
- Bot reads 2026-02-10 Agenda.md
- Adds bullet point under President Announcements
- Saves updated file
- Replies: "Added to 2/10 agenda ✓"

### Test 2: Agenda Doesn't Exist
```
/rotary add president announcement to 12/31 agenda - Test
```

**Expected result:**
- Bot tries to read 2026-12-31 Agenda.md
- File not found
- Bot replies with error: "No agenda found for 2026-12-31."

### Test 3: Full Workflow Still Works
```
/rotary
```

**Expected result:**
- Interactive workflow unchanged
- Asks for guests, announcements, etc.
- Creates new agenda from template

## Troubleshooting

### Bot can't find agenda
- Check file exists: `~/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary/Meetings/2026-02-10 Agenda.md`
- Check date format matches YYYY-MM-DD pattern
- Verify file has correct sections (## President Announcements, etc.)

### Bot adds to wrong section
- Check the announcement text contains keywords: "president" or "member"
- Bot defaults to President Announcements if ambiguous

### Bot creates new agenda instead of adding
- Verify you used `/rotary add` not just `/rotary`
- Check the directive was loaded correctly (restart bot if needed)

## Related Documentation

- [TELEGRAM_BOT_FIXES_2026-02-09.md](TELEGRAM_BOT_FIXES_2026-02-09.md) - Today's other fixes
- [FIX_SUMMARY_2026-02-09.md](FIX_SUMMARY_2026-02-09.md) - Full system fixes
