# Python Bytecode Cache - Permanent Fix

## The Problem

Python automatically creates `.pyc` bytecode files in `__pycache__/` directories when running scripts. These are cached compiled versions of `.py` files for faster startup.

**Issue:** After git operations (pull, merge, checkout), source file timestamps can be confused, causing Python to use **stale bytecode** even when source code is updated. This manifested as:

- Case law summaries using old model name `minimax_coding` despite source showing `MiniMax-M2.5`
- python-dotenv parse errors from old `.env` format despite fixes being applied

## The Solution (Multi-Layer Defense)

### Layer 1: Disable Bytecode Writing (Primary Fix)

All atlas launchd services now run with `PYTHONDONTWRITEBYTECODE=1` environment variable, which prevents Python from writing `.pyc` files entirely.

**Applied to all 29 atlas launchd services:**

```bash
tools/system/fix_launchd_bytecode.sh
```

This script:
1. Backs up all plists to `~/Library/LaunchAgents/backups/`
2. Adds `EnvironmentVariables` section with `PYTHONDONTWRITEBYTECODE=1`
3. Reloads all services

**Performance impact:** Negligible - automation scripts run infrequently, Python startup is fast enough

### Layer 2: Git Post-Merge Hook (Backup Protection)

`.git/hooks/post-merge` automatically deletes all `__pycache__/` directories and `.pyc` files after git pull/merge operations.

This ensures even if bytecode is created (e.g., manual script runs), it's cleaned after code updates.

### Layer 3: Manual Cleanup (Emergency)

If issues persist despite layers 1-2:

```bash
# Delete all bytecode cache
find /Users/printer/atlas/tools -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null
find /Users/printer/atlas/tools -name '*.pyc' -delete 2>/dev/null
```

## Verification

After applying fix, verify services run with environment variable:

```bash
# Check plist has EnvironmentVariables
plutil -p ~/Library/LaunchAgents/com.atlas.daily-brief.plist | grep -A2 EnvironmentVariables

# Check running service
launchctl print gui/$(id -u)/com.atlas.daily-brief | grep -A5 environment variables
```

## When to Update This

If you add NEW launchd services:

1. Run `tools/system/fix_launchd_bytecode.sh` to apply env var to all services
2. OR manually add to new plist:

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>PYTHONDONTWRITEBYTECODE</key>
  <string>1</string>
</dict>
```

## Root Cause Analysis

Python bytecode caching is designed to improve performance by avoiding re-compilation. However, git operations can create timestamp inconsistencies:

1. Git pull updates source files
2. Timestamps might not be newer than existing `.pyc` files
3. Python sees `.pyc` is "up to date" (by timestamp), uses it
4. Stale bytecode executes with old code

**Why manual runs didn't show the issue:**
- Manual runs use current user environment
- Launchd services have isolated environments with different timing
- Fresh terminal sessions reload code; long-running launchd services cache imports

## Historical Context

- **2026-02-13**: First fix - corrected model name in source, deleted `__pycache__`
- **2026-02-15**: Issue recurred - deleted cache again, documented in MEMORY.md
- **2026-02-16**: Issue recurred again - implemented this permanent 3-layer fix

The pattern: manual fixes worked temporarily, but bytecode cache regenerated with stale code on next automated run.

## Key Lesson

**For production automation scripts, disable bytecode caching.**
The performance benefit is minimal, and cache invalidation bugs create confusing, intermittent failures that are hard to debug.

**Better:** Deterministic, predictable behavior > micro-optimizations
