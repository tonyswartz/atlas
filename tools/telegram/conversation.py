"""
Conversation handler.

Manages per-user state and runs the Claude tool_use loop.
On first message from a user, loads memory and builds the system prompt.
Each subsequent message appends to the existing conversation history.
"""

import os
import json
import logging
import openai
from pathlib import Path

from config import load_config, get_repo_root
from tool_definitions import TOOL_DEFINITIONS
import tool_runner

REPO_ROOT = get_repo_root()
logger = logging.getLogger(__name__)

_SESSIONS_PATH = REPO_ROOT / "data" / "sessions.json"


def _load_sessions() -> dict:
    """Load persisted session messages from disk. system_prompt regenerates fresh on next use."""
    if not _SESSIONS_PATH.exists():
        return {}
    try:
        raw = json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))
        return {
            int(k): {
                "messages": v.get("messages", []),
                "system_prompt": "",
                "memory_loaded": False,
                "model_id": v.get("model_id", "ollama"),
            }
            for k, v in raw.items()
        }
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sessions() -> None:
    """Persist current session messages to disk for restart continuity."""
    try:
        _SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        out = {
            str(uid): {
                "messages": sess.get("messages", []),
                "model_id": sess.get("model_id", "ollama"),
            }
            for uid, sess in _sessions.items()
        }
        _SESSIONS_PATH.write_text(json.dumps(out), encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to persist sessions: %s", e)


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

# Deflection phrases — local 7B model sometimes refuses instead of acting
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


def _get_fallback_client():
    """Build an OpenAI-compatible client for the fallback model. Returns (client, model_name) or (None, None)."""
    config = load_config()
    fallback_cfg = config.get("fallback", {})
    if not fallback_cfg.get("enabled", False):
        return None, None
    key = os.environ.get("MINIMAX", "").strip()
    if not key:
        logger.warning("MINIMAX key not set in .env — fallback disabled")
        return None, None
    base_url = fallback_cfg.get("base_url", "https://api.minimax.chat/v1")
    model = fallback_cfg.get("model", "MiniMax-01")
    client = openai.OpenAI(base_url=base_url, api_key=key)
    return client, model


def _get_client_and_model(user_id: int):
    """Return (client, model_name) for the session's selected model. Ensures session exists."""
    config = load_config()
    model_cfg = config.get("model", {})
    if user_id not in _sessions:
        _sessions[user_id] = {
            "messages": [],
            "system_prompt": "",
            "memory_loaded": False,
            "model_id": "ollama",
        }
    model_id = _sessions[user_id].get("model_id", "ollama")
    if model_id == "minimax":
        client, model_name = _get_fallback_client()
        if client and model_name:
            return client, model_name
        logger.warning("Session set to minimax but fallback unavailable — using ollama")
    # Default: Ollama
    client = openai.OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    )
    model_name = model_cfg.get("name", "qwen2.5:7b")
    return client, model_name


def get_available_models() -> list[dict]:
    """Return list of {id, label} for models the user can select."""
    config = load_config()
    models = [{"id": "ollama", "label": "Ollama (local)"}]
    fallback_cfg = config.get("fallback", {})
    if fallback_cfg.get("enabled", False) and os.environ.get("MINIMAX", "").strip():
        models.append({
            "id": "minimax",
            "label": fallback_cfg.get("model", "MiniMax-01"),
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
        current = _sessions.get(user_id, {}).get("model_id", "ollama")
        lines = [f"Session model: {current}", ""]
        for m in available:
            mark = " ✓" if m["id"] == current else ""
            lines.append(f"• {m['id']} — {m['label']}{mark}")
        lines.append("")
        lines.append("Switch: /models ollama  or  /models minimax")
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
    _save_sessions()
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
    client, model_name = _get_client_and_model(user_id)

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
                "model_id": "ollama",
            }

    session = _sessions[user_id]

    # Append user message
    session["messages"].append({"role": "user", "content": text})
    session["messages"] = _trim_history(session["messages"])

    # Write raw incoming text for polling scripts (e.g. bambu reply handler)
    (REPO_ROOT / "memory" / "last_incoming_message.txt").write_text(text, encoding="utf-8")

    # --- Prefetch web search when user clearly asks to browse/search the web ---
    # DDG (browser_search) is free and tried first. Brave (web_search) is the paid fallback.
    if _is_web_search_intent(text):
        query = _derive_search_query(text)
        search_result = await tool_runner.execute("browser_search", {"query": query, "count": 5})
        used_tool = "browser_search"
        # If DDG failed, fall back to Brave
        try:
            parsed = json.loads(search_result)
            if not parsed.get("ok") or not parsed.get("results"):
                search_result = await tool_runner.execute("web_search", {"query": query, "count": 5})
                used_tool = "web_search"
        except (json.JSONDecodeError, KeyError):
            search_result = await tool_runner.execute("web_search", {"query": query, "count": 5})
            used_tool = "web_search"

        tool_call_id = "prefetch-web-search"
        session["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": tool_call_id,
                "type": "function",
                "function": {"name": used_tool, "arguments": json.dumps({"query": query, "count": 5})},
            }],
        })
        session["messages"].append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": search_result,
        })

    # --- Prefetch for "priorities" / "what should I focus on" ---
    # Inject kanban + journal + reminders so the first reply is always data-backed.
    if _is_priorities_intent(text):
        prefetch_ids = ["prefetch-kanban", "prefetch-journal", "prefetch-reminders"]
        prefetch_calls = [
            ("kanban_read", {}),
            ("journal_read_recent", {"days": 7}),
            ("reminders_read", {}),
        ]
        assistant_tool_calls = [
            {"id": fid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
            for fid, (name, args) in zip(prefetch_ids, prefetch_calls)
        ]
        session["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": assistant_tool_calls,
        })
        for fid, (name, args) in zip(prefetch_ids, prefetch_calls):
            result = await tool_runner.execute(name, args)
            session["messages"].append({"role": "tool", "tool_call_id": fid, "content": result})

    # --- Prefetch for "what's today" / "what do I have today" ---
    # Inject reminders so the model can summarize; it will call daily_brief/calendar if needed.
    # Skip if we already prefetched (e.g. "what are my priorities today" matched priorities).
    if _is_whats_today_intent(text) and not _is_priorities_intent(text):
        tid = "prefetch-reminders-today"
        session["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": tid,
                "type": "function",
                "function": {"name": "reminders_read", "arguments": "{}"},
            }],
        })
        session["messages"].append({
            "role": "tool",
            "tool_call_id": tid,
            "content": await tool_runner.execute("reminders_read", {}),
        })

    # --- Prefetch for "remind me to ..." ---
    # Inject current reminders so model has context when it calls reminder_add.
    if _is_remind_me_intent(text):
        tid = "prefetch-reminders-remind"
        session["messages"].append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": tid,
                "type": "function",
                "function": {"name": "reminders_read", "arguments": "{}"},
            }],
        })
        session["messages"].append({
            "role": "tool",
            "tool_call_id": tid,
            "content": await tool_runner.execute("reminders_read", {}),
        })

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

        # Try MiniMax for a natural-language answer
        reply = None
        fallback_client, fallback_model = _get_fallback_client()
        if fallback_client:
            bambu_prompt = (
                "You are a helpful assistant with access to a Bambu 3D printer.\n"
                "Answer the user's question concisely based on the data below.\n\n"
                f"[Printer Status]\n{json.dumps(live, indent=2)}\n\n"
                f"[AMS Status]\n{json.dumps(ams_data, indent=2)}\n\n"
                f"User question: {text}"
            )
            try:
                fb_resp = fallback_client.chat.completions.create(
                    model=fallback_model,
                    messages=[{"role": "user", "content": bambu_prompt}],
                    temperature=0.3,
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
        _save_sessions()
        return reply

    # --- Tool-use loop ---
    model_cfg = config.get("model", {})

    # System prompt is prepended as a message (OpenAI convention)
    # but kept out of session["messages"] so it survives history trimming
    api_messages = [{"role": "system", "content": session["system_prompt"]}] + session["messages"]

    MAX_TOOL_ROUNDS = 10
    for _round in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=model_name,
            messages=api_messages,
            tools=TOOL_DEFINITIONS,
            temperature=model_cfg.get("temperature", 0.7),
        )

        message = response.choices[0].message
        tool_calls = message.tool_calls

        # Append assistant message to history (must include tool_calls for round-trip)
        assistant_msg = {"role": "assistant", "content": message.content}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        session["messages"].append(assistant_msg)
        api_messages.append(assistant_msg)

        if not tool_calls:
            reply = message.content or "(no response)"

            # --- MiniMax fallback only when using Ollama and local model deflected ---
            session_model = session.get("model_id", "ollama")
            if session_model == "ollama" and _is_deflection(message.content):
                fallback_client, fallback_model = _get_fallback_client()
                if fallback_client and fallback_model:
                    logger.info("Local model deflected — retrying with %s", fallback_model)
                    try:
                        fb_response = fallback_client.chat.completions.create(
                            model=fallback_model,
                            messages=api_messages,
                            tools=TOOL_DEFINITIONS,
                            temperature=model_cfg.get("temperature", 0.7),
                        )
                        fb_msg = fb_response.choices[0].message
                        if fb_msg.content and not fb_msg.tool_calls:
                            reply = _strip_think(fb_msg.content)
                            logger.info("Fallback model responded successfully")
                    except Exception as e:
                        logger.warning("Fallback model failed: %s — using local response", e)

            _save_sessions()
            return reply

        # Execute each tool call and feed results back individually
        # (OpenAI requires one tool_result message per tool_call_id)
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}

            logger.info("Tool call round %d: %s(%s)", _round, tc.function.name, tc.function.arguments[:120])
            result_str = await tool_runner.execute(tc.function.name, args)

            tool_result_msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            }
            session["messages"].append(tool_result_msg)
            api_messages.append(tool_result_msg)
        # Loop continues — model sees results and may call more tools or respond

    # Exhausted max tool rounds without a text reply
    logger.warning("Tool-use loop hit %d rounds without text reply — returning last content", MAX_TOOL_ROUNDS)
    _save_sessions()
    return message.content or "(tool loop limit reached — no text response)"


def reset_session(user_id: int) -> None:
    """Clear a user's conversation state. Next message will reload memory."""
    _sessions.pop(user_id, None)
    _save_sessions()
