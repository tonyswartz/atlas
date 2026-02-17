# No Secrets in Tracked Files

**Rule:** API keys, tokens, passwords, and other secrets must **never** appear in any file that is committed to the repo.

## Where Secrets Live

| Location | Purpose |
|----------|---------|
| **`.env`** (gitignored) | Local env vars; never commit. |
| **envchain** (Apple Keychain) | Preferred for Atlas: `envchain atlas` injects vars at runtime. See `docs/ENVCHAIN.md`. |
| **`~/Library/LaunchAgents/*.plist`** | Launchd can have `EnvironmentVariables`; keep plists **out of the repo** or use envchain in the command. |
| **`secrets/`** (e.g. Bambu under clawd) | Tool-specific secrets; path is outside or gitignored. |
| **`credentials.json`, `token.json`** (gitignored) | OAuth credentials. |

## Where Secrets Must NOT Appear

- **Docs and summaries** — No real tokens in `docs/*.md`, session summaries, or READMEs. Use placeholders: `REDACTED`, `use .env`, `from envchain`, `<TELEGRAM_BOT_TOKEN>`, etc.
- **Args and config in repo** — `args/*.yaml` and other committed config: variable names only, no values.
- **Plist examples in repo** — If we keep plist *templates* in the repo, use `<REDACTED>` or `$TELEGRAM_BOT_TOKEN`-style placeholders; never paste real tokens.
- **Logs and backups** — Keep in `.tmp/`, `backups/`, or gitignored dirs; never commit logs that might contain tokens.

## If You Add a New Service

1. Put the secret in **envchain** (and optionally `.env` for local use).  
2. Document the **variable name** only (e.g. `NEW_SERVICE_API_KEY`) in `.env.example` and `docs/ENVCHAIN.md`.  
3. In docs or examples, reference the variable name; never paste the value.  
4. Run `python3 tools/security/secret_scan.py` before committing to catch mistakes.

## Enforcement

- **Pre-commit (optional):** Run `pre-commit install` once; then the secret scan runs on every commit. Config: `.pre-commit-config.yaml`.
- **Manual:** `python3 tools/security/secret_scan.py` from repo root.  
- **AI:** Claude is instructed never to write secrets into tracked files (CLAUDE.md guardrails).
