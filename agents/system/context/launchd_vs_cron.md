# Launchd vs Cron: When to Use Each

## The Critical Difference

**Cron:**
- Runs in system context (root or user)
- **Cannot access macOS Keychain**
- Cannot access OAuth tokens stored in Keychain
- Cannot use `envchain` to load credentials

**Launchd:**
- Runs in user session (via `~/Library/LaunchAgents/`)
- **Can access macOS Keychain**
- Can use `envchain` to load credentials
- More powerful scheduling options

## Decision Tree

```
Does the script need:
├─ OAuth tokens? (gog calendar, Oura, etc.)
│  └─ Use launchd
├─ envchain credentials? (TELEGRAM_BOT_TOKEN from Keychain)
│  └─ Use launchd
├─ Only .env credentials? (no Keychain)
│  └─ Can use cron
└─ No credentials at all?
   └─ Can use cron
```

## Real-World Examples

### Use Launchd For:

**Daily Brief (needs gog calendar):**
```xml
~/Library/LaunchAgents/com.atlas.daily-brief.plist

<key>ProgramArguments</key>
<array>
  <string>/opt/homebrew/bin/envchain</string>
  <string>atlas</string>
  <string>/opt/homebrew/bin/python3</string>
  <string>/Users/printer/atlas/tools/briefings/daily_brief.py</string>
</array>

<key>StartCalendarInterval</key>
<dict>
  <key>Hour</key>
  <integer>6</integer>
  <key>Minute</key>
  <integer>0</integer>
</dict>
```

**LegalKanban Sync (needs database URL from envchain):**
```xml
~/Library/LaunchAgents/com.atlas.legalkanban-sync.plist
```

**Watchdog (needs Telegram token from envchain):**
```xml
~/Library/LaunchAgents/com.atlas.watchdog.plist
```

### Use Cron For:

**Bambu Watcher (uses .env credentials only):**
```bash
*/5 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/bambu/bambu_buddy_watcher.py
```

**File monitoring (no credentials):**
```bash
*/10 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/monitoring/file_watcher.py
```

## Launchd Plist Template

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <!-- Unique reverse-domain identifier -->
  <key>Label</key>
  <string>com.atlas.script-name</string>

  <!-- Command to run (with envchain wrapper if needed) -->
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/envchain</string>
    <string>atlas</string>
    <string>/opt/homebrew/bin/python3</string>
    <string>/Users/printer/atlas/tools/category/script.py</string>
  </array>

  <!-- Schedule (daily at 6:00 AM) -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>6</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <!-- Logging -->
  <key>StandardOutPath</key>
  <string>/Users/printer/atlas/logs/script.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/printer/atlas/logs/script.error.log</string>

  <!-- Working directory -->
  <key>WorkingDirectory</key>
  <string>/Users/printer/atlas</string>

  <!-- Auto-restart on failure (optional) -->
  <key>KeepAlive</key>
  <false/>
</dict>
</plist>
```

## Managing Launchd Agents

**Load (enable):**
```bash
launchctl load ~/Library/LaunchAgents/com.atlas.script-name.plist
```

**Unload (disable):**
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.script-name.plist
```

**List loaded agents:**
```bash
launchctl list | grep com.atlas
```

**Run immediately (test):**
```bash
launchctl start com.atlas.script-name
```

**Check if running:**
```bash
launchctl list | grep com.atlas.script-name
```

**View logs:**
```bash
tail -f ~/atlas/logs/script.log
```

## Common Mistakes

### ❌ Wrong: Using envchain in cron
```bash
# This will fail - cron can't access Keychain
0 6 * * * envchain atlas python3 tools/briefings/daily_brief.py
```

### ✅ Right: Using envchain in launchd
```xml
<key>ProgramArguments</key>
<array>
  <string>/opt/homebrew/bin/envchain</string>
  <string>atlas</string>
  <string>/opt/homebrew/bin/python3</string>
  <string>/Users/printer/atlas/tools/briefings/daily_brief.py</string>
</array>
```

### ❌ Wrong: Credentials stored in cron
```bash
# Insecure - credentials exposed in cron file
0 6 * * * TOKEN=abc123 python3 tools/briefings/daily_brief.py
```

### ✅ Right: Credentials from .env or envchain
```bash
# Cron (using .env file)
0 6 * * * python3 tools/briefings/daily_brief.py

# OR launchd (using envchain)
# See plist template above
```

## Credential Loading Pattern

**In your Python script:**
```python
from tools.common.credentials import get_telegram_token

# This function:
# 1. Tries envchain first (works in launchd)
# 2. Falls back to .env (works in cron)
token = get_telegram_token()
```

**Never write custom credential loading** - always import from `tools/common/credentials.py`

## Troubleshooting

**Launchd agent not running:**
```bash
# Check if loaded
launchctl list | grep com.atlas.script-name

# Check logs
tail -f ~/atlas/logs/script.error.log

# Test manually
launchctl start com.atlas.script-name
```

**Cron job not running:**
```bash
# Check cron is running
ps aux | grep cron

# View cron logs
tail -f /var/log/cron.log  # (if available)

# Test script manually
python3 /Users/printer/atlas/tools/category/script.py
```

**envchain not working:**
```bash
# Test envchain access
envchain atlas env | grep TELEGRAM_BOT_TOKEN

# If empty, credential not set
envchain --set atlas TELEGRAM_BOT_TOKEN
```

## Quick Reference

| Feature | Cron | Launchd |
|---------|------|---------|
| Keychain access | ❌ | ✅ |
| envchain support | ❌ | ✅ |
| .env file support | ✅ | ✅ |
| Complex schedules | Limited | Advanced |
| Auto-restart on failure | ❌ | ✅ |
| Load on login | ❌ | ✅ |
| Easy syntax | ✅ | ❌ (XML) |
| Logging built-in | ❌ | ✅ |

## Migration Guide: Cron → Launchd

1. **Identify the cron job:**
   ```bash
   crontab -l | grep script_name
   ```

2. **Create launchd plist** (use template above)

3. **Load the plist:**
   ```bash
   launchctl load ~/Library/LaunchAgents/com.atlas.script-name.plist
   ```

4. **Test:**
   ```bash
   launchctl start com.atlas.script-name
   tail -f ~/atlas/logs/script.log
   ```

5. **Remove from cron:**
   ```bash
   crontab -e
   # Delete the line, save
   ```

6. **Verify launchd running:**
   ```bash
   launchctl list | grep com.atlas.script-name
   ```
