# Scheduled jobs (crontab)

Atlas runs Bambu watcher and Kanban runner on a schedule. Point your crontab at the Atlas wrappers so these jobs run from Atlas (logs go to `atlas/logs/`).

## Crontab entries

Run `crontab -e` and add these lines (merge with any existing entries you have):

```
*/5 * * * * /bin/bash /Users/printer/atlas/tools/bambu/bambu_watcher_wrapper.sh >> /Users/printer/atlas/logs/bambu_watcher.log 2>&1
*/30 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/bambu/bambu_watcher_health.py >> /Users/printer/atlas/logs/bambu_watcher_health.log 2>&1
*/15 * * * * /bin/bash /Users/printer/atlas/tools/tasks/kanban_runner_wrapper.sh >> /Users/printer/atlas/logs/kanban_runner.log 2>&1
0 6 * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/briefings/daily_brief.py >> /Users/printer/atlas/logs/daily_brief.log 2>&1
0 9 * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/legal/wa_dui_bill_tracker.py >> /Users/printer/atlas/logs/wa_dui_bill_tracker.log 2>&1
0 12 * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/briefings/local_news.py >> /Users/printer/atlas/logs/local_news.log 2>&1
0 15 * * * /opt/homebrew/bin/python3 /Users/printer/atlas/tools/briefings/research_brief.py >> /Users/printer/atlas/logs/research_brief.log 2>&1
```

- **Bambu:** Every 5 minutes — checks for print completion, sends spool prompts if needed.
- **Bambu health:** Every 30 minutes — if watcher state hasn’t updated in 20+ min, sends Telegram alert (throttled to once per 2 h).
- **Kanban:** Every 15 minutes — polls Obsidian Kanban and runs approved tasks.
- **Daily brief:** 6:00 — runs daily briefing.
- **WA DUI Bill Tracker:** 9:00 — checks tracked bills, sends update to Telegram.
- **Local news:** 12:00 (noon) — Ellensburg / Yakima / Seattle news, sent via Telegram and logged to Obsidian.
- **Research brief:** 15:00 (3pm) — tech + Kraken news from Google RSS, sent via Telegram.

Both wrappers use `flock` so only one instance runs at a time. Clawd scripts can still be run by hand; these entries use only the Atlas wrappers.
