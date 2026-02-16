# Autonomous Code Repair System

The Telegram bot includes a self-healing system that **automatically diagnoses and fixes failing tools** using MiniMax AI.

## How It Works

### 1. Failure Detection

The `bot_health_monitor.py` runs every 10 minutes and:
- Detects tool loops (bot stuck calling tools without generating text)
- Identifies which tool caused the failure
- Tracks failures in `data/bot_failure_tracking.json`

### 2. Pattern Recognition

When the same tool fails **3+ times within 6 hours**, the system triggers auto-repair.

### 3. Autonomous Repair Process

The `auto_fixer.py` script:

1. **Diagnoses** - Calls MiniMax with:
   - Current code
   - Recent failure logs
   - Error messages
   - Contextual information

2. **Generates Fix** - MiniMax analyzes root cause and proposes minimal fix

3. **Creates Backup** - Original code saved to `data/backups/` with timestamp

4. **Applies Fix** - Writes corrected code to the tool file

5. **Validates** - Runs Python syntax check to ensure fix is valid

6. **Commits to Git** - Creates detailed commit with:
   - Tool name
   - Number of failures
   - Time window
   - Backup location
   - Error summaries
   - Co-authored by: MiniMax M2.5

7. **Sends Alert** - Notifies you via Telegram with commit hash

## Configuration

Edit `args/telegram.yaml`:

```yaml
bot:
  auto_fix:
    enabled: true  # Master switch
    failures_threshold: 3  # How many failures trigger repair
    time_window_hours: 6  # Within this time window
```

**To disable:** Set `enabled: false`

## Safety Features

### Backups
Every fix creates a timestamped backup:
```
data/backups/tool_name_backup_20260216_140530.py
```

### Git History
All fixes are committed to git with detailed messages:
```bash
git log  # See all auto-fixes
git show <commit_hash>  # Review specific fix
```

### Syntax Validation
Fixes are validated before deployment. If syntax check fails, the system:
- Rolls back to original code
- Logs the failure
- Sends alert that auto-fix failed

### Rollback
To undo an auto-fix:

```bash
# Option 1: Git revert (recommended)
git revert <commit_hash>

# Option 2: Restore from backup
cp data/backups/tool_name_backup_TIMESTAMP.py tools/telegram/tool_name.py
git add tools/telegram/tool_name.py
git commit -m "Rollback auto-fix - restore from backup"
```

## Example Workflow

**Scenario:** The `rotary_read_agenda` tool has a KeyError bug

1. **10:30 AM** - User sends `/rotary`, bot hits tool loop
   - Monitor detects failure
   - Records: `rotary_tool` failed at 10:30

2. **10:45 AM** - User tries again, same error
   - Monitor records 2nd failure

3. **11:00 AM** - User tries third time
   - Monitor detects pattern: 3 failures in 30 minutes
   - **Triggers auto-fixer**

4. **Auto-fixer process:**
   ```
   [11:00:15] 🔧 Starting auto-fix for tool: rotary_tool
   [11:00:16] ✓ Created backup: rotary_tool_backup_20260216_110016.py
   [11:00:45] ✓ Applied fix to tools/telegram/rotary_tool.py
   [11:00:46] ✓ Fix validated and applied successfully
   [11:00:47] ✓ Committed fix to git: a1b2c3d
   ```

5. **Telegram Alert:**
   ```
   🔧 Bot Health Monitor

   Issues detected and remediated:

   • Tool loop in session 8241581699

   🤖 Autonomous Code Repairs:

   • ✓ Auto-fixed rotary_tool: Auto-fixed rotary_tool after 3 failures.
     Backup: rotary_tool_backup_20260216_110016.py (commit: a1b2c3d)

   Cleared sessions: 8241581699
   ```

6. **Next time user sends `/rotary`** - works perfectly!

## What Gets Fixed

The auto-fixer can repair:
- **Logic errors** (wrong conditionals, missing edge cases)
- **KeyErrors** (accessing missing dict keys)
- **AttributeErrors** (calling methods on None)
- **IndexErrors** (list index out of range)
- **Type mismatches** (string vs int comparisons)
- **Missing error handling** (try/except blocks)
- **API integration issues** (wrong parameters, response parsing)

## What It Can't Fix

- **External dependencies** (API changes, network issues)
- **Data format changes** (upstream schema changes)
- **Configuration errors** (wrong API keys, missing files)
- **Architectural problems** (need to redesign tool completely)

For these issues, you'll get an alert that auto-fix failed, and manual intervention is needed.

## Monitoring

**View failure tracking:**
```bash
cat data/bot_failure_tracking.json
```

**Check auto-fixer logs:**
```bash
tail -f logs/auto_fixer.log
```

**Review all auto-fixes:**
```bash
git log --grep="Auto-fix:" --oneline
```

**See backups:**
```bash
ls -lah data/backups/
```

## Advanced Usage

### Manual Trigger

You can manually trigger a fix for testing:

```python
from tools.telegram.auto_fixer import fix_tool

failures = [
    {
        "timestamp": "2026-02-16 10:30:00",
        "error": "KeyError: 'content'",
        "context": "Session had messages without content field"
    }
]

result = fix_tool("test_tool", failures)
print(result)
```

### Disable for Specific Tools

To prevent auto-fixing a specific tool, you'd need to modify the tool name detection logic in `bot_health_monitor.py` to exclude it. Generally not recommended - better to disable auto-fix globally if you're concerned.

### Review Before Deploy

If you want to review fixes before they're applied:
1. Set `enabled: false` in config
2. Monitor will still track failures
3. When pattern detected, you'll get alert
4. Manually run auto-fixer and review the fix
5. Commit if satisfied

## Cost

Each auto-fix makes one MiniMax API call (~$0.01 per fix).

With `failures_threshold: 3` and `time_window_hours: 6`, the system is conservative and only fixes recurring problems, not one-off glitches.

## Philosophy

**The system treats symptoms AND root causes:**
- **Immediate relief** - Clear stuck sessions, restart bot (symptom)
- **Permanent cure** - Fix the underlying code bug (root cause)

This creates a truly autonomous system that gets more reliable over time, not just temporarily masked issues.

---

**Built:** 2026-02-16
**Model:** MiniMax M2.5 (SOTA for coding/agents)
**Trigger:** 3 failures in 6 hours
**Safety:** Backups + Git commits + Syntax validation
