"""
Telegram bot entry point.

Starts a polling loop, routes incoming messages to the conversation handler,
and sends replies back. Enforces user allowlist and typing indicators from config.

Run:
    python3 tools/telegram/bot.py
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Ensure this package's directory is on the path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from telegram.constants import ChatAction

from config import load_config, get_repo_root
from conversation import handle_message, reset_session, handle_models_command
from commands import route as route_command, get_trial_prep_message, get_code_directive, trigger_restart, can_restart
from group_manager import register_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def _post_init(application) -> None:
    """Send a short 'Connected' message so /restart has visible confirmation."""
    config = load_config()
    allowed = config.get("bot", {}).get("allowed_user_ids", [])
    chat_id = allowed[0] if allowed else None
    if not chat_id:
        env_id = os.environ.get("TELEGRAM_ID", "").strip()
        if env_id and env_id.isdigit():
            chat_id = int(env_id)
    if chat_id:
        try:
            await application.bot.send_message(chat_id=chat_id, text="Back online.")
        except Exception as e:
            logger.warning("Could not send startup notification: %s", e)


async def on_message(update: Update, context) -> None:
    """Handle an incoming text message."""
    config = load_config()
    user = update.effective_user
    user_id = user.id
    chat = update.effective_chat

    # --- Allowlist check ---
    allowed = config.get("bot", {}).get("allowed_user_ids", [])
    if allowed and user_id not in allowed:
        await update.message.reply_text("Sorry, you're not on the access list.")
        return

    # --- Group autodetection ---
    # Register groups/supergroups automatically when bot receives messages
    if chat.type in ("group", "supergroup"):
        is_new = register_chat(chat.id, chat.type, chat.title, chat.username)
        if is_new:
            logger.info("🆕 New group registered: %s (%s)", chat.title, chat.id)

    logger.info(f"Message from user {user_id} ({user.first_name}) in {chat.type} ({chat.title or 'private'}): {update.message.text[:80]}")

    # --- Side-channel: persist raw message for bambu reply handler polling ---
    try:
        (get_repo_root() / "memory/last_incoming_message.txt").write_text(
            update.message.text, encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"Could not persist last incoming message: {e}")

    # --- Substitute /trial or /code with a directive for the LLM ---
    text = update.message.text
    trial_directive = get_trial_prep_message(text)
    if trial_directive is not None:
        text = trial_directive
    else:
        code_directive = get_code_directive(text)
        if code_directive is not None:
            text = code_directive

    # --- Typing indicator ---
    if config.get("bot", {}).get("typing_indicator", True):
        await update.message.chat.send_action(ChatAction.TYPING)

    # --- Handle /reset and /new (clear session, fresh context on next message) ---
    if update.message.text.strip().lower() in ("/reset", "/clear", "/new"):
        reset_session(user_id)
        await update.message.reply_text("Fresh start. Context reloads next message.")
        return

    # --- /restart (allowlisted users only; restarts via LaunchAgent) ---
    if update.message.text.strip().lower() == "/restart":
        allowed = config.get("bot", {}).get("allowed_user_ids", [])
        if not can_restart(user_id, allowed):
            await update.message.reply_text("You're not allowed to restart the bot.")
            return
        reply = trigger_restart()
        await update.message.reply_text(reply)
        return

    # --- /models: list or switch session model (ollama / minimax) ---
    if text.strip().lower().startswith("/models"):
        reply = handle_models_command(user_id, text)
        await update.message.reply_text(reply)
        return

    # --- Slash-command interception (before LLM) ---
    command_reply = route_command(text)
    if command_reply is not None:
        await update.message.reply_text(command_reply)
        return

    # --- Quick signal for known-slow operations (bambu fetches via FTPS) ---
    _lower = text.strip().lower()
    if any(w in _lower for w in ("bambu", "printer", "printing", "ams", "filament", "tray")):
        await update.message.reply_text("checking the printer…")

    # --- Process message via LLM ---
    try:
        reply = await handle_message(text, user_id)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.exception("Error handling message")
        await update.message.reply_text("An error occurred while processing your request.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.startswith("<"):
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    # Verify Ollama is reachable
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=3)
    except Exception:
        print("ERROR: Ollama is not running on localhost:11434. Start it with: ollama serve")
        sys.exit(1)

    print("Starting Telegram bot... (Ctrl+C to stop)")
    app = Application.builder().token(token).post_init(_post_init).build()

    # Handle all text messages (including /reset, /clear)
    app.add_handler(MessageHandler(filters.TEXT, on_message))

    app.run_polling()


if __name__ == "__main__":
    main()
