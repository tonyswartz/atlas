# Goal: 3D Print Tracking

## Objective
Track completed 3D prints from Bambu Lab printer, prompt user for spool usage, and log data to JeevesUI.

## Agent Focus
The **Bambu Agent** specializes in:
- Print completion detection
- Spool usage tracking
- BambuBuddy database integration
- JeevesUI logging
- Obsidian journal integration

## Key Tools
- `tools/bambu/bambu_buddy_watcher.py` — Primary tracker (BambuBuddy SQLite DB)
- `tools/bambu/bambu_watcher.py` — FTP fallback (misses Handy app prints)
- `tools/bambu/bambu_prompt_poller.py` — Sends Telegram prompts
- `tools/bambu/bambu_reply_handler.py` — Parses replies, logs to JeevesUI

## Process

### 1. Print Detection (Primary: BambuBuddy)
**Runs every 5 minutes via cron**

```bash
*/5 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/bambu/bambu_buddy_watcher.py
```

**How it works:**
1. Queries BambuBuddy SQLite DB (`~/apps/bambuddy/bambuddy.db`)
2. Reads `print_archives` table for completed prints
3. Tracks last processed ID in `data/bambu_buddy_last_id.txt`
4. Detects new completions since last check
5. Extracts metadata: filename, filament type/color/weight
6. Appends to `memory/bambu-pending-prompts.md`

**Advantages:**
- Catches ALL prints (BambuStudio, Handy app, SD card)
- Full filament metadata for auto-matching
- No FTP access needed

### 2. Print Detection (Fallback: FTP)
**Runs every 5 minutes via cron (via wrapper)**

```bash
*/5 * * * * flock -n /tmp/bambu_watcher.lock /Users/printer/atlas/tools/bambu/bambu_watcher_wrapper.sh
```

**How it works:**
1. Connects to printer via FTPS
2. Checks `/data/Metadata/` for `.gcode` files
3. Compares timestamps to detect completion
4. **Limitation:** Misses Handy app prints (path: `/data/Metadata/plate_1.gcode`)

### 3. User Prompt (Prompt Poller)
**Runs after watcher (via wrapper)**

**How it works:**
1. Reads `memory/bambu-pending-prompts.md`
2. Fetches full spool inventory from JeevesUI API
3. Sends Telegram message:
   ```
   New print completed: [filename]

   Which spool(s)?
   1. PolyTerra PLA Mint | 824g
   2. PolyLite PLA Grey | 567g
   3. Bambu PETG White | 912g
   [...]

   Reply: spool_number, grams_used, your_name
   ```
4. Saves reply format to `memory/bambu-last-reply.txt`

**Multi-color format:**
```
Reply: 5, 42g + 8, 18g, Tony
```

### 4. Reply Parsing (Reply Handler)
**Triggered by Telegram bot on reply to prompt**

**How it works:**
1. Parses reply format: `spool_number, grams, name` or `N, Xg + M, Yg, name`
2. Looks up spool details from last prompt
3. Calls JeevesUI API:
   ```python
   POST /api/spool-log-from-telegram
   {
       "spool_id": 5,
       "grams": 42.0,
       "name": "Tony",
       "print_name": "bracket_v2.gcode"
   }
   ```
4. Logs to Obsidian journal (optional)
5. Removes from pending prompts

## Edge Cases

### BambuBuddy DB Unavailable
- Falls back to FTP watcher automatically
- Logs error but continues
- Health monitor alerts if state file not updated (20+ min)

### Multiple Pending Prompts
- Poller processes one at a time
- Each prompt gets unique message ID
- Reply handler matches by message reply chain

### Invalid Reply Format
- Reply handler sends error: "Format: spool_number, grams, name"
- Prompt remains in pending list
- User can re-reply with correct format

### Multi-Color Prints
- Reply format: `5, 42g + 8, 18g, Tony`
- Handler splits on `+`, processes each spool separately
- All spools logged to same print in JeevesUI

## Health Monitoring

**Watchdog** (`tools/bambu/bambu_watcher_health.py`)
- Runs every 30 min via cron
- Checks if `data/bambu_buddy_last_id.txt` modified in last 20 min
- Sends Telegram alert if stale (throttled to 1/day)

## Success Criteria
- All prints detected (regardless of source)
- Prompts sent within 5 minutes of completion
- Reply parsing success rate >95%
- JeevesUI logging successful
- Zero missed prints from Handy app

## Known Issues
- FTP watcher misses Handy app prints (path: `/data/Metadata/plate_1.gcode`)
  - **Fixed:** BambuBuddy watcher catches these
- Spool auto-detection not yet implemented
  - BambuBuddy has filament metadata, could auto-match

## Future Enhancements
- Auto-match spool by type/color/weight from BambuBuddy metadata
- Pre-fill reply with best-guess spool
- Track print cost per spool (current $/g rate)
- Integration with Bambu Cloud API for real-time notifications

## References
- `docs/BAMBU_NOTIFICATION_STATUS.md` — System status overview
- BambuBuddy DB schema: `print_archives` table
- JeevesUI API: `/api/spool-log-from-telegram`
