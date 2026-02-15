# Credential Loading - Centralized Pattern

## Problem

Atlas tools run in two different contexts:
1. **Launchd** (user session) - CAN access macOS Keychain → envchain works
2. **Cron** (system context) - CANNOT access macOS Keychain → envchain fails

This led to inconsistent behavior where cron jobs would fail with "namespace atlas not defined" errors.

## Solution

**Centralized credential loader**: `tools/common/credentials.py`

All scripts now import and use this single module for loading credentials. It tries envchain first (for launchd), then falls back to .env (for cron).

## Usage

```python
from tools.common.credentials import get_telegram_token, get_credential

# Get TELEGRAM_BOT_TOKEN
token = get_telegram_token()
if not token:
    print("TELEGRAM_BOT_TOKEN not available")
    sys.exit(1)

# Get any credential
db_url = get_credential("MINDSETLOG_DB_URL")
api_key = get_credential("SOME_API_KEY", required=True)  # Raises ValueError if missing
```

## Migration Pattern

**OLD CODE:**
```python
import os
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    # Read from .env...
```

**NEW CODE:**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from common.credentials import get_telegram_token

token = get_telegram_token()
if not token:
    print("TELEGRAM_BOT_TOKEN not available")
    sys.exit(1)
```

## Files Already Migrated

- ✅ `tools/bambu/bambu_reply_handler.py`
- ✅ `tools/bambu/bambu_prompt_poller.py`

## Files That Need Migration

All files that reference `TELEGRAM_BOT_TOKEN`:

### High Priority (run via cron, frequently error)
- `tools/tasks/claude_task_runner.py`
- `tools/tasks/task_executor.py`
- `tools/system/service_health_monitor.py`
- `tools/briefings/weekly_review.py`
- `tools/legal/wa_dui_bill_tracker.py`
- `tools/briefings/local_news.py`

### Medium Priority (run via launchd, already working but should be consistent)
- `tools/briefings/daily_brief.py`
- `tools/heartbeat/watchdog.py`
- `tools/briefings/research_brief.py`

### Low Priority (test scripts, not critical)
- `tools/telegram/bot.py` - uses python-telegram-bot which loads from env
- `tools/telegram/send_test_message.py`
- `tools/telegram/test_bot.py`
- `tools/telegram/comprehensive_test.py`
- `scripts/test_envchain.py`

## Files That Need `MINDSETLOG_DB_URL`

**IMPORTANT**: Database credentials are NOT in .env (security policy). These scripts MUST run via launchd with envchain, NOT cron.

- `tools/briefings/mindsetlog_db_sync.py` - Currently cron, **migrate to launchd**
- `tools/briefings/health_monitor.py` - Currently cron, **migrate to launchd**
- `tools/briefings/wellness_coach.py` - Currently cron, **migrate to launchd**
- `tools/briefings/monthly_fitness_review.py` - Currently cron, **migrate to launchd**
- `tools/briefings/health_stats.py`

## Security Policy

**.env Contains:**
- TELEGRAM_BOT_TOKEN only (acceptable risk for notifications)

**.env Does NOT Contain:**
- Database credentials (MINDSETLOG_DB_URL, LEGALKANBAN)
- These remain in envchain only → launchd jobs only

**Implication:**
- Cron jobs can send Telegram messages ✅
- Cron jobs CANNOT access databases ❌
- Database access requires migration to launchd

## Benefits

1. **Consistency**: One way to load credentials across all scripts
2. **Reliability**: Works in both launchd and cron contexts (for Telegram)
3. **Security**: Database credentials only in Keychain, never on disk
4. **Maintainability**: Single place to update credential loading logic
5. **Clarity**: No more custom `_load_bot_token()` functions scattered everywhere

## Best Practices

1. Always use `tools/common/credentials.py` for credential loading
2. Never write custom .env parsing code
3. For new credentials, add a helper function to credentials.py (like `get_telegram_token()`)
4. Log clear error messages when credentials are missing
