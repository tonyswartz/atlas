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
import re
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure this package's directory is on the path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from telegram.constants import ChatAction

from config import load_config, get_repo_root
from conversation import handle_message, reset_session, handle_models_command
from commands import route as route_command, get_trial_prep_message, get_code_directive, get_rotary_directive, get_schedule_directive, get_episode_directive, get_build_directive, trigger_restart, can_restart
from group_manager import register_chat

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Used by git_sync_and_restart to avoid restarting while the bot is handling a message
BOT_BUSY_FILE = get_repo_root() / "data" / "bot_busy_since"


@asynccontextmanager
async def show_typing(chat, interval: int = 4):
    """Continuously sends a typing action to the chat while active."""
    async def _keep_typing():
        try:
            while True:
                await chat.send_action(ChatAction.TYPING)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Typing indicator failed: %s", e)

    task = asyncio.create_task(_keep_typing())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _handle_podcast_reply(update: Update, reply_to_msg_id: int, text: str) -> bool:
    """
    Smart conversational handler for podcast-related replies.
    Handles: episode ideas, approvals, regeneration requests, and more.
    Returns True if handled, False otherwise.
    """
    import json
    from tools.podcast.pronunciation import parse_one_off_fixes
    from tools.telegram.tool_runner import execute

    prompts_file = Path("/Users/printer/atlas/data/podcast_prompts.json")
    try:
        with open(prompts_file) as f:
            prompts_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False

    text_lower = text.lower().strip()

    # Keywords for different actions
    approval_keywords = ["approved", "approve", "looks good", "lgtm", "go ahead", "yes", "proceed"]
    regenerate_keywords = ["regenerate", "redo", "create new", "make new", "i edited", "edited the script",
                          "new version", "re-generate", "re-synthesize", "resynthesize"]

    # 1. Check if replying to a podcast prompt (episode idea)
    if str(reply_to_msg_id) in prompts_data.get("prompts", {}):
        prompt_info = prompts_data["prompts"][str(reply_to_msg_id)]
        podcast = prompt_info["podcast"]

        logger.info(f"Detected reply to {podcast} podcast prompt - creating episode")

        result_json = execute("podcast_create_episode", {"podcast": podcast, "idea": text})
        result = json.loads(result_json)

        if result.get("success"):
            await update.message.reply_text(
                f"✅ Creating {podcast} episode...\n\nScript generation in progress. You'll get a preview shortly.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to create episode: {result.get('error', 'Unknown error')}",
                parse_mode="Markdown"
            )

        return True

    # 2. Check if replying to a script preview or final audio (approval or regeneration)
    episode_id = None

    # Check script previews
    if str(reply_to_msg_id) in prompts_data.get("script_previews", {}):
        episode_id = prompts_data["script_previews"][str(reply_to_msg_id)]["episode_id"]

    # Check final audio messages
    elif str(reply_to_msg_id) in prompts_data.get("final_audio", {}):
        episode_id = prompts_data["final_audio"][str(reply_to_msg_id)]["episode_id"]

    if episode_id:
        # Detect if this is a paragraph-specific regeneration
        is_paragraph_request = "paragraph" in text_lower or "part about" in text_lower

        # Detect if this is a regeneration request
        is_regenerate = any(keyword in text_lower for keyword in regenerate_keywords)
        is_approval = any(keyword in text_lower for keyword in approval_keywords)

        # Parse pronunciation fixes
        one_off_fixes = parse_one_off_fixes(text)

        if is_paragraph_request and is_regenerate:
            logger.info(f"Detected paragraph regeneration request for episode {episode_id}")

            # Try to extract paragraph number
            import re
            para_number_match = re.search(r'paragraph\s+(\d+)', text_lower)
            search_term_match = re.search(r'(?:part about|paragraph about|section about)\s+([^,\.]+)', text_lower, re.IGNORECASE)

            tool_input = {"episode_id": episode_id}

            if para_number_match:
                tool_input["paragraph_number"] = int(para_number_match.group(1))
                logger.info(f"  Paragraph number: {tool_input['paragraph_number']}")
            elif search_term_match:
                tool_input["search_term"] = search_term_match.group(1).strip()
                logger.info(f"  Search term: {tool_input['search_term']}")
            else:
                # Try to extract any quoted or capitalized term
                potential_terms = re.findall(r'"([^"]+)"', text)
                if potential_terms:
                    tool_input["search_term"] = potential_terms[0]

            if one_off_fixes:
                tool_input["pronunciation_fixes"] = one_off_fixes

            result_json = execute("podcast_regenerate_paragraph", tool_input)
            result = json.loads(result_json)

            if result.get("success"):
                para_info = f" paragraph {result.get('paragraph_number', '?')}" if result.get('paragraph_number') is not None else ""
                await update.message.reply_text(
                    f"🔄 Regenerating{para_info} of {episode_id}...\n\nProcessing just that section.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to regenerate paragraph: {result.get('error', 'Unknown error')}",
                    parse_mode="Markdown"
                )

            return True

        if is_regenerate:
            logger.info(f"Detected regeneration request for episode {episode_id}")

            tool_input = {"episode_id": episode_id}
            if one_off_fixes:
                tool_input["pronunciation_fixes"] = one_off_fixes

            result_json = execute("podcast_regenerate_voice", tool_input)
            result = json.loads(result_json)

            if result.get("success"):
                await update.message.reply_text(
                    f"🔄 Regenerating {episode_id}...\n\nReading your edited script and creating new audio.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to regenerate: {result.get('error', 'Unknown error')}",
                    parse_mode="Markdown"
                )

            return True

        elif is_approval:
            logger.info(f"Detected approval for episode {episode_id}")

            tool_input = {"episode_id": episode_id}
            if one_off_fixes:
                tool_input["pronunciation_fixes"] = one_off_fixes

            result_json = execute("podcast_approve_script", tool_input)
            result = json.loads(result_json)

            if result.get("success"):
                await update.message.reply_text(
                    f"🎙️ {episode_id} approved!\n\nGenerating voice and mixing audio...",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ Failed to process approval: {result.get('error', 'Unknown error')}",
                    parse_mode="Markdown"
                )

            return True

    return False


async def _keep_typing(chat, stop_event):
    """Keep sending typing indicator every 4 seconds until stop_event is set."""
    try:
        while not stop_event.is_set():
            await chat.send_action(ChatAction.TYPING)
            await asyncio.sleep(4)
    except Exception:
        pass  # Ignore errors (e.g., if chat closes)


def _escape_markdown(text: str) -> str:
    """Prepare reply for Telegram parse_mode=Markdown: allow bold/italic/links, but prevent '[date]' or '[LK-511]'
    from being parsed as links (which causes 'Can't parse entities'). Escapes \\ and [ unless part of a link; normalizes ** to *."""
    if not text:
        return text
    # Backslash first so we don't double-escape
    text = text.replace("\\", "\\\\")
    # Telegram uses single * for bold; model often outputs **. Normalize so **bold** -> *bold*
    text = text.replace("**", "*")

    # Split by markdown links: [text](url)
    # This regex matches [text](url) structure
    link_pattern = re.compile(r'(\[[^\]\n]+\]\([^)\n]+\))')
    parts = link_pattern.split(text)

    # parts will be [text, link, text, link, text]
    for i, part in enumerate(parts):
        if i % 2 == 0: # This is text, not a link
            # Escape [ so [26-02-03] don't start a link
            parts[i] = part.replace("[", "\\[")
        # else: it's a link, leave it alone

    return "".join(parts)


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
        await update.message.reply_text("Sorry, you're not on the access list.", parse_mode="Markdown")
        return

    # --- Group autodetection ---
    # Register groups/supergroups automatically when bot receives messages
    if chat.type in ("group", "supergroup"):
        is_new = register_chat(chat.id, chat.type, chat.title, chat.username)
        if is_new:
            logger.info("🆕 New group registered: %s (%s)", chat.title, chat.id)

    logger.info(f"Message from user {user_id} ({user.first_name}) in {chat.type} ({chat.title or 'private'}): {update.message.text[:80]}")

    # --- Group-specific message files for handlers ---
    # Each group can have its own last_message file for specialized handlers
    if chat.type in ("group", "supergroup"):
        group_file = Path(f"/Users/printer/atlas/memory/group_{chat.id}_last_message.txt")
        group_file.write_text(update.message.text, encoding="utf-8")

        # Bambu group: bot stays silent (reply handler processes messages)
        if chat.id == -5286539940:
            logger.info("Bambu group message - staying silent, reply handler will process")
            return

    # --- Podcast reply detection ---
    # Check if this message is a reply to a podcast prompt or script preview
    if update.message.reply_to_message:
        reply_to_msg_id = update.message.reply_to_message.message_id
        podcast_handled = await _handle_podcast_reply(update, reply_to_msg_id, update.message.text)
        if podcast_handled:
            return

    # --- /build and /code: accept in any chat; reply goes to Coding group if not there ---
    text = update.message.text
    text_lower = text.strip().lower()
    coding_group_id = config.get("bot", {}).get("groups", {}).get("code")
    redirect_build_to_coding = (
        coding_group_id
        and chat.id != coding_group_id
        and (text_lower.startswith("/build") or text_lower.startswith("/code"))
    )

    # --- Substitute special commands with directives for the LLM ---
    trial_directive = get_trial_prep_message(text)
    if trial_directive is not None:
        text = trial_directive
    else:
        code_directive = get_code_directive(text)
        if code_directive is not None:
            text = code_directive
        else:
            rotary_directive = get_rotary_directive(text)
            if rotary_directive is not None:
                text = rotary_directive
            else:
                schedule_directive = get_schedule_directive(text)
                if schedule_directive is not None:
                    text = schedule_directive
                else:
                    build_directive = get_build_directive(text)
                    if build_directive is not None:
                        text = build_directive
                    else:
                        episode_directive = get_episode_directive(text)
                        if episode_directive is not None:
                            text = episode_directive

    # --- Start continuous typing indicator ---
    typing_enabled = config.get("bot", {}).get("typing_indicator", True)
    stop_typing = asyncio.Event()
    typing_task = None

    if typing_enabled:
        typing_task = asyncio.create_task(_keep_typing(update.message.chat, stop_typing))

    try:
        # Signal that we're handling a message (for git_sync_and_restart: don't restart mid-turn)
        try:
            BOT_BUSY_FILE.parent.mkdir(parents=True, exist_ok=True)
            BOT_BUSY_FILE.touch()
        except OSError:
            pass

        # --- Handle /reset and /new (clear session, fresh context on next message) ---
        if update.message.text.strip().lower() in ("/reset", "/clear", "/new"):
            reset_session(user_id)
            await update.message.reply_text("Fresh start. Context reloads next message.", parse_mode="Markdown")
            return

        # --- /restart (allowlisted users only; restarts via LaunchAgent) ---
        if update.message.text.strip().lower() == "/restart":
            allowed = config.get("bot", {}).get("allowed_user_ids", [])
            if not can_restart(user_id, allowed):
                await update.message.reply_text("You're not allowed to restart the bot.", parse_mode="Markdown")
                return
            reply = trigger_restart()
            await update.message.reply_text(_escape_markdown(reply), parse_mode="Markdown")
            return

        # --- /models: list or switch session model (ollama / minimax) ---
        if text.strip().lower().startswith("/models"):
            reply = handle_models_command(user_id, text)
            await update.message.reply_text(_escape_markdown(reply), parse_mode="Markdown")
            return

        # --- Slash-command interception (before LLM) ---
        command_reply = route_command(text)
        if command_reply is not None:
            await update.message.reply_text(_escape_markdown(command_reply), parse_mode="Markdown")
            return

        # --- Quick signal for known-slow operations (bambu fetches via FTPS) ---
        # Skip for /build and /code so we don't say "checking the printer" when building a script that mentions printer
        _lower = text.strip().lower()
        if not (_lower.startswith("/build") or _lower.startswith("/code")):
            if any(w in _lower for w in ("bambu", "printer", "printing", "ams", "filament", "tray")):
                await update.message.reply_text("checking the printer…", parse_mode="Markdown")

        # --- Process message via LLM ---
        reply = await handle_message(text, user_id)
        if redirect_build_to_coding:
            await context.bot.send_message(
                chat_id=coding_group_id,
                text="From main chat:\n\n" + _escape_markdown(reply),
                parse_mode="Markdown",
            )
            await update.message.reply_text(
                "I'm handling your request in the Coding group — check there for my response and any follow-up questions.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(_escape_markdown(reply), parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error handling message")
        await update.message.reply_text(_escape_markdown(f"Couldn't do that: {e}"), parse_mode="Markdown")
    finally:
        # Clear busy indicator so git_sync can restart when idle
        try:
            if BOT_BUSY_FILE.exists():
                BOT_BUSY_FILE.unlink()
        except OSError:
            pass
        # Stop typing indicator
        if typing_task:
            stop_typing.set()
            try:
                await asyncio.wait_for(typing_task, timeout=1.0)
            except asyncio.TimeoutError:
                typing_task.cancel()


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
    from telegram.request import HTTPXRequest
    # Increase timeouts: connect=30s, read=30s, write=30s, pool=30s
    request = HTTPXRequest(connection_pool_size=8, connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0, pool_timeout=30.0)
    app = Application.builder().token(token).request(request).post_init(_post_init).build()

    # Handle all text messages (including /reset, /clear)
    app.add_handler(MessageHandler(filters.TEXT, on_message))

    app.run_polling()


if __name__ == "__main__":
    main()
