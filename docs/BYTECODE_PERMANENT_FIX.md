# Bytecode Cache Permanent Fix

**Problem:** Python bytecode cache (`.pyc` files, `__pycache__/` directories) caused recurring issues where stale cached code was used despite source file updates. This manifested as:
- Case law summaries using old model name `minimax_coding` despite source showing `MiniMax-M2.5`
- Errors recurring daily despite source code fixes

**Root Cause:** Previous fixes (env vars, git hooks) only prevented NEW bytecode or cleaned after git operations. Daily launchd services ran without git pulls, so old bytecode persisted indefinitely.

---

## The 3-Layer Defense (2026-02-18)

### Layer 1: Daily Automated Cleanup ⭐ **KEY FIX**

**What:** Launchd service runs daily at 5:55am (before 6am services) to delete ALL bytecode cache

**Files:**
- Script: `tools/system/cleanup_bytecode.sh`
- Plist: `~/Library/LaunchAgents/com.atlas.bytecode-cleanup.plist`
- Logs: `logs/bytecode_cleanup.log`

**Why this works:** Guarantees fresh Python imports every day regardless of git activity

**Verify it's running:**
```bash
launchctl list | grep bytecode-cleanup
tail logs/bytecode_cleanup.log
```

### Layer 2: Python `-B` Flag

**What:** Python's `-B` flag tells Python to ignore bytecode cache even if it exists

**Applied to critical services:**
- `com.atlas.daily-brief`
- `com.atlas.local-news`
- `com.atlas.wa-dui-tracker`
- `com.atlas.watchdog`
- `com.atlas.weekly-review`

**How to add to more services:**
```bash
./tools/system/add_python_B_flag.sh
```

**Example ProgramArguments:**
```xml
<array>
    <string>/opt/homebrew/bin/envchain</string>
    <string>atlas</string>
    <string>/opt/homebrew/bin/python3</string>
    <string>-B</string>  <!-- This line added -->
    <string>/path/to/script.py</string>
</array>
```

### Layer 3: Environment Variable (Kept)

**What:** `PYTHONDONTWRITEBYTECODE=1` in all launchd plists prevents NEW bytecode creation

**Why keep it:** Defense in depth - prevents cache accumulation between daily cleanups

---

## Why This Is Actually Permanent

**Previous attempts failed because:**
1. Env var only prevents new cache (doesn't delete existing)
2. Git hook only runs after `git pull` (services never pull)
3. Manual cleanup requires human memory (unreliable)

**This solution works because:**
1. ✅ Automated daily cleanup (5:55am) - no human action needed
2. ✅ Python `-B` flag - works even if cleanup fails
3. ✅ Runs BEFORE daily services (6am) - timing guarantees fresh state

**Failure modes eliminated:**
- ❌ "Forgot to clean cache manually" → Automated
- ❌ "No git pull so hook didn't run" → Time-based trigger
- ❌ "Cleanup failed but service ran anyway" → `-B` flag ignores cache

---

## Maintenance

**Add `-B` flag to new Python services:**
Edit the service's plist, add `<string>-B</string>` after the `python3` line, reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.NEW-SERVICE.plist
launchctl load ~/Library/LaunchAgents/com.atlas.NEW-SERVICE.plist
```

**Verify cleanup is working:**
```bash
# Check service status
launchctl list | grep bytecode-cleanup

# Check recent cleanups
tail -20 logs/bytecode_cleanup.log

# Manually trigger cleanup (for testing)
./tools/system/cleanup_bytecode.sh
```

**Emergency manual cleanup:**
```bash
find /Users/printer/atlas -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null
find /Users/printer/atlas -name '*.pyc' -delete 2>/dev/null
```

---

## Verification Commands

```bash
# Verify no bytecode exists
find /Users/printer/atlas -name '__pycache__' -o -name '*.pyc' 2>/dev/null | wc -l
# Should output: 0

# Check cleanup service is loaded
launchctl list | grep bytecode-cleanup
# Should show: -	0	com.atlas.bytecode-cleanup

# Verify daily-brief has -B flag
grep -A5 "ProgramArguments" ~/Library/LaunchAgents/com.atlas.daily-brief.plist | grep -- "-B"
# Should show: <string>-B</string>
```

---

## History

- **2026-02-13:** Fixed model name in source code
- **2026-02-15:** Manual bytecode cleanup (recurred next day)
- **2026-02-16:** Added env var + git hook (still recurred)
- **2026-02-18:** ✅ **PERMANENT FIX** - Daily cleanup service + `-B` flag

**This fix addresses the root cause: stale bytecode persisting between runs.**
