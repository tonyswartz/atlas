# Run Atlas at login

To have the Atlas Telegram bot start when you log in (and restart if it exits), install the LaunchAgent.

## One-time setup

1. Copy the plist to LaunchAgents:
   ```bash
   cp /Users/printer/atlas/com.atlas.telegram-bot.plist ~/Library/LaunchAgents/
   ```

2. Load it. On **macOS Ventura / Sonoma and later**, use `bootstrap` (not `load`). If you previously loaded with `load`, unload first:
   ```bash
   # If you get "Load failed: 5" or job already loaded, unload first:
   launchctl bootout gui/$(id -u) com.atlas.telegram-bot 2>/dev/null || true
   # Then load (modern macOS):
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.atlas.telegram-bot.plist
   ```
   On **older macOS**, you can use:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.atlas.telegram-bot.plist
   ```

After this, the bot will start at login and keep running (KeepAlive). Logs go to `~/Library/Logs/telegram-bot.log` and `~/Library/Logs/telegram-bot.err.log`.

## Optional: install script

From the Atlas repo root you can run:
```bash
./scripts/install-launchagent.sh
```
This copies the plist and runs the bootstrap steps for you.

## Useful commands

- Start now: `launchctl start com.atlas.telegram-bot`
- Stop: `launchctl stop com.atlas.telegram-bot`
- Unload (disable at login): `launchctl bootout gui/$(id -u) com.atlas.telegram-bot` (or on older macOS: `launchctl unload ~/Library/LaunchAgents/com.atlas.telegram-bot.plist`)

## If you get "Load failed: 5" or "Bootstrap failed: 5"

This usually means the job is already loaded or launchd is in a bad state. Try in order:

1. **Unload first, then load again** — In **Terminal.app** (not Cursor’s terminal), run:
   ```bash
   launchctl bootout gui/$(id -u) com.atlas.telegram-bot
   cp /Users/printer/atlas/com.atlas.telegram-bot.plist ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.atlas.telegram-bot.plist
   ```

2. **Clear extended attributes** on the plist (can cause I/O errors):
   ```bash
   xattr -c ~/Library/LaunchAgents/com.atlas.telegram-bot.plist
   ```
   Then run the bootout/bootstrap steps again.

3. **See the real error** (run in Terminal.app):
   ```bash
   sudo launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.atlas.telegram-bot.plist
   ```
   The message after sudo will often explain the failure (e.g. path or permission).

4. **Run the bot without LaunchAgent** — To keep it running in the background from a terminal:
   ```bash
   cd /Users/printer/atlas && /opt/homebrew/bin/python3 tools/telegram/bot.py
   ```
   Use `tmux` or `screen` if you want it to survive closing the window.
