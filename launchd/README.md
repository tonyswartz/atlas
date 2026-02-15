# Atlas launchd jobs (replaces crontab)

These run in your **user session**, so Apple Keychain (and `envchain atlas`) is available. No need to keep a `.env` for cron.

## Install

From repo root:

```bash
./launchd/install-launchd.sh
```

This copies plists to `~/Library/LaunchAgents/` and loads them. Logs go to `atlas/logs/`.

## Jobs

| Label | Schedule | Description |
|-------|----------|-------------|
| com.atlas.bambu-watcher | Every 5 min | Bambu print completion + spool prompts |
| com.atlas.bambu-watcher-health | Every 30 min | Health check; Telegram alert if watcher stale |
| com.atlas.daily-brief | 6:00 | Daily briefing |
| com.atlas.wa-dui-bill-tracker | 9:00 | WA DUI bill tracker |
| com.atlas.local-news | 12:00 | Local news brief |
| com.atlas.research-brief | 15:00 | Research brief |
| com.atlas.rotary-print-agenda | Tue 16:00 | Print Rotary agenda (if completed) to Brother MFC-L3780CDW; Telegram when done |
| com.atlas.watchdog | 6:05 | Scans logs for errors, Telegram alert |

**Kanban runner** is not in Atlas (lives in clawd); keep that in crontab or add a separate launchd plist there.

## Uninstall

```bash
./launchd/install-launchd.sh --unload
```

Then remove plists from `~/Library/LaunchAgents/` if desired.

## Requirements

- `envchain` with namespace `atlas` populated (see `docs/ENVCHAIN.md`)
- Paths in plists use `/Users/printer/atlas` and `/opt/homebrew/bin`; edit plists if your paths differ
