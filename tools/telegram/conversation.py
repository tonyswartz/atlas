"""
Conversation handler.

Manages per-user state and runs the Claude tool_use loop.
On first message from a user, loads memory and builds the system prompt.
Each subsequent message appends to the existing conversation history.
"""

import os
import json
import sqlite3
import logging
import openai
from pathlib import Path

from config import load_config, get_repo_root
from tool_definitions import TOOL_DEFINITIONS
import tool_runner

REPO_ROOT = get_repo_root()
logger = logging.getLogger(__name__)

_SESSIONS_PATH = REPO_ROOT / "data" / "sessions.json"
_SESSIONS_DB_PATH = REPO_ROOT / "data" / "sessions.db"


def _init_db() -> None:
    """Initialize the sessions database table."""
    try:
        _SESSIONS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(_SESSIONS_DB_PATH) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions (user_id INTEGER PRIMARY KEY, data TEXT)"
            )
            conn.commit()
    except sqlite3.Error as e:
        logger.error("Failed to initialize sessions DB: %s", e)


def _migrate_json_to_db() -> None:
    """Migrate legacy sessions.json to SQLite if needed."""
    if not _SESSIONS_PATH.exists():
        return

    try:
        with sqlite3.connect(_SESSIONS_DB_PATH) as conn:
            # Check if DB is already populated to avoid overwriting with stale JSON
            cursor = conn.execute("SELECT count(*) FROM sessions")
            if cursor.fetchone()[0] > 0:
                logger.warning("DB already populated; skipping migration from %s", _SESSIONS_PATH.name)
                return

            logger.info("Migrating sessions.json to SQLite...")
            raw = json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))
            for k, v in raw.items():
                try:
                    uid = int(k)
                    data = json.dumps({
                        "messages": v.get("messages", []),
                        "model_id": v.get("model_id", "ollama"),
                    })
                    conn.execute(
                        "INSERT OR REPLACE INTO sessions (user_id, data) VALUES (?, ?)",
                        (uid, data)
                    )
                except ValueError:
                    logger.warning("Skipping invalid user ID during migration: %s", k)
            conn.commit()

        # Rename legacy file
        backup = _SESSIONS_PATH.with_suffix(".json.migrated")
        _SESSIONS_PATH.rename(backup)
        logger.info("Migration complete. Legacy file renamed to %s", backup.name)

    except (json.JSONDecodeError, OSError, sqlite3.Error) as e:
        logger.error("Migration failed: %s", e)


def _save_session(user_id: int) -> None:
    """Persist a single user's session to DB."""
    sess = _sessions.get(user_id)
    if not sess:
        return

    try:
        data = json.dumps({
            "messages": sess.get("messages", []),
            "model_id": sess.get("model_id", "ollama"),
        })
        with sqlite3.connect(_SESSIONS_DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (user_id, data) VALUES (?, ?)",
                (user_id, data)
            )
            conn.commit()
    except (sqlite3.Error, OSError) as e:
        logger.warning("Failed to save session for user %d: %s", user_id, e)


def _delete_session(user_id: int) -> None:
    """Remove a user's session from DB."""
    try:
        with sqlite3.connect(_SESSIONS_DB_PATH) as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()
    except sqlite3.Error as e:
        logger.warning("Failed to delete session for user %d: %s", user_id, e)


def _sanitize_loaded_messages(messages: list) -> list:
    """Strip assistant tool_calls and tool messages from persisted history so we never send
    stale tool_call ids to the API (OpenRouter/MiniMax reject 'tool id not found' when
    tool results don't match the current turn's assistant tool_calls)."""
    out = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            continue
        if role == "assistant" and m.get("tool_calls"):
            sanitized = {"role": "assistant", "content": m.get("content") or ""}
            if sanitized["content"] and not sanitized["content"].strip().endswith("[Tools were used.]"):
                sanitized["content"] = (sanitized["content"].strip() + "\n\n[Tools were used.]").strip()
            elif not sanitized["content"].strip():
                sanitized["content"] = "[Tools were used.]"
            out.append(sanitized)
            continue
        out.append(m)
    return out


def _load_sessions() -> dict:
    """Load persisted session messages from disk. system_prompt regenerates fresh on next use."""
    _init_db()
    _migrate_json_to_db()

    try:
        with sqlite3.connect(_SESSIONS_DB_PATH) as conn:
            cursor = conn.execute("SELECT user_id, data FROM sessions")
            raw_sessions = {}
            for row in cursor:
                uid, data_str = row
                try:
                    data = json.loads(data_str)
                    raw_sessions[uid] = {
                        "messages": data.get("messages", []),
                        "system_prompt": "",
                        "memory_loaded": False,
                        "model_id": data.get("model_id", "ollama"),
                    }
                except json.JSONDecodeError:
                    logger.warning("Skipping corrupt session data for user %d", uid)
            return raw_sessions
    except sqlite3.Error as e:
        logger.error("Failed to load sessions from DB: %s", e)
        return {}


# Per-user conversation state: { user_id: { messages, system_prompt, memory_loaded, model_id } }
_sessions: dict = _load_sessions()

# Max messages to keep in history (oldest dropped first, system prompt is separate)
MAX_HISTORY = 30


def _load_system_prompt(memory_context: str) -> str:
    """Read the system prompt template and inject persona, memory + tool reference."""
    template_path = REPO_ROOT / "hardprompts" / "telegram_system_prompt.md"
    tool_ref_path = REPO_ROOT / "context" / "gotcha_tools_reference.md"
    soul_path = REPO_ROOT / "context" / "SOUL.md"
    user_path = REPO_ROOT / "context" / "USER.md"

    template = template_path.read_text(encoding="utf-8")
    tool_ref = tool_ref_path.read_text(encoding="utf-8")

    persona_parts = []
    if soul_path.exists():
        persona_parts.append(soul_path.read_text(encoding="utf-8"))
    if user_path.exists():
        persona_parts.append(user_path.read_text(encoding="utf-8"))
    persona_context = "\n\n".join(persona_parts) if persona_parts else "(No SOUL.md or USER.md in context.)"

    prompt = template.replace("[PERSONA_CONTEXT]", persona_context)
    prompt = prompt.replace("[MEMORY_CONTEXT]", memory_context)
    prompt = prompt.replace("[TOOL_REFERENCE]", tool_ref)
    return prompt


async def _load_memory() -> str:
    """Run memory_read and return a formatted string for the system prompt."""
    config = load_config()
    mem_cfg = config.get("memory", {})

    result = await tool_runner.execute("memory_read", {
        "format": "json",
        "include_db": mem_cfg.get("load_db_entries", True),
        "days": mem_cfg.get("log_days", 2),
    })

    # result is a JSON string — parse and summarise for the prompt
    try:
        data = json.loads(result)
        parts = []

        # MEMORY.md content
        mem_file = data.get("memory_file", {})
        if mem_file.get("success") and mem_file.get("content"):
            parts.append("### MEMORY.md\n" + mem_file["content"])

        # Daily logs
        for log in data.get("daily_logs", []):
            if log.get("success") and log.get("content"):
                parts.append(f"### Log: {log.get('date', 'unknown')}\n" + log["content"])

        # DB entries
        for entry in data.get("db_entries", []):
            parts.append(f"- [{entry.get('type', '?')}] {entry.get('content', '')}")

        return "\n\n".join(parts) if parts else "(no memory entries yet)"
    except (json.JSONDecodeError, KeyError):
        return result  # fallback: return raw output


def _trim_history(messages: list) -> list:
    """Drop oldest messages if history exceeds MAX_HISTORY."""
    if len(messages) <= MAX_HISTORY:
        return messages
    return messages[-MAX_HISTORY:]


# Phrases that clearly mean "search the web" / "browse the internet"
_WEB_SEARCH_TRIGGERS = (
    "browse the internet",
    "search the web",
    "look up on the web",
    "search the web for",
    "look up online",
    "search online",
    "look it up online",
    "find out online",
    "search online for",
)

# Priorities / what's on my plate — prefetch kanban + journal + reminders so first reply is data-backed
_PRIORITIES_TRIGGERS = (
    "my priorities",
    "my top priorities",
    "what should i focus on",
    "what should i work on",
    "what's on my plate",
    "what do i need to do",
    "what have i got going",
    "priorities this week",
)

# What's today — prefetch reminders (and optionally daily_brief is called by model)
_WHATS_TODAY_TRIGGERS = (
    "what's today",
    "what do i have today",
    "whats today",
    "what do i have on today",
    "what's my day",
    "whats my day",
    "what do i have on",
)


# "Remind me" — prefetch current reminders so model has context before calling reminder_add
_REMIND_ME_TRIGGERS = (
    "remind me to ",
    "remind me about ",
    "set a reminder for ",
    "set a reminder to ",
    "add a reminder",
    "remind me ",
)

# Bambu printer — prefetch status + last completed print so model has data to answer from
_BAMBU_TRIGGERS = (
    "bambu",
    "printer",
    "print status",
    "what's printing",
    "whats printing",
    "is it printing",
    "my print",
    "last print",
    "recent print",
    "print finished",
    "print done",
    "filament",
    "ams",
    "3d print",
)

# Deflection phrases — local 7B model sometimes refuses or asks for clarification instead of acting
_DEFLECTION_PHRASES = (
    "i'm not able to",
    "i cannot",
    "i can't ",
    "i don't have the ability",
    "as an ai",
    "i'm unable to",
    "i apologize, but i",
    "sorry, but i",
    "i'm afraid i",
    "i don't think i can",
    "that's not something i",
    "unfortunately, i",
    "i'm just an ai",
    "i don't have access",
    # Wishy-washy clarification requests when it should just act
    "could you specify",
    "could you clarify",
    "could you provide more",
    "to better understand",
    "which aspects are you interested in",
    "what specifically would you like",
    "can you provide more context",
    "i need more information",
    "please specify",
)


def _is_remind_me_intent(text: str) -> bool:
    """True if the user is asking to set a reminder."""
    lower = (text or "").strip().lower()
    return any(phrase in lower for phrase in _REMIND_ME_TRIGGERS)


def _is_bambu_intent(text: str) -> bool:
    """True if the user is asking about the Bambu printer or a recent print."""
    lower = (text or "").strip().lower()
    return any(phrase in lower for phrase in _BAMBU_TRIGGERS)


def _is_deflection(text: str | None) -> bool:
    """True if the model response looks like a deflection/refusal rather than an actual answer."""
    if not text or len(text.strip()) < 10:
        return True
    lower = text.strip().lower()
    return any(phrase in lower for phrase in _DEFLECTION_PHRASES)


import re as _re
_THINK_TAG = _re.compile(r'<think>.*?</think>', _re.DOTALL)

def _strip_think(text: str) -> str:
    """Remove <think>...</think> reasoning blocks that MiniMax includes by default."""
    return _THINK_TAG.sub('', text).strip()


def _get_openrouter_key() -> str | None:
    """Load OpenRouter API key from environment, .env, or legacy clawdbot profiles."""
    # Check environment first
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key

    # Check .env file
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.upper().startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"\'')
                if key:
                    return key

    # Check legacy clawdbot auth profiles
    legacy = Path.home() / ".clawdbot/agents/main/agent/auth-profiles.json"
    if legacy.exists():
        try:
            prof = json.loads(legacy.read_text()).get("profiles", {}).get("openrouter:default", {})
            if prof.get("type") == "api_key":
                key = prof.get("key")
                if key:
                    return key
        except Exception:
            pass

    return None


def _is_rate_limit_error(error: Exception) -> bool:
    """Check if error is a rate limit / quota exceeded error."""
    error_str = str(error).lower()
    # Check for common rate limit indicators
    return any(phrase in error_str for phrase in [
        "rate limit", "quota", "429", "too many requests",
        "rate_limit_exceeded", "quota_exceeded", "insufficient_quota"
    ])


def _get_provider_client(provider_cfg: dict):
    """Build OpenAI-compatible client for a provider config. Returns (client, model_name, provider_name) or (None, None, None)."""
    provider = provider_cfg.get("provider", "")

    if provider == "minimax":
        api_key_env = provider_cfg.get("api_key_env", "MINIMIAX_CODING")
        key = os.environ.get(api_key_env, "").strip()
        if not key:
            logger.warning(f"{api_key_env} not found — MiniMax unavailable")
            return None, None, None
        client = openai.OpenAI(
            base_url=provider_cfg.get("base_url", "https://api.minimax.io/v1"),
            api_key=key,
            timeout=provider_cfg.get("timeout", 60.0)
        )
        return client, provider_cfg.get("model", "MiniMax-M2.5"), "minimax"

    elif provider == "openrouter":
        key = _get_openrouter_key()
        if not key:
            logger.warning("OPENROUTER_API_KEY not found — OpenRouter unavailable")
            return None, None, None
        client = openai.OpenAI(
            base_url=provider_cfg.get("base_url", "https://openrouter.ai/api/v1"),
            api_key=key,
            timeout=provider_cfg.get("timeout", 60.0)
        )
        return client, provider_cfg.get("model", "openrouter/free"), "openrouter"

    elif provider == "ollama":
        client = openai.OpenAI(
            base_url=provider_cfg.get("base_url", "http://localhost:11434/v1"),
            api_key="ollama",
            timeout=provider_cfg.get("timeout", 120.0)
        )
        return client, provider_cfg.get("model", "qwen2.5:14b"), "ollama"

    return None, None, None


def _get_client_and_model(user_id: int):
    """Return (client, model_name, provider_id) for the session's selected model. Ensures session exists."""
    config = load_config()
    if user_id not in _sessions:
        _sessions[user_id] = {
            "messages": [],
            "system_prompt": "",
            "memory_loaded": False,
            "model_id": "primary",  # Default to primary (MiniMax coding plan)
        }
    model_id = _sessions[user_id].get("model_id", "primary")

    # Try primary model
    if model_id == "primary":
        primary_cfg = config.get("primary", {})
        if primary_cfg:
            client, model_name, provider = _get_provider_client(primary_cfg)
            if client and model_name:
                return client, model_name, provider or "minimax"
        logger.warning("Primary model unavailable — falling through to fallbacks")
        model_id = "fallback"  # Fall through

    # Try fallbacks in order
    if model_id == "fallback" or model_id in ["openrouter", "minimax", "ollama"]:
        fallbacks = config.get("fallbacks", [])

        # If user manually selected a specific provider, try that first
        if model_id in ["openrouter", "minimax", "ollama"]:
            for fb_cfg in fallbacks:
                if fb_cfg.get("provider") == model_id and fb_cfg.get("enabled", True):
                    client, model_name, provider = _get_provider_client(fb_cfg)
                    if client and model_name:
                        return client, model_name, provider or model_id

        # Otherwise try all enabled fallbacks in order
        for fb_cfg in fallbacks:
            if fb_cfg.get("enabled", True):
                client, model_name, provider = _get_provider_client(fb_cfg)
                if client and model_name:
                    logger.info(f"Using fallback: {provider}")
                    return client, model_name, provider or "unknown"

        logger.warning("All fallbacks exhausted")

    # Final fallback - Ollama (should always work if running)
    logger.warning("Using final fallback: Ollama")
    client = openai.OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        timeout=120.0,
    )
    return client, "qwen2.5:14b", "ollama"


def get_available_models() -> list[dict]:
    """Return list of {id, label} for models the user can select."""
    config = load_config()
    models = []

    # Primary model (MiniMax coding plan)
    primary_cfg = config.get("primary", {})
    if primary_cfg:
        client, model_name, provider = _get_provider_client(primary_cfg)
        if client and model_name:
            models.append({
                "id": "primary",
                "label": f"{model_name} (primary - coding plan)",
            })

    # Fallback models
    fallbacks = config.get("fallbacks", [])
    for fb_cfg in fallbacks:
        if not fb_cfg.get("enabled", True):
            continue
        provider = fb_cfg.get("provider", "")
        client, model_name, provider_id = _get_provider_client(fb_cfg)
        if client and model_name:
            models.append({
                "id": provider,
                "label": f"{model_name} ({provider} - fallback)",
            })

    return models


def handle_models_command(user_id: int, text: str) -> str:
    """
    Handle /models [id]. No arg: list models and current. With arg: switch session to that model.
    """
    arg = (text or "").strip()
    if arg.lower().startswith("/models"):
        arg = arg[7:].strip()
    available = get_available_models()
    ids = [m["id"] for m in available]

    if not arg:
        current = _sessions.get(user_id, {}).get("model_id", "openrouter")
        lines = [f"Session model: {current}", ""]
        for m in available:
            mark = " ✓" if m["id"] == current else ""
            lines.append(f"• {m['id']} — {m['label']}{mark}")
        lines.append("")
        lines.append("Switch: /models <id>  (e.g., /models openrouter)")
        return "\n".join(lines)

    choice = arg.lower().strip()
    if choice not in ids:
        return f"Unknown model: {choice}. Use: " + ", ".join(ids)

    if user_id not in _sessions:
        _sessions[user_id] = {
            "messages": [],
            "system_prompt": "",
            "memory_loaded": False,
            "model_id": "ollama",
        }
    _sessions[user_id]["model_id"] = choice
    _save_session(user_id)
    label = next(m["label"] for m in available if m["id"] == choice)
    return f"Session set to {choice} ({label}). Your next messages will use this model."


def _is_web_search_intent(text: str) -> bool:
    """True if the user is clearly asking to search or browse the web."""
    lower = (text or "").strip().lower()
    return any(phrase in lower for phrase in _WEB_SEARCH_TRIGGERS)


def _is_priorities_intent(text: str) -> bool:
    """True if the user is asking about their priorities or what to focus on."""
    lower = (text or "").strip().lower()
    return any(phrase in lower for phrase in _PRIORITIES_TRIGGERS)


def _is_whats_today_intent(text: str) -> bool:
    """True if the user is asking what's on today or what they have today."""
    lower = (text or "").strip().lower()
    return any(phrase in lower for phrase in _WHATS_TODAY_TRIGGERS)


def _derive_search_query(text: str) -> str:
    """Turn a 'browse the web to find...' style message into a short search query."""
    lower = (text or "").strip()
    # Remove common lead-in phrases so the rest is the actual question
    for phrase in (
        "browse the internet to see if you can determine ",
        "browse the internet to ",
        "search the web to see if ",
        "search the web for ",
        "search the web to ",
        "look up on the web ",
        "look up online ",
        "search online for ",
        "search online ",
    ):
        if lower.lower().startswith(phrase):
            lower = lower[len(phrase) :].strip()
            break
    # Use the whole (possibly trimmed) message as the query; Brave handles natural language. Cap length.
    query = (lower or text or "search").strip()
    if len(query) > 250:
        query = query[:247] + "..."
    return query or "search"


async def handle_message(text: str, user_id: int) -> str:
    """
    Handle an incoming message from a Telegram user.

    Maintains per-user conversation state. On first message, loads memory
    and builds the system prompt. Runs the OpenAI-compatible tool-use loop
    against the session's selected model (Ollama or Minimax) until the model
    returns a text-only response.
    """
    config = load_config()
    client, model_name, provider_id = _get_client_and_model(user_id)

    # --- Session init (or re-init after restart with persisted messages) ---
    if user_id not in _sessions or not _sessions[user_id].get("memory_loaded"):
        memory_text = await _load_memory()
        system_prompt = _load_system_prompt(memory_text)
        if user_id in _sessions:
            # Restored from disk — keep messages, attach fresh prompt
            _sessions[user_id]["system_prompt"] = system_prompt
            _sessions[user_id]["memory_loaded"] = True
        else:
            _sessions[user_id] = {
                "messages": [],
                "system_prompt": system_prompt,
                "memory_loaded": True,
                "model_id": "primary",  # Use primary model by default (MiniMax coding plan)
            }

    session = _sessions[user_id]

    # Append user message
    session["messages"].append({"role": "user", "content": text})
    session["messages"] = _trim_history(session["messages"])

    # NOTE: incoming message already written in bot.py for Bambu group only
    # (removed duplicate write here to prevent overwriting Bambu replies)

    # --- Prefetch web search disabled ---
    # Let the LLM choose browser tool for current information based on tool descriptions.
    # Prefetching search APIs bypasses the LLM's decision-making and prevents it from
    # using the browser tool to scrape actual page content.
    # if _is_web_search_intent(text):
    #     ... (prefetch logic disabled)

    # --- Prefetch for "priorities" / "what should I focus on" ---
    # Run tools and inject results as a user context message. Avoids fake assistant+tool_calls
    # which break APIs (OpenRouter/MiniMax) that validate tool_call_id against the last assistant.
    if _is_priorities_intent(text):
        kanban = await tool_runner.execute("kanban_read", {})
        journal = await tool_runner.execute("journal_read_recent", {"days": 7})
        reminders = await tool_runner.execute("reminders_read", {})
        ctx = (
            "[Context already fetched — use this to answer; call other tools only if needed.]\n\n"
            "**Tasks (Tony Tasks.md):**\n" + (kanban[:4000] + "…" if len(kanban) > 4000 else kanban) + "\n\n"
            "**Journal (last 7 days):**\n" + (journal[:4000] + "…" if len(journal) > 4000 else journal) + "\n\n"
            "**Reminders:**\n" + (reminders[:2000] + "…" if len(reminders) > 2000 else reminders)
        )
        session["messages"].append({"role": "user", "content": ctx})

    # --- Prefetch for "what's today" / "what do I have today" ---
    # Skip if we already prefetched (e.g. "what are my priorities today" matched priorities).
    elif _is_whats_today_intent(text):
        reminders = await tool_runner.execute("reminders_read", {})
        ctx = (
            "[Reminders already fetched — use this; call calendar/daily_brief if needed.]\n\n"
            "**Reminders:**\n" + (reminders[:3000] + "…" if len(reminders) > 3000 else reminders)
        )
        session["messages"].append({"role": "user", "content": ctx})

    # --- Prefetch for "remind me to ..." ---
    elif _is_remind_me_intent(text):
        reminders = await tool_runner.execute("reminders_read", {})
        ctx = "[Current reminders — use when adding the new one.]\n\n" + (reminders[:3000] + "…" if len(reminders) > 3000 else reminders)
        session["messages"].append({"role": "user", "content": ctx})

    # --- Bambu/printer questions → deterministic handler ---
    # The local 7B model loops infinitely on the bambu tool. Answer directly from data.
    # Try MiniMax first for natural phrasing; fall back to deterministic formatter.
    if _is_bambu_intent(text):
        status_result = await tool_runner.execute("bambu", {"action": "status"})
        ams_result = await tool_runner.execute("bambu", {"action": "ams"})
        state_path = REPO_ROOT / "data" / "bambu_last_state.json"
        try:
            live = json.loads(status_result)
        except (json.JSONDecodeError, TypeError):
            live = {"raw": status_result}
        if state_path.exists():
            try:
                watcher_state = json.loads(state_path.read_text(encoding="utf-8"))
                live["last_completed_print"] = watcher_state.get("last_completed_print", "unknown")
                live["last_completed_at"] = watcher_state.get("last_completed_at", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        try:
            ams_data = json.loads(ams_result)
        except (json.JSONDecodeError, TypeError):
            ams_data = {}

        # Download + parse slice_info, but only for the file the watcher logged as last completed.
        # Do NOT fall back to newest file — phone prints may not match.
        slice_info = None
        last_completed_name = live.get("last_completed_print", "")
        if last_completed_name:
            try:
                from tools.bambu.bambu_watcher import ftp_list_gcode_3mf, ftp_download, parse_slice_info_from_3mf
                import tempfile
                entries = ftp_list_gcode_3mf()
                match = next((e for e in entries if e["name"] == last_completed_name), None)
                if match:
                    tmp_3mf = Path(tempfile.gettempdir()) / "last_print.gcode.3mf"
                    if ftp_download(match["name"], tmp_3mf):
                        slice_info = parse_slice_info_from_3mf(tmp_3mf)
                        tmp_3mf.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("slice_info fetch failed: %s", e)
        live["slice_info"] = slice_info

        # Try primary model for a natural-language answer
        reply = None
        config = load_config()
        primary_cfg = config.get("primary", {})
        bambu_client, bambu_model, _ = _get_provider_client(primary_cfg)
        if bambu_client:
            bambu_prompt = (
                "You are a helpful assistant with access to a Bambu 3D printer.\n"
                "Answer the user's question concisely based on the data below.\n\n"
                f"[Printer Status]\n{json.dumps(live, indent=2)}\n\n"
                f"[AMS Status]\n{json.dumps(ams_data, indent=2)}\n\n"
                f"User question: {text}"
            )
            try:
                fb_resp = bambu_client.chat.completions.create(
                    model=bambu_model,
                    messages=[{"role": "user", "content": bambu_prompt}],
                    temperature=0.3,
                    max_tokens=2048,  # Bambu prompts are short
                )
                reply = _strip_think(fb_resp.choices[0].message.content or "")
                logger.info("Bambu query answered via MiniMax")
            except Exception as e:
                logger.warning("MiniMax bambu query failed: %s — using deterministic formatter", e)

        # Deterministic fallback: format status from the data we already have
        if not reply:
            data = live.get("data", live)
            state = data.get("gcode_state", "unknown").upper()
            pct = data.get("percent", "?")
            fname = data.get("file", "unknown").split("/")[-1]
            last = live.get("last_completed_print", "unknown")
            last_at = live.get("last_completed_at", "unknown")

            lines = []
            if state == "PRINTING":
                lines.append(f"Printing: {fname} — {pct}% done")
            elif state == "PAUSE":
                lines.append(f"Paused: {fname} at {pct}%")
            elif state == "FINISH":
                lines.append(f"Idle — last print finished: {fname}")
            else:
                lines.append(f"Status: {state}")

            lines.append(f"Last completed: {last} ({last_at})")

            # If we have slice_info, show what filament was actually used and match to tray
            si = live.get("slice_info")
            if si:
                lines.append(f"Filament used: {si.get('material','?')} #{si.get('color','?')} — {si.get('used_g','?')}g ({si.get('used_m','?')}m)")

            # AMS trays: data.ams.ams[].tray[]
            # Match the "used" tray by comparing slice_info material+color to tray data
            ams_units = ams_data.get("data", {}).get("ams", {}).get("ams", [])
            trays = [t for unit in ams_units for t in unit.get("tray", [])]
            used_tray = None
            if trays and si:
                si_mat = (si.get("material") or "").upper()
                si_color = (si.get("color") or "").upper()[:6]
                used_tray = next(
                    (t for t in trays
                     if t.get("tray_type", "").upper() == si_mat
                     and (t.get("tray_color") or "")[:6].upper() == si_color),
                    None
                )
            if trays:
                if used_tray:
                    lines.append(f"Used tray: Tray {used_tray.get('id','?')} ({used_tray.get('tray_type','?')} #{(used_tray.get('tray_color') or '?')[:6]})")
                lines.append("AMS trays:")
                for t in trays:
                    ttype = t.get("tray_type", "?")
                    color = (t.get("tray_color") or "?")[:6]
                    remain = t.get("remain", -1)
                    remain_str = f"{remain}g" if remain and remain > 0 else "no spool data"
                    marker = " ◄" if t is used_tray else ""
                    lines.append(f"  Tray {t.get('id','?')}: {ttype} #{color} — {remain_str}{marker}")

            reply = "\n".join(lines)

        session["messages"].append({"role": "assistant", "content": reply})
        _save_session(user_id)
        return reply

    # --- Tool-use loop with hardened safeguards ---

    # Get model_id from session to determine message role compatibility
    session_model_id = session.get("model_id", "primary")

    # System prompt is prepended as a message (OpenAI convention)
    # but kept out of session["messages"] so it survives history trimming
    # MiniMax doesn't support system role, so we convert it to user message
    system_role = "system" if session_model_id != "minimax" else "user"
    api_messages = [{"role": system_role, "content": session["system_prompt"]}] + session["messages"]

    MAX_TOOL_ROUNDS = 10
    MAX_CALLS_PER_TOOL = 3  # Prevent any single tool from being called too many times
    REQUIRE_TEXT_EVERY = 4  # Force text response every N rounds

    # Track tool usage to detect loops
    tool_call_counts = {}
    rounds_since_text = 0

    for _round in range(MAX_TOOL_ROUNDS):
        # Safeguard: Force text response if too many rounds without one
        if rounds_since_text >= REQUIRE_TEXT_EVERY:
            logger.warning(f"Forcing text response after {rounds_since_text} rounds without text")
            api_messages.append({
                "role": system_role,
                "content": "IMPORTANT: You must provide a text response now. Do not make any more tool calls until you've responded to the user."
            })
            rounds_since_text = 0  # Reset counter

        # Try API call with automatic fallback on rate limits
        response = None
        used_provider = provider_id
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=api_messages,
                tools=TOOL_DEFINITIONS,
                temperature=config.get("primary", {}).get("temperature", 0.7),
                max_tokens=config.get("primary", {}).get("max_tokens", 4096),
            )
        except Exception as e:
            # Check if this is a rate limit error
            if _is_rate_limit_error(e):
                logger.warning(f"Rate limit hit on {provider_id}: {e}")
                logger.info("Attempting fallback models...")

                # Try each fallback in order
                fallbacks = config.get("fallbacks", [])
                for fb_cfg in fallbacks:
                    if not fb_cfg.get("enabled", True):
                        continue

                    fb_client, fb_model, fb_provider = _get_provider_client(fb_cfg)
                    if not fb_client or not fb_model:
                        continue

                    try:
                        logger.info(f"Trying fallback: {fb_provider}")
                        response = fb_client.chat.completions.create(
                            model=fb_model,
                            messages=api_messages,
                            tools=TOOL_DEFINITIONS,
                            temperature=fb_cfg.get("temperature", 0.7),
                            max_tokens=fb_cfg.get("max_tokens", 4096),
                        )
                        used_provider = fb_provider
                        logger.info(f"Fallback succeeded: {fb_provider}")
                        break
                    except Exception as fb_e:
                        logger.warning(f"Fallback {fb_provider} failed: {fb_e}")
                        continue

                if not response:
                    logger.error("All fallbacks exhausted")
                    return f"All models unavailable. Primary error: {e}"
            else:
                logger.exception(f"API call failed: {e}")
                return f"API error: {e}"

        if not response:
            return "API error: No response from any model"

        if not response or not response.choices:
            logger.error(f"Empty response from API: {response}")
            return "Got empty response from API"

        message = response.choices[0].message
        tool_calls = message.tool_calls

        # Debug logging
        logger.info(f"OpenRouter response - content: {repr(message.content)}, tool_calls: {bool(tool_calls)}, finish_reason: {response.choices[0].finish_reason}")

        # Append assistant message to history (must include tool_calls for round-trip)
        # Strip <think> tags from MiniMax responses before saving
        content = message.content
        if used_provider == "minimax" and content:
            content = _strip_think(content)
        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": str(tc.id) if tc.id is not None else f"tool_call_{tc.function.name}_{_round}",
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        session["messages"].append(assistant_msg)
        api_messages.append(assistant_msg)

        if not tool_calls:
            # Strip <think> tags from MiniMax responses
            reply = message.content or "(no response)"
            if used_provider == "minimax":
                reply = _strip_think(reply)

            _save_session(user_id)
            return reply

        # Safeguard: Check for tool loops before executing
        loop_detected = False
        for tc in tool_calls:
            tool_call_counts[tc.function.name] = tool_call_counts.get(tc.function.name, 0) + 1

            if tool_call_counts[tc.function.name] > MAX_CALLS_PER_TOOL:
                logger.warning(f"Loop detected: {tc.function.name} called {tool_call_counts[tc.function.name]} times (max {MAX_CALLS_PER_TOOL})")
                loop_detected = True
                break

        if loop_detected:
            _save_sessions()
            return f"I seem to be stuck in a loop calling the same tools repeatedly. Let me try a different approach: could you rephrase your request or break it into smaller steps?"

        # Execute each tool call and feed results back individually
        # (OpenAI requires one tool_result message per tool_call_id)
        # Use string id so APIs (e.g. MiniMax/OpenRouter) that validate tool_call_id get a consistent format.
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse tool arguments: {e}. Raw: {tc.function.arguments[:200]}")
                args = {}

            logger.info("Tool call round %d: %s(%s)", _round, tc.function.name, tc.function.arguments[:120])
            result_str = await tool_runner.execute(tc.function.name, args)

            tc_id = tc.id if tc.id is not None else f"tool_call_{tc.function.name}_{_round}"
            tool_result_msg = {
                "role": "tool",
                "tool_call_id": str(tc_id),
                "content": result_str,
            }
            session["messages"].append(tool_result_msg)
            api_messages.append(tool_result_msg)

        rounds_since_text += 1
        # Loop continues — model sees results and may call more tools or respond

    # Exhausted max tool rounds without a text reply
    logger.warning("Tool-use loop hit %d rounds without text reply — returning last content", MAX_TOOL_ROUNDS)
    _save_session(user_id)
    return message.content or "(tool loop limit reached — no text response)"


def reset_session(user_id: int) -> None:
    """Clear a user's conversation state. Next message will reload memory."""
    _sessions.pop(user_id, None)
    _delete_session(user_id)
