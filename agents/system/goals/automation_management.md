# Goal: System Automation Management

## Objective
Configure, monitor, and maintain Atlas system automations (cron, launchd, health checks, backups).

## Agent Focus
The **System Agent** specializes in:
- Automation configuration (cron, launchd)
- Service health monitoring
- Backup management
- Script generation
- System troubleshooting

## Key Tools
- `tools/system/system_config.py` — Configure automations
- `tools/system/cron_manager.py` — Cron job management
- `tools/system/script_writer.py` — Generate Python scripts
- `tools/system/service_health_monitor.py` — Monitor service status
- `tools/heartbeat/watchdog.py` — Error scanner

## Process

### 1. Automation Configuration
**system_config.py**

**Capabilities:**
- Update chat IDs for briefings
- Add/remove/update cron schedules
- Create new monitoring jobs
- List all automations

**Usage:**
```bash
# Update Telegram chat ID
python tools/system/system_config.py --action update_chat_id --chat-id 8241581699

# Add cron job
python tools/system/system_config.py --action add_cron --script-path tools/bambu/bambu_watcher.py --schedule "*/5 * * * *"

# Remove cron job
python tools/system/system_config.py --action remove_cron --script-path tools/bambu/bambu_watcher.py

# Update cron schedule
python tools/system/system_config.py --action update_cron_time --script-path tools/briefings/daily_brief.py --schedule "0 6 * * *"

# List all automations
python tools/system/system_config.py --action list_automations
```

### 2. Cron Management
**cron_manager.py**

**Operations:**
```bash
# List current cron jobs
python tools/system/cron_manager.py list

# Add new job
python tools/system/cron_manager.py add --schedule "*/5 * * * *" --command "/opt/homebrew/bin/python3 /Users/printer/atlas/tools/bambu/bambu_watcher.py"

# Remove job
python tools/system/cron_manager.py remove --pattern "bambu_watcher"

# Update schedule
python tools/system/cron_manager.py update --pattern "daily_brief" --schedule "0 6 * * *"
```

**Cron vs Launchd:**
- Use **cron** for: Simple file watchers, scripts with .env credentials only
- Use **launchd** for: Scripts needing Keychain access (OAuth, envchain)

### 3. Script Generation
**script_writer.py**

**Generates working Python scripts from natural language descriptions**

**Usage:**
```bash
python tools/system/script_writer.py \
  --task "Monitor website uptime and send Telegram alert on downtime" \
  --output tools/monitoring/uptime_monitor.py \
  --schedule "*/5 * * * *"
```

**What it creates:**
- Working Python script with imports, error handling, logging
- Atlas integration (Telegram, credentials, paths)
- Optional cron installation

**Requirements:**
- Clear task description (what, inputs, outputs, error handling)
- Output path (where to save script)
- Optional schedule (cron format)

### 4. Service Health Monitoring
**service_health_monitor.py**

**Monitors:**
- Cron jobs (last run time, success/failure)
- Launchd agents (running status)
- Log file sizes (detect runaway logs)
- Database connections (test connectivity)
- API endpoints (health checks)

**Usage:**
```bash
python tools/system/service_health_monitor.py --action check_all
```

**Outputs:**
```json
{
  "cron": {
    "bambu_watcher": {"last_run": "2026-02-09 19:00", "status": "ok"},
    "daily_brief": {"last_run": "2026-02-09 06:00", "status": "ok"}
  },
  "launchd": {
    "com.atlas.legalkanban-sync": {"status": "running"}
  },
  "logs": {
    "oversized": []
  },
  "databases": {
    "mindsetlog": {"status": "connected"},
    "legalkanban": {"status": "connected"}
  }
}
```

### 5. Error Monitoring (Watchdog)
**heartbeat/watchdog.py**

**Runs:** Daily at 6:05 AM (after daily brief)

**Process:**
1. Scans today's log files in `logs/`
2. Searches for error patterns:
   - Python tracebacks
   - "error:" (case insensitive)
   - "failed"
   - HTTP error codes (4xx, 5xx)
3. Filters false positives:
   - "Calendar error:" (known transient)
   - "Weather error:" (timeouts expected)
4. Sends Telegram alert if errors found

**Launchd:**
```xml
~/Library/LaunchAgents/com.atlas.watchdog.plist
```

## Edge Cases

### Cron Keychain Access
**Problem:** Cron can't access macOS Keychain
**Solution:** Use launchd for scripts needing OAuth/envchain

**Example:**
```bash
# ❌ Won't work (cron can't access Keychain)
0 6 * * * envchain atlas python3 tools/briefings/daily_brief.py

# ✅ Works (launchd runs in user session)
~/Library/LaunchAgents/com.atlas.daily-brief.plist
```

### Envchain in Launchd
**Problem:** Launchd needs explicit envchain wrapper
**Solution:** Wrap ProgramArguments with envchain

```xml
<key>ProgramArguments</key>
<array>
  <string>/opt/homebrew/bin/envchain</string>
  <string>atlas</string>
  <string>/opt/homebrew/bin/python3</string>
  <string>/Users/printer/atlas/tools/briefings/daily_brief.py</string>
</array>
```

### Log File Growth
**Problem:** Uncapped logs can fill disk
**Solution:** Implement log rotation

```python
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    "logs/script.log",
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

### Service Restart on Failure
**Launchd auto-restart:**
```xml
<key>KeepAlive</key>
<true/>
<!-- OR -->
<key>RunAtLoad</key>
<true/>
```

## Success Criteria
- All automations running on schedule
- Service health check passes
- No unhandled errors in logs
- Backups completing successfully
- System uptime >99%

## Known Issues
- Cron Keychain limitation (use launchd instead)
- Log rotation not implemented on all scripts
- No centralized automation dashboard (manual checks)

## Future Enhancements
- Web dashboard for automation status
- Automated recovery for failed services
- Performance metrics (execution time, resource usage)
- Integration with monitoring services (Sentry, DataDog)

## References
- `docs/CRON.md` — Cron vs launchd guidance
- `docs/ENVCHAIN.md` — Credential management
- Launchd plists: `~/Library/LaunchAgents/com.atlas.*.plist`
- Logs: `logs/*.log`
