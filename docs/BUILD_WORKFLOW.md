# /build — Conversational Script Builder

The `/build` command enables you to create custom Python scripts and schedule them automatically through a conversational interface with the Telegram bot — no need to open an IDE.

## Quick Start

```
You: /build I need a script that checks my calendar every morning at 7am and texts me today's events

Bot: I'll help you build that script. Let me clarify a few things:

     1. Which calendar should I check?
     2. What exactly should be included in the text?
     3. Should it include all-day events?
     ...
```

The bot will:
1. Ask clarifying questions
2. Generate the Python code
3. Show you the code for review
4. Save it when you approve
5. Schedule it with launchd if you want

## How It Works

### Architecture

```
/build command
    ↓
BUILD_DIRECTIVE (commands.py)
    ↓
Conversation with user
    ↓
script_writer tool → generates/saves Python code
    ↓
launchd_manager tool → creates .plist and schedules
    ↓
Script runs automatically on schedule
```

### Components

**1. `/build` Command** (`tools/telegram/commands.py`)
- Triggers BUILD_DIRECTIVE
- Guides LLM through script creation workflow
- Provides patterns and best practices

**2. `script_writer` Tool** (`tools/system/script_writer.py`)
- Generates Python script templates based on task classification
- Validates Python syntax
- Saves scripts to `tools/scripts/` directory
- Makes scripts executable (chmod 755)

**3. `launchd_manager` Tool** (`tools/system/launchd_manager.py`)
- Creates launchd `.plist` files
- Parses human-readable schedules
- Loads jobs into launchd
- Lists/manages existing jobs

**4. Tool Definitions** (`tools/telegram/tool_definitions.py`)
- OpenAI-compatible tool schemas
- Defines parameters for script_writer and launchd_manager
- Used by LLM to call tools correctly

**5. Tool Runner** (`tools/telegram/tool_runner.py`)
- Routes tool calls to Python scripts
- Parses JSON results
- Handles errors gracefully

## Workflow Example

### User: "I want to monitor my printer and get a text when it finishes"

**Step 1: Clarification**
```
Bot: I can build that for you! A few questions:

     1. How should I check the printer status? (FTP, API, local command?)
     2. How often should I check? (every minute, every 5 minutes?)
     3. Should I only notify once per job, or every check?
```

**Step 2: Code Generation**
```
Bot: Here's the script I'll create:

     ```python
     #!/usr/bin/env python3
     """
     Monitor Bambu printer and send Telegram notification on completion
     """

     import json
     import os
     import sys
     import urllib.request
     from pathlib import Path

     REPO_ROOT = Path(__file__).parent.parent.parent
     STATE_FILE = REPO_ROOT / "data" / "printer_monitor_state.json"

     def get_printer_status():
         # Check printer via bambu-cli
         result = subprocess.run(["/opt/homebrew/bin/bambu-cli", "--json", "status"],
                               capture_output=True, text=True)
         return json.loads(result.stdout)

     def send_telegram(text: str):
         token = os.environ.get("TELEGRAM_BOT_TOKEN")
         # ... (implementation)

     def main():
         status = get_printer_status()
         state = load_state()

         if status["gcode_state"] == "FINISH" and state.get("last_state") == "RUNNING":
             send_telegram("🎉 Print completed!")

         save_state({"last_state": status["gcode_state"]})

     if __name__ == "__main__":
         main()
     ```

     This script:
     - Checks printer status via bambu-cli
     - Saves state to data/printer_monitor_state.json
     - Only sends notification on status change (RUNNING → FINISH)
     - Requires TELEGRAM_BOT_TOKEN from envchain

     Look good?
```

**Step 3: User Approval**
```
User: Yes, looks great

Bot: ✅ Saving script...
```

**Step 4: Scheduling**
```
Bot: Script saved to tools/scripts/printer_monitor.py

     Would you like to schedule it to run automatically?

User: Yes, check every 2 minutes

Bot: Creating launchd job...

     ✅ Script created: tools/scripts/printer_monitor.py
     ✅ Scheduled: every 2 minutes via launchd
     📋 Logs: logs/com.atlas.printer-monitor.log

     To test manually: /run printer_monitor
     To check status: launchctl list | grep atlas
     To stop: launchctl unload ~/Library/LaunchAgents/com.atlas.printer-monitor.plist
```

## Script Templates

The `script_writer` generates templates based on task classification:

### 1. Telegram Notifier
For tasks involving sending Telegram messages.

**Triggers**: "telegram", "notify", "send message", "alert"

**Includes**:
- `send_telegram()` function with retry logic
- Timezone handling (Pacific time)
- Error handling and logging

### 2. Web Scraper
For tasks involving fetching web pages.

**Triggers**: "scrape", "fetch", "download", "web page"

**Includes**:
- `fetch_page()` with user-agent headers
- Timeout handling
- Error handling

### 3. File Processor
For tasks processing files.

**Triggers**: "process file", "read file", "parse", "csv", "json"

**Includes**:
- File existence checks
- Encoding handling (UTF-8)
- Argparse for CLI args

### 4. API Poller
For tasks checking APIs periodically.

**Triggers**: "poll", "check api", "monitor", "watch"

**Includes**:
- State persistence (JSON file)
- Timestamp tracking
- Change detection logic

### 5. Generic
Fallback template for other tasks.

**Includes**:
- Basic structure
- REPO_ROOT reference
- Shebang and docstring

## Scheduling Options

`launchd_manager` parses human-readable schedules:

| Schedule String | Meaning | launchd Equivalent |
|----------------|---------|-------------------|
| `"every 5 minutes"` | Every 5 minutes | `StartInterval` 300 seconds |
| `"every hour"` | Every hour | `StartInterval` 3600 seconds |
| `"daily at 9am"` | Every day at 9:00 AM | `StartCalendarInterval` Hour=9, Minute=0 |
| `"every weekday at 5pm"` | Mon-Fri at 5:00 PM | `StartCalendarInterval` (5 entries) |

### Schedule Parsing Examples

```python
parse_schedule("every 5 minutes")
# → {"type": "interval", "seconds": 300}

parse_schedule("daily at 9:30am")
# → {"type": "calendar", "intervals": {"Hour": 9, "Minute": 30}}

parse_schedule("every weekday at 5pm")
# → {"type": "calendar", "intervals": [
#      {"Weekday": 1, "Hour": 17, "Minute": 0},  # Monday
#      {"Weekday": 2, "Hour": 17, "Minute": 0},  # Tuesday
#      ...
#    ]}
```

## Launchd Integration

### Plist Structure

Generated plists include:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.atlas.my-script</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/envchain</string>
        <string>atlas</string>
        <string>/opt/homebrew/bin/python3</string>
        <string>/Users/printer/atlas/tools/scripts/my_script.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/printer/atlas</string>

    <key>StandardOutPath</key>
    <string>/Users/printer/atlas/logs/com.atlas.my-script.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/printer/atlas/logs/com.atlas.my-script.error.log</string>

    <key>StartInterval</key>
    <integer>300</integer>  <!-- 5 minutes -->

    <!-- or -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
```

### Why envchain?

Scripts run with `envchain atlas` to access:
- `TELEGRAM_BOT_TOKEN`
- `LEGALKANBAN` (database URL)
- Other credentials in macOS Keychain

This is more secure than storing credentials in `.env` files.

### Launchd vs Cron

**Use launchd (via /build) when:**
- Script needs Keychain access (OAuth tokens, API keys via envchain)
- You want automatic retry on failure
- You need more complex scheduling (e.g., "weekdays only")

**Use cron when:**
- Script doesn't need credentials
- Simple time-based schedules
- Legacy compatibility

## File Locations

### Scripts
- **Saved to**: `tools/scripts/<name>.py`
- **Permissions**: 755 (executable)
- **Naming**: Automatically adds `.py` if omitted

### Launchd Plists
- **Saved to**: `~/Library/LaunchAgents/com.atlas.<name>.plist`
- **Naming**: Auto-prefixed with `com.atlas.`
- **Format**: Standard Apple PropertyList XML

### Logs
- **Standard output**: `logs/com.atlas.<name>.log`
- **Error output**: `logs/com.atlas.<name>.error.log`
- **Location**: Relative to repo root

## Safety Features

### Path Protection
- All file writes are path-validated
- Must be within `tools/scripts/` directory
- No directory traversal allowed (`../` blocked)

### Syntax Validation
- Python code is compiled before saving
- SyntaxError caught and reported with line number
- Prevents saving broken scripts

### Approval Gates
- Bot shows code before saving
- User must explicitly approve
- No automatic execution without confirmation

### Script Isolation
- Each script runs in its own process
- Errors don't affect other scripts
- Logs captured separately per script

## Common Patterns

### 1. Telegram Notifications
```python
from common.credentials import get_telegram_token

def send_telegram(text: str) -> bool:
    token = get_telegram_token()
    # ... (implementation from daily_brief.py)
```

### 2. State Persistence
```python
STATE_FILE = REPO_ROOT / "data" / "my_script_state.json"

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))
```

### 3. Credential Access
```python
import sys
from pathlib import Path

# Add common to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "common"))

from credentials import get_telegram_token

token = get_telegram_token()
```

## Management Commands

### Via Telegram

**Test a script manually:**
```
/run <script_name>
```

**Check running jobs:**
```
(via Telegram chat, the bot can't execute shell commands directly,
but you can ask it to check logs)
```

### Via Terminal

**List all atlas jobs:**
```bash
launchctl list | grep com.atlas
```

**Check job status:**
```bash
launchctl list com.atlas.my-script
```

**View logs:**
```bash
tail -f logs/com.atlas.my-script.log
tail -f logs/com.atlas.my-script.error.log
```

**Stop a job:**
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.my-script.plist
```

**Start a job:**
```bash
launchctl load ~/Library/LaunchAgents/com.atlas.my-script.plist
```

**Restart a job:**
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.my-script.plist
launchctl load ~/Library/LaunchAgents/com.atlas.my-script.plist
```

## Troubleshooting

### Script not running on schedule

**Check if job is loaded:**
```bash
launchctl list | grep com.atlas.my-script
```

**Check logs for errors:**
```bash
tail -20 logs/com.atlas.my-script.error.log
```

**Verify plist syntax:**
```bash
plutil ~/Library/LaunchAgents/com.atlas.my-script.plist
```

### Permission errors

**Ensure script is executable:**
```bash
chmod +x tools/scripts/my_script.py
```

**Check plist permissions:**
```bash
ls -la ~/Library/LaunchAgents/com.atlas.my-script.plist
```

### Credentials not accessible

**Verify envchain namespace:**
```bash
envchain atlas env | grep TELEGRAM
```

**Check if script uses envchain:**
- Plist should have `envchain` in `ProgramArguments`
- Script should import from `common.credentials`

### Script works manually but not via launchd

**Common causes:**
1. Missing PATH environment variables
2. Hardcoded paths that don't exist
3. Keychain access (use envchain)
4. Working directory issues (plist sets it to repo root)

**Debug:**
```bash
# Add debug logging to script
print(f"Running from: {os.getcwd()}", file=sys.stderr)
print(f"REPO_ROOT: {REPO_ROOT}", file=sys.stderr)

# Check error log
tail -f logs/com.atlas.my-script.error.log
```

## Best Practices

### 1. Use State Files for Stateful Scripts
Always save state to `data/` directory:
```python
STATE_FILE = REPO_ROOT / "data" / "my_script_state.json"
```

### 2. Always Handle Errors Gracefully
```python
try:
    # Do work
    result = do_something()
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
```

### 3. Use Timeouts for External Calls
```python
result = subprocess.run(cmd, timeout=30)
response = urllib.request.urlopen(url, timeout=10)
```

### 4. Log Important Events
```python
print(f"Processed {count} items")
print(f"State saved to {STATE_FILE}")
```

### 5. Test Before Scheduling
```bash
# Test manually first
python tools/scripts/my_script.py

# Then schedule
```

### 6. Keep Scripts Focused
- One script, one job
- Don't combine unrelated tasks
- Easier to debug and maintain

### 7. Use Descriptive Names
- Good: `calendar_morning_brief.py`
- Bad: `script1.py`, `test.py`

## Examples

### Example 1: Daily Weather Alert

**User request:**
```
/build Send me the weather every morning at 6am
```

**Generated script** (`tools/scripts/weather_alert.py`):
```python
#!/usr/bin/env python3
"""Daily weather alert via Telegram"""

import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "common"))

from credentials import get_telegram_token

def get_weather():
    # Open-Meteo API (free, no key needed)
    url = "https://api.open-meteo.com/v1/forecast?latitude=46.9965&longitude=-120.5478&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=America/Los_Angeles&forecast_days=1"
    resp = urllib.request.urlopen(url, timeout=10)
    return json.loads(resp.read())

def send_telegram(text: str):
    token = get_telegram_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": "8241581699", "text": text})
    req = urllib.request.Request(url, data=payload.encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)

def main():
    weather = get_weather()
    daily = weather["daily"]

    high = daily["temperature_2m_max"][0]
    low = daily["temperature_2m_min"][0]
    precip = daily["precipitation_sum"][0]

    message = f"☀️ Today's Weather\n\nHigh: {high}°C\nLow: {low}°C\nPrecip: {precip}mm"

    send_telegram(message)
    print("Weather alert sent")

if __name__ == "__main__":
    main()
```

**Schedule**: `daily at 6am`

**Launchd job**: `com.atlas.weather-alert`

### Example 2: Website Change Monitor

**User request:**
```
/build Check my law firm website every hour and notify me if it changes
```

**Generated script** (`tools/scripts/website_monitor.py`):
```python
#!/usr/bin/env python3
"""Monitor law firm website for changes"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
STATE_FILE = REPO_ROOT / "data" / "website_monitor_state.json"

sys.path.insert(0, str(REPO_ROOT / "tools" / "common"))
from credentials import get_telegram_token

def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    return resp.read().decode("utf-8")

def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())

def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def send_telegram(text: str):
    token = get_telegram_token()
    # ... (implementation)

def main():
    url = "https://yourlawfirm.com"
    content = fetch_page(url)
    current_hash = compute_hash(content)

    state = load_state()
    last_hash = state.get("last_hash")

    if last_hash and last_hash != current_hash:
        send_telegram(f"🚨 Website changed!\n{url}")

    save_state({"last_hash": current_hash, "url": url})
    print(f"Checked {url} - hash: {current_hash[:8]}...")

if __name__ == "__main__":
    main()
```

**Schedule**: `every hour`

**Launchd job**: `com.atlas.website-monitor`

## Future Enhancements

Potential improvements to the `/build` system:

1. **LLM-generated code** (currently uses templates)
   - Call Claude API to generate custom logic
   - Better handling of complex requirements

2. **Script versioning**
   - Keep history of script changes
   - Ability to rollback to previous version

3. **Testing framework**
   - Auto-generate unit tests
   - Dry-run mode before scheduling

4. **Script discovery**
   - `/scripts` command to list all user scripts
   - `/edit <script>` to modify existing scripts

5. **Dependency management**
   - Auto-detect required packages
   - Install via pip in virtual env

6. **Error notifications**
   - Auto-alert on script failures
   - Retry logic configuration

7. **Web dashboard**
   - View all scheduled scripts
   - Start/stop/edit from web UI
   - View logs in real-time

## Related Documentation

- [TELEGRAM_BOT_SAFEGUARDS.md](TELEGRAM_BOT_SAFEGUARDS.md) - Bot safety mechanisms
- [CREDENTIAL_LOADING.md](CREDENTIAL_LOADING.md) - Envchain and credential access
- [CRON_TO_LAUNCHD_MIGRATION.md](CRON_TO_LAUNCHD_MIGRATION.md) - Why we use launchd
- [ENVCHAIN.md](ENVCHAIN.md) - Keychain-based credential management

## Tool Reference

### script_writer Tool

**Actions**:
- `generate`: Create script template from description
- `save`: Save code to file
- `validate`: Check Python syntax

**Parameters**:
```json
{
  "action": "generate|save|validate",
  "description": "What the script should do",
  "code": "Python code to save",
  "filename": "script_name.py",
  "imports": ["import requests", "from pathlib import Path"],
  "use_envchain": true
}
```

### launchd_manager Tool

**Actions**:
- `create`: Generate launchd plist
- `load`: Start a job
- `unload`: Stop a job
- `list`: Show all atlas jobs

**Parameters**:
```json
{
  "action": "create|load|unload|list",
  "script_path": "tools/scripts/my_script.py",
  "label": "my-script",
  "schedule": "daily at 9am",
  "run_at_load": false,
  "description": "Human-readable description"
}
```

---

**Last updated**: 2026-02-15
