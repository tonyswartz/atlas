# Cron to Launchd Migration (2026-02-09)

## Why This Was Done

**Problem**: Cron jobs using `envchain atlas` failed because cron cannot access macOS Keychain.

**Solution**: Migrated all jobs needing credentials to launchd (runs in user session with Keychain access).

## Jobs Migrated to Launchd

### Database Credentials Required (MUST be launchd)
- ✅ `mindsetlog-sync` - 11pm daily
- ✅ `health-monitor` - 7am daily
- ✅ `wellness-coach` - 7:30am daily
- ✅ `monthly-fitness-review` - 8am on 1st of month

### Telegram Only (migrated for consistency)
- ✅ `wa-dui-tracker` - 9am daily
- ✅ `local-news` - 12pm daily
- ✅ `weekly-review` - 5pm Fridays
- ✅ `claude-task-runner` - every 15 min (2, 17, 32, 47)
- ✅ `service-health-monitor` - every 10 min
- ✅ `task-executor` - every 5 min

## Jobs Remaining in Cron (No Credentials)
- ✅ `bambu_watcher.sh` - every 5 min
- ✅ `bambu_watcher_health.py` - every 30 min
- ✅ `bambu_buddy_watcher.py` - every 5 min
- ✅ `backup_jeevesui.py` - 3am daily

## All Launchd Services

```bash
launchctl list | grep com.atlas
```

Currently running:
- com.atlas.bambu-prompt-poller
- com.atlas.bambu-reply-handler
- com.atlas.claude-task-runner
- com.atlas.daily-brief
- com.atlas.health-monitor
- com.atlas.legalkanban-sync
- com.atlas.local-news
- com.atlas.mindsetlog-sync
- com.atlas.monthly-fitness-review
- com.atlas.research-brief
- com.atlas.service-health-monitor
- com.atlas.task-executor
- com.atlas.telegram-bot
- com.atlas.wa-dui-tracker
- com.atlas.watchdog
- com.atlas.weekly-review
- com.atlas.wellness-coach

## Managing Services

```bash
# Check status
launchctl list | grep com.atlas

# Unload a service
launchctl unload ~/Library/LaunchAgents/com.atlas.SERVICE_NAME.plist

# Load a service
launchctl load ~/Library/LaunchAgents/com.atlas.SERVICE_NAME.plist

# View logs
tail -f /Users/printer/atlas/logs/SERVICE_NAME.log
```

## Result

✅ **No more "namespace atlas not defined" errors**  
✅ **All services have reliable Keychain access**  
✅ **Database credentials never touch disk**  
✅ **Consistent environment across all scheduled jobs**
