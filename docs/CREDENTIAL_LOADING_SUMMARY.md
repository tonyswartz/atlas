# Credential Loading - Complete Solution Summary

## Problem
Cron jobs using `envchain atlas` were failing with "namespace atlas not defined" because **cron cannot access macOS Keychain**.

## Root Cause
- Launchd jobs run in user session → CAN access Keychain → envchain works ✅
- Cron jobs run in system context → CANNOT access Keychain → envchain fails ❌
- Each script had custom .env fallback code → inconsistent, scattered implementations

## Solution Implemented (2026-02-09)

### 1. Centralized Credential Loader
Created `tools/common/credentials.py`:
- Single module that ALL scripts import
- Tries envchain first (environment variables)
- Falls back to .env file automatically
- Works reliably in BOTH launchd and cron contexts

### 2. Minimal .env for Cron Fallback
Created `/Users/printer/atlas/.env` with:
- TELEGRAM_BOT_TOKEN only
- **NOT included**: Database credentials (MINDSETLOG_DB_URL, LEGALKANBAN)
- **Reason**: Database access requires envchain/launchd for security
- Permissions: 600 (owner read/write only)
- Gitignored (never committed)

### 3. Updated Scripts
- ✅ `tools/bambu/bambu_reply_handler.py` - uses `get_telegram_token()`
- ✅ `tools/bambu/bambu_prompt_poller.py` - uses `get_telegram_token()`

### 4. Removed Duplicate Code
- Deleted custom `_load_bot_token()` functions from Bambu scripts
- Now all use centralized `tools/common/credentials.py`

## How It Works

```python
# OLD WAY (scattered, inconsistent):
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    # Read from .env file... (each script does this differently)

# NEW WAY (centralized, consistent):
from tools.common.credentials import get_telegram_token
token = get_telegram_token()  # Works in BOTH launchd and cron!
```

### Execution Flow
1. **Launchd job runs**:
   - Script uses `get_telegram_token()`
   - Finds token in `os.environ` (set by envchain)
   - Returns token ✅

2. **Cron job runs**:
   - Script uses `get_telegram_token()`
   - Checks `os.environ` (not present, envchain can't access Keychain)
   - Falls back to reading `/Users/printer/atlas/.env`
   - Returns token ✅

## Status

### Fixed (No More Errors)
- ✅ Bambu reply handler confirmations
- ✅ Bambu prompt poller notifications
- ✅ Consistent credential loading pattern established

### Still Need Migration
All cron jobs that access TELEGRAM_BOT_TOKEN or MINDSETLOG_DB_URL should be updated to use `tools/common/credentials.py`:

**High Priority:**
- `tools/tasks/claude_task_runner.py`
- `tools/tasks/task_executor.py`
- `tools/system/service_health_monitor.py`
- `tools/briefings/weekly_review.py`
- `tools/legal/wa_dui_bill_tracker.py`

See `docs/CREDENTIAL_LOADING.md` for complete migration list and patterns.

## Security Model
- **Telegram token**: Available in both cron (.env) and launchd (envchain)
- **Database credentials**: Only in launchd (envchain) for security
- **Implication**: Cron jobs needing database access must migrate to launchd

## Benefits
1. ✅ **Works everywhere**: Launchd, cron, manual execution - all work
2. ✅ **No more errors**: "TELEGRAM_BOT_TOKEN not found" eliminated
3. ✅ **Single source of truth**: One place to update credential loading
4. ✅ **Easy to maintain**: No scattered .env parsing code
5. ✅ **Secure**: Database credentials only in Keychain, not on disk

## Testing
```bash
# Test without envchain (simulates cron):
python3 tools/bambu/bambu_reply_handler.py  # ✅ Works

# Test with envchain (simulates launchd):
envchain atlas python3 tools/bambu/bambu_reply_handler.py  # ✅ Works
```

Both contexts now work reliably!
