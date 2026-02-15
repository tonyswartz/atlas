# Using envchain with Apple Keychain (instead of .env)

Atlas can load secrets from **envchain** (Apple Keychain) instead of a plain `.env` file. This keeps credentials out of the repo and off disk.

## Install envchain

```bash
brew install envchain
```

## One-time: migrate from .env to Keychain

1. Create the `atlas` namespace and set every variable. You’ll be prompted for each value (paste from your current `.env`):

   ```bash
   cd /Users/printer/atlas
   envchain --set atlas \
     TELEGRAM_BOT_TOKEN \
     MCP \
     BRAVE_API_KEY \
     TELEGRAM_ID \
     MINIMAX \
     MINIMAX_GROUP_ID \
     MINDSETLOG_DB_HOST \
     MINDSETLOG_DB_PORT \
     MINDSETLOG_DB_NAME \
     MINDSETLOG_DB_USER \
     MINDSETLOG_DB_PASSWORD \
     MINDSETLOG_EMAIL \
     MINDSETLOG_DB_URL
   ```

   For sensitive values, use `--noecho` so they don’t echo as you type:

   ```bash
   envchain --set --noecho atlas TELEGRAM_BOT_TOKEN MINDSETLOG_DB_PASSWORD MINDSETLOG_DB_URL
   envchain --set atlas MCP BRAVE_API_KEY TELEGRAM_ID MINIMAX MINIMAX_GROUP_ID MINDSETLOG_DB_HOST MINDSETLOG_DB_PORT MINDSETLOG_DB_NAME MINDSETLOG_DB_USER MINDSETLOG_EMAIL
   ```

2. Optional vars (set if you use them): `OPENAI_API_KEY`, `HELICONE_API_KEY`, `OPENROUTER_API_KEY`, `MINDSETLOG_URL`, `MINDSETLOG_PASSWORD`, `BROWSER_SERVER_PORT`, `TELEGRAM_CHAT_ID`.

3. After everything is in Keychain, remove or rename your `.env`:

   ```bash
   mv .env .env.bak
   ```

## Running tools with envchain

Run any command with the `atlas` namespace so it gets the Keychain env vars:

```bash
envchain atlas python tools/telegram/bot.py
envchain atlas python tools/briefings/daily_brief.py
envchain atlas python tools/research/web_search.py --query "something"
```

Or use the helper script (from repo root):

```bash
./scripts/run_with_envchain.sh python tools/telegram/bot.py
./scripts/run_with_envchain.sh bash -c "python tools/whatever.py"
```

For a one-off script:

```bash
envchain atlas bash -c "python tools/whatever.py"
```

## Cron and background jobs

Cron does not run under your login session, so Keychain may be locked and envchain may prompt or fail. Options:

1. **Unlock Keychain before cron** (e.g. in a wrapper that runs at login or before the job):
   ```bash
   security unlock-keychain -p "your-keychain-password" login.keychain-db
   ```
   Then run the job with `envchain atlas python ...`.

2. **Keep a minimal .env only for cron**  
   Use envchain for interactive use and keep a restricted `.env` (permissions `600`) that only cron reads, with only the vars those jobs need. Do not commit `.env`.

3. **Run cron under your user with keychain available**  
   If the cron job runs in a context where the user is logged in and the default keychain is unlocked, `envchain atlas ...` can work without extra steps.

Update your cron entries to use envchain where appropriate, for example:

```cron
0 8 * * * envchain atlas /usr/bin/python3 /Users/printer/atlas/tools/briefings/daily_brief.py
```

## Adding or changing a variable

- **Add a new secret:**  
  `envchain --set atlas NEW_VAR_NAME`  
  (or `envchain --set --noecho atlas NEW_VAR_NAME` for passwords.)

- **Change a value:**  
  Run `envchain --set atlas EXISTING_VAR_NAME` again and enter the new value.

- **List namespaces:**  
  `envchain --list`  
  (You should see `atlas`.)

## How Atlas uses this

- Scripts use `os.environ.get("VAR_NAME", ...)`. When you run under `envchain atlas`, those vars are already in the environment.
- Any `load_dotenv(.env)` calls only fill in vars that are **not** already set, so Keychain (envchain) wins when you use it.
- A few tools also read from `.env` if the var is missing from the environment, so both envchain-only and .env-only setups work.

## Test that everything works

From repo root (with envchain installed and `atlas` namespace populated):

```bash
envchain atlas python scripts/test_envchain.py
```

This checks all required vars and runs a quick Brave Search + Telegram token format check. Exit 0 = OK.

## Reference: variable list

See `.env.example` in the repo root for the full list of variable names (no values). Use that list with `envchain --set atlas VAR1 VAR2 ...` when migrating or adding vars.
