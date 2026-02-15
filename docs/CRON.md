# Scheduled jobs (launchd or crontab)

**Preferred: launchd** — Runs in your user session so **envchain** (Apple Keychain) works. No `.env` needed for scheduled jobs.

## launchd (recommended)

From repo root:

```bash
./launchd/install-launchd.sh
```

See `launchd/README.md` for job list and uninstall. Logs go to `atlas/logs/`.

---

## Crontab (legacy)

If you use crontab instead, run jobs with **envchain** so Keychain vars are available:

```bash
crontab -e
```

Add (merge with existing entries):

```
*/5 * * * * /opt/homebrew/bin/envchain atlas /bin/bash /Users/printer/atlas/tools/bambu/bambu_watcher_wrapper.sh >> /Users/printer/atlas/logs/bambu_watcher.log 2>&1
*/30 * * * * /opt/homebrew/bin/envchain atlas /opt/homebrew/bin/python3 /Users/printer/atlas/tools/bambu/bambu_watcher_health.py >> /Users/printer/atlas/logs/bambu_watcher_health.log 2>&1
0 6 * * * /opt/homebrew/bin/envchain atlas /opt/homebrew/bin/python3 /Users/printer/atlas/tools/briefings/daily_brief.py >> /Users/printer/atlas/logs/daily_brief.log 2>&1
0 9 * * * /opt/homebrew/bin/envchain atlas /opt/homebrew/bin/python3 /Users/printer/atlas/tools/legal/wa_dui_bill_tracker.py >> /Users/printer/atlas/logs/wa_dui_bill_tracker.log 2>&1
0 12 * * * /opt/homebrew/bin/envchain atlas /opt/homebrew/bin/python3 /Users/printer/atlas/tools/briefings/local_news.py >> /Users/printer/atlas/logs/local_news.log 2>&1
0 15 * * * /opt/homebrew/bin/envchain atlas /opt/homebrew/bin/python3 /Users/printer/atlas/tools/briefings/research_brief.py >> /Users/printer/atlas/logs/research_brief.log 2>&1
```

- **Bambu:** Every 5 min — print completion, spool prompts.
- **Bambu health:** Every 30 min — Telegram alert if watcher stale.
- **Daily brief:** 6:00
- **WA DUI Bill Tracker:** 9:00
- **Local news:** 12:00
- **Research brief:** 15:00

- **Rotary agenda print:** Tuesday 16:00 via launchd only (see `launchd/README.md`). Prints this week's agenda to Brother MFC-L3780CDW if the agenda file exists and is completed; sends Telegram when done. Cron equivalent: `0 16 * * 2 envchain atlas python3 .../tools/rotary/print_agenda.py >> .../logs/rotary_print_agenda.log 2>&1`
  - **Printer:** Set `ROTARY_PRINTER` in envchain if your CUPS queue name differs (default: `Brother_MFC_L3780CDW_series`; check `lpstat -p`). Check with `lpstat -p`.
  - **One page:** Script uses pandoc with small margins (0.35in) and 8pt font. If the agenda still spills to two pages, edit `tools/rotary/print_agenda.py` and reduce `geometry` or `fontsize` in `markdown_to_pdf()`.
  - **Requires:** `pandoc` (and a PDF engine, e.g. `brew install pandoc basictex` or `wkhtmltopdf`).

**Kanban runner** is not in Atlas (in clawd); add that to crontab separately if needed. **Watchdog** (post-cron error scanner) is included in launchd at 6:05; for crontab add: `5 6 * * * ... watchdog.py`.
