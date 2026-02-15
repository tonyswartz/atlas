# Atlas setup checklist

Use this to get Atlas fully functional. Do these in order.

---

## 1. Environment and dependencies

- **Python 3** — Atlas scripts assume `python3` on PATH. Use 3.10+.
- **Secrets** — Either **.env** in the repo root or **envchain** (Apple Keychain; see `docs/ENVCHAIN.md`). Required: `TELEGRAM_BOT_TOKEN` from [@BotFather](https://t.me/BotFather). Optional: `OPENAI_API_KEY` for semantic/hybrid memory and OpenAI-using tools.
- **Install Python deps:** From repo root:
  ```bash
  pip install -r requirements.txt
  ```

---

## 2. Ollama (for the Telegram bot)

The bot uses **Ollama** on `localhost:11434` as the LLM. The default model in `args/telegram.yaml` is `qwen2.5:7b`.

- Install [Ollama](https://ollama.com) if needed.
- Start Ollama (usually runs as a service; if not: `ollama serve`).
- Pull the model:
  ```bash
  ollama pull qwen2.5:7b
  ```
- To use a different model, edit `args/telegram.yaml` → `model.name`.

---

## 3. Telegram bot access (recommended)

- **Restrict who can use the bot:** In `args/telegram.yaml`, set `allowed_user_ids` to your Telegram user ID (and any other trusted IDs). Empty list = anyone can message the bot. See [docs/SECURITY.md](SECURITY.md).
- Get your user ID: message the bot and check `~/Library/Logs/telegram-bot.log`, or use [@userinfobot](https://t.me/userinfobot).
  ```yaml
  bot:
    allowed_user_ids: [8241581699]   # your ID
  ```

---

## 4. Run the bot at login

So the Telegram bot is always available:

- **Option A — script:** From Atlas repo root:
  ```bash
  ./scripts/install-launchagent.sh
  ```
- **Option B — manual:** See [docs/STARTUP.md](STARTUP.md) (copy plist to `~/Library/LaunchAgents/`, then `launchctl load`).

After this, the bot starts at login. Logs: `~/Library/Logs/telegram-bot.log` and `telegram-bot.err.log`.

---

## 5. Scheduled jobs (Bambu + Kanban)

To run scheduled jobs (Bambu, briefings, etc.):

- **Preferred:** launchd (works with envchain): `./launchd/install-launchd.sh` — see [docs/CRON.md](CRON.md) and `launchd/README.md`.
- **Or** run `crontab -e` and add the envchain-wrapped lines from [docs/CRON.md](CRON.md).

If you skip this, you can still run the scripts by hand when needed.

---

## 6. JeevesUI (only if you use Bambu tools)

Bambu watcher/poller/reply-handler need **JeevesUI** for spool list and print-job logging. JeevesUI lives in the **clawd** repo.

- Start JeevesUI so it listens on **port 6001**:
  - `launchctl start com.jeeves-ui` (if you use its LaunchAgent), or
  - `cd /Users/printer/clawd/JeevesUI && npm run start`
- See [docs/JEEVESUI.md](JEEVESUI.md). If you don’t use 3D printing/Bambu, you can skip this.

---

## 7. Bambu / Kanban (optional, only if you use them)

- **Bambu:** Bambu tools read credentials from clawd: `/Users/printer/clawd/secrets/bambu.env` and write the token to `clawd/secrets/bambu_token.json`. Run `python3 tools/bambu/bambu_login.py` once to log in (from Atlas root, or ensure clawd paths exist).
- **Kanban:** Uses Obsidian Kanban note and `clawdbot` CLI for some steps. The Kanban note path and tasks path are in `tools/tasks/kanban_runner.py` (Dropbox/Obsidian and clawd by default). No extra setup if those paths already exist.

---

## Quick verification

1. **Bot:** Send a message to your Telegram bot. You should get a reply (and see logs in `~/Library/Logs/telegram-bot.log`).
2. **Ollama:** `curl http://localhost:11434/api/tags` — should list models including `qwen2.5:7b`.
3. **Cron:** After adding crontab, check `atlas/logs/bambu_watcher.log` and `kanban_runner.log` after 5–15 minutes for new entries.
4. **JeevesUI:** If you use Bambu, `curl http://localhost:6001/api/filament/spools` should return JSON (or 401 if auth is on).

---

## Summary table

| Item | Required? | Where |
|------|-----------|--------|
| TELEGRAM_BOT_TOKEN in .env | Yes (for bot) | `.env` |
| Ollama installed + model pulled | Yes (for bot) | System |
| allowed_user_ids | Recommended | `args/telegram.yaml` |
| LaunchAgent (run at login) | Recommended | `./scripts/install-launchagent.sh` or [STARTUP.md](STARTUP.md) |
| Crontab (Bambu + Kanban) | Optional | [CRON.md](CRON.md) |
| JeevesUI on 6001 | Only for Bambu | clawd repo |
| Bambu login / secrets | Only for Bambu | clawd `secrets/` |
