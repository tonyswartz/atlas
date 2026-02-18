# Bytecode Cache - PERMANENT FIX Applied (2026-02-18)

## What Changed Today

You asked: **"We have tried to fix that bytecode issue daily for weeks. What do we do different to stop that forever?"**

The previous fixes failed because they only addressed symptoms, not the root cause.

---

## The Root Cause

**Previous attempts (2026-02-13 to 2026-02-16):**
- ✅ Fixed source code (model name)
- ✅ Added `PYTHONDONTWRITEBYTECODE=1` env var
- ✅ Created git post-merge hook to clean cache

**Why they failed:**
- Env var only prevents NEW bytecode (doesn't delete existing)
- Git hook only runs after `git pull` (daily services never pull)
- Old bytecode from before the fix persisted indefinitely

**Result:** Daily 6am services kept using stale bytecode from weeks ago.

---

## The Permanent Fix: 3 Layers

### Layer 1: Daily Automated Cleanup ⭐ **THE KEY**

**What:** New launchd service runs every day at **5:55am** (before daily services at 6am)

**Does:** Deletes ALL Python bytecode cache (`__pycache__/`, `*.pyc` files)

**Files Created:**
- `tools/system/cleanup_bytecode.sh` - The cleanup script
- `~/Library/LaunchAgents/com.atlas.bytecode-cleanup.plist` - Launchd config
- `logs/bytecode_cleanup.log` - Daily cleanup log

**Why this works:** Guarantees fresh Python imports every single day, regardless of git activity.

### Layer 2: Python `-B` Flag (Failsafe)

**What:** Added `-B` flag to Python invocations in critical services

**Services Updated:**
- com.atlas.daily-brief
- com.atlas.local-news
- com.atlas.wa-dui-tracker
- com.atlas.watchdog
- com.atlas.weekly-review

**Does:** Even if cleanup fails, Python will ignore bytecode cache entirely

**Tool Created:** `tools/system/add_python_B_flag.sh` to add flag to future services

### Layer 3: Environment Variable (Kept as defense-in-depth)

**What:** `PYTHONDONTWRITEBYTECODE=1` in all launchd plists (already had this)

**Does:** Prevents NEW bytecode from being written

**Why keep it:** Defense in depth - prevents cache accumulation between daily cleanups

---

## Why This Is Actually Permanent

**Timeline:**
```
5:55 AM  → Cleanup service deletes all bytecode
5:56 AM  → System is clean
6:00 AM  → daily_brief runs with:
            • No bytecode cache (just deleted)
            • Python -B flag (ignores cache anyway)
            • PYTHONDONTWRITEBYTECODE=1 (won't create new cache)
```

**Failure modes eliminated:**
- ❌ "Forgot to clean cache" → Automated, runs daily
- ❌ "No git pull so hook didn't run" → Time-based trigger
- ❌ "Cleanup failed but service ran" → `-B` flag ignores cache anyway

**This will work because:**
1. **Automated** - No human action required
2. **Scheduled** - Runs before services need it
3. **Triple redundancy** - 3 independent layers

---

## Verification

All 3 layers confirmed working:

```
✅ Layer 1: Daily cleanup service loaded and tested
✅ Layer 2: 5 critical services have -B flag
✅ Layer 3: 33 services have PYTHONDONTWRITEBYTECODE=1
✅ Current state: 0 bytecode files exist
```

---

## What To Expect

**Tomorrow (2026-02-19) at 6:00 AM:**
- Cleanup service will run at 5:55am
- daily_brief will use fresh imports
- Case law summaries will work correctly
- No more `minimax_coding` errors

**Future:**
- This runs automatically every day
- No maintenance needed
- No manual cleanup needed
- Works even if you never `git pull`

---

## Documentation

Full technical details: [`docs/BYTECODE_PERMANENT_FIX.md`](./BYTECODE_PERMANENT_FIX.md)

Verification commands:
```bash
# Check cleanup service is running
launchctl list | grep bytecode-cleanup

# View cleanup history
tail -20 logs/bytecode_cleanup.log

# Verify no bytecode exists
find /Users/printer/atlas -name '__pycache__' -o -name '*.pyc' | wc -l
# Should always show: 0
```

---

## Also Fixed Today

1. **✅ `.env` parsing error** - Quoted MCP URL on line 3
2. **✅ Daily brief task filter** - Now only shows overdue + today tasks (removed future/no-date tasks)

---

**This fix addresses the root cause, not symptoms. The bytecode issue should never recur.**
