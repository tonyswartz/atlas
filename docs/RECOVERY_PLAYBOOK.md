# Recovery Playbook

Quick reference for recovering from common system failures.

---

## JeevesUI Not Loading

**Symptoms:** Shows "Loading..." with no styling, or navigation but blank content

**Quick Fix:**
```bash
cd /Users/printer/clawd/JeevesUI
npm run build
launchctl restart com.jeeves-ui
```

**If directory is missing:**
```bash
# Option 1: Restore from Atlas backup
cd /Users/printer/atlas/backups/jeevesui
tar -xzf jeevesui-*.tar.gz -C /Users/printer/clawd/

# Option 2: Restore from system backup
cd /Users/printer
tar -xzf clawdbot-backup-*.tar.gz "Users/printer/clawd/JeevesUI/"
mv Users/printer/clawd/JeevesUI /Users/printer/clawd/
rm -rf Users

# Then rebuild
cd /Users/printer/clawd/JeevesUI
npm install --legacy-peer-deps
npm run build
launchctl start com.jeeves-ui
```

**Verify recovery:**
```bash
curl http://localhost:6001/api/health | jq
```

---

## Bambu Integration Not Working

**Symptoms:** Print completions not being detected, prompts not appearing

**Check status:**
```bash
# Check BambuBuddy watcher
tail -20 /Users/printer/atlas/logs/bambu_buddy_watcher.log

# Check pending prompts
cat /Users/printer/atlas/memory/bambu-pending-prompts.md

# Check JeevesUI connectivity
curl -s http://localhost:6001/api/filament/spools | jq 'length'
```

**Common fixes:**
```bash
# Restart BambuBuddy watcher (if stale)
# It runs via cron, will auto-restart on next run

# Check if JeevesUI is down
launchctl start com.jeeves-ui

# Check fallback CSV for missed prints
cat /Users/printer/atlas/data/print_jobs_fallback.csv
```

---

## Telegram Bot Not Responding

**Symptoms:** Bot doesn't respond to commands or messages

**Check status:**
```bash
ps aux | grep bot.py
tail -20 /Users/printer/atlas/logs/telegram_bot.log
```

**Restart:**
```bash
launchctl stop com.atlas.telegram-bot
launchctl start com.atlas.telegram-bot

# Verify
ps aux | grep bot.py
```

---

## Daily Brief Not Sending

**Symptoms:** No morning brief at 6 AM

**Check logs:**
```bash
tail -50 /Users/printer/atlas/logs/daily_brief.log
```

**Common issues:**
- **Keychain access:** Daily brief uses launchd (not cron) to access Keychain
- **gog credentials expired:** Run `/apps/gog/gog login` to refresh
- **Weather API timeout:** Check logs for timeout errors

**Manual run:**
```bash
cd /Users/printer/atlas
/opt/homebrew/bin/python3 tools/briefings/daily_brief.py
```

---

## Service Health Monitor Not Auto-Recovering

**Check monitor status:**
```bash
tail -50 /Users/printer/atlas/logs/service_health_monitor.log
cat /Users/printer/atlas/data/service_health_state.json
```

**Force recovery:**
```bash
# Run monitor manually
/opt/homebrew/bin/python3 /Users/printer/atlas/tools/system/service_health_monitor.py

# Clear recovery state (if stuck)
rm /Users/printer/atlas/data/service_health_state.json
```

---

## Disk Space Full

**Check usage:**
```bash
df -h /
du -sh ~/Library/Logs
du -sh /Users/printer/atlas/logs
du -sh /Users/printer/atlas/backups
```

**Clean up:**
```bash
# Rotate logs
find /Users/printer/atlas/logs -name "*.log" -mtime +30 -delete

# Clean old backups
find /Users/printer/atlas/backups -name "*.tar.gz" -mtime +14 -delete

# Clean npm cache
npm cache clean --force

# Clean old JeevesUI builds
cd /Users/printer/clawd/JeevesUI && rm -rf .next
```

---

## System-Wide Health Check

**Run comprehensive status check:**
```bash
# Service health
/opt/homebrew/bin/python3 /Users/printer/atlas/tools/system/service_health_monitor.py

# Check recent errors
tail -100 /Users/printer/atlas/logs/*.log | grep -i error

# Check cron jobs
crontab -l

# Check launchd jobs
launchctl list | grep -E "atlas|jeeves"

# Disk space
df -h /

# Process status
ps aux | grep -E "bot.py|node.*6001|bambu"
```

---

## Emergency Contacts

- **Telegram:** Send `/status` to bot for system health
- **Logs:** `/Users/printer/atlas/logs/`
- **Backups:** `/Users/printer/atlas/backups/`
- **State files:** `/Users/printer/atlas/data/`
