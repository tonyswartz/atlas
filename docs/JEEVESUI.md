# JeevesUI (Bambu / filament)

Atlas Bambu tools (watcher, prompt poller, reply handler, import_spoolman, update_spool_prices) talk to **JeevesUI** for spool inventory and print-job logging.

- **Where it runs:** JeevesUI lives in the **clawd** repo and is not part of Atlas. Start it from clawd so it is always available:
  - `launchctl start com.jeeves-ui` (if using the LaunchAgent)
  - Or: `cd /Users/printer/clawd/JeevesUI && npm run start` (or `npm run dev`)
- **Port:** All Atlas Bambu tools use **`http://localhost:6001`**. JeevesUI must be listening on **6001**. In clawd, `JeevesUI/package.json` is already set to port 6001 (`next dev -p 6001` and `next start -p 6001`), so no config change is needed as long as you start it from clawd.
- **APIs used:** `/api/filament/spools`, `/api/filament/print-jobs`

If JeevesUI is not running, Bambu prompt poller and reply handler will fail to fetch spools or log jobs.
