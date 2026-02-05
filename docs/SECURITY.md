# Security

## Telegram bot access control

In `args/telegram.yaml`, `allowed_user_ids` controls who can use the Atlas Telegram bot.

- **Empty list (`[]`):** No access control. Anyone with the bot link can message it and trigger memory reads/writes, goal reads, and allowlisted scripts.
- **For production:** Set your Telegram user ID (and any other trusted users) so only they can use the bot:
  - `allowed_user_ids: [8241581699]` (example; use your real ID)

**How to get your Telegram user ID:** Message the bot and check the Atlas logs (e.g. `~/Library/Logs/telegram-bot.log`) for the user ID in the log line, or use [@userinfobot](https://t.me/userinfobot) on Telegram.

See `args/telegram.yaml` for the setting.

## Ollama

The Telegram bot talks to Ollama on `localhost:11434` with no authentication. Keep Ollama bound to localhost and run it on a machine you trust. Do not expose Ollama to the network unless you have separate access controls.
