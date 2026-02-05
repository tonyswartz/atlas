#!/usr/bin/env python3
"""Telegram quick-capture handler.

Watches recent Telegram messages from Tony for commands and appends to Obsidian notes:
- /random or /randoms  -> Saved/Random Ideas.md (aggressive categorization)
- /travel or /travels  -> Saved/Travel Ideas.md (categorize by country)
- /quote(s)            -> Saved/Quotes.md
- /link(s)             -> Saved/Links.md
- /gift(s)             -> Saved/Gifts.md
- /food(s)             -> Saved/Foods.md

Model for categorization: openrouter/devstral-2-2512:free (alias: fast)

Idempotency: stores last processed Telegram message id.

Notes:
- This script uses `clawdbot message read --json` and `clawdbot message send`.
- It does not require Gateway tool access; it can run from isolated cron.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_FILE = Path("/Users/printer/atlas/logs/quick-capture-handler.log")
STATE_FILE = Path("/Users/printer/atlas/memory/quick-capture-last-id.txt")
AUTH_PROFILES = Path.home() / ".clawdbot/agents/main/agent/auth-profiles.json"

TELEGRAM_CHANNEL = "telegram"
TELEGRAM_TARGET = "8241581699"  # Tony

VAULT = Path.home() / "Library/CloudStorage/Dropbox/Obsidian/Tony's Vault"

NOTES = {
    "random": VAULT / "Saved" / "Random Ideas.md",
    "travel": VAULT / "Saved" / "Travel Ideas.md",
    "quote": VAULT / "Saved" / "Quotes.md",
    "link": VAULT / "Saved" / "Links.md",
    "gift": VAULT / "Saved" / "Gifts.md",
    "food": VAULT / "Saved" / "Foods.md",
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")


def sh(cmd: list[str], timeout: int | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return p.returncode, p.stdout


def notify_tony(text: str) -> None:
    cmd = [
        "clawdbot",
        "message",
        "send",
        "--channel",
        TELEGRAM_CHANNEL,
        "--target",
        TELEGRAM_TARGET,
        "--message",
        text,
    ]
    rc, out = sh(cmd, timeout=30)
    if rc != 0:
        log(f"notify_tony failed rc={rc}: {out[:200]}")


def load_openrouter_key() -> str | None:
    try:
        doc = json.loads(AUTH_PROFILES.read_text(encoding="utf-8"))
        prof = (doc.get("profiles") or {}).get("openrouter:default")
        if prof and prof.get("type") == "api_key":
            return prof.get("key")
    except Exception as e:
        log(f"failed to load openrouter key: {e}")
    return None


def openrouter_chat(model: str, system: str, user: str) -> str | None:
    """Minimal OpenRouter chat call; returns assistant content."""
    import urllib.request

    key = load_openrouter_key()
    if not key:
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Optional but nice for OpenRouter analytics.
            "HTTP-Referer": "https://clawd.bot",
            "X-Title": "clawdbot-quick-capture",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (((data.get("choices") or [])[0] or {}).get("message") or {}).get("content")
    except Exception as e:
        log(f"openrouter_chat failed: {e}")
        return None


def read_recent_messages(limit: int = 20) -> list[dict[str, Any]]:
    cmd = ["clawdbot", "message", "read", "--channel", TELEGRAM_CHANNEL, "--target", TELEGRAM_TARGET, "--limit", str(limit), "--json"]
    rc, out = sh(cmd, timeout=30)
    if rc != 0:
        log(f"message read failed rc={rc}: {out[:200]}")
        return []
    try:
        doc = json.loads(out)
    except Exception:
        # Sometimes CLI may print extra; try last JSON object.
        m = re.search(r"(\{.*\})\s*$", out, re.S)
        if not m:
            return []
        doc = json.loads(m.group(1))

    # Plugin responses vary; handle common shapes.
    if isinstance(doc, dict) and "messages" in doc and isinstance(doc["messages"], list):
        return doc["messages"]
    if isinstance(doc, list):
        return doc
    return []


def load_last_id() -> str:
    return STATE_FILE.read_text(encoding="utf-8").strip() if STATE_FILE.exists() else ""


def save_last_id(msg_id: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(str(msg_id), encoding="utf-8")


@dataclass
class Command:
    kind: str
    text: str


CMD_RE = re.compile(r"^\s*/(randoms?|travels?|quotes?|links?|gifts?|foods?)\b\s*(.*)$", re.I | re.S)


def parse_command(text: str) -> Command | None:
    m = CMD_RE.match(text or "")
    if not m:
        return None
    cmd = m.group(1).lower()
    rest = (m.group(2) or "").strip()

    # Normalize plural -> singular kind
    if cmd.startswith("random"):
        kind = "random"
    elif cmd.startswith("travel"):
        kind = "travel"
    elif cmd.startswith("quote"):
        kind = "quote"
    elif cmd.startswith("link"):
        kind = "link"
    elif cmd.startswith("gift"):
        kind = "gift"
    elif cmd.startswith("food"):
        kind = "food"
    else:
        return None

    return Command(kind=kind, text=rest)


def insert_bullet_under_section(note_text: str, section_heading: str, bullet: str) -> str:
    """Insert bullet directly under a markdown '## Heading' section."""
    lines = note_text.splitlines(True)
    out: list[str] = []
    inserted = False
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if not inserted and lines[i].strip() == f"## {section_heading}":
            # Ensure next line exists and is newline
            out.append(f"- {bullet}\n")
            inserted = True
        i += 1
    if not inserted:
        # Append section at end
        if not note_text.endswith("\n"):
            out.append("\n")
        out.append(f"\n## {section_heading}\n")
        out.append(f"- {bullet}\n")
    return "".join(out)


def append_capture(kind: str, raw_text: str) -> tuple[str, str]:
    """Append capture to appropriate note.

Returns (note_relative, section_used).
"""
    path = NOTES[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# {path.stem}\n\n## Inbox\n- \n", encoding="utf-8")

    now = datetime.now().strftime("%y-%m-%d")

    if kind == "travel":
        system = (
            "You categorize travel ideas by country. "
            "Return ONLY valid JSON: {\"country\": string, \"clean\": string}. "
            "country must be one of: USA, Canada, Mexico, Japan, UK, France, Italy, Spain, Portugal, Germany, Iceland, Australia / NZ, Europe (general), Other / Unknown. "
            "clean should be a concise bullet text (keep links)."
        )
        resp = openrouter_chat("openrouter/devstral-2-2512:free", system, raw_text) or ""
        try:
            obj = json.loads(resp)
            country = str(obj.get("country") or "Other / Unknown")
            clean = str(obj.get("clean") or raw_text).strip()
        except Exception:
            country, clean = "Other / Unknown", raw_text
        section = country
        bullet = f"{now} — {clean}"

    elif kind == "random":
        system = (
            "You categorize general random ideas aggressively. "
            "Return ONLY valid JSON: {\"category\": string, \"clean\": string}. "
            "category must be one of: Business / Work, Systems / Automation, Personal, Writing / Content, Legal / Swartz Law, Rotary / Community, Health / Fitness, Tech / Gear, Money, Questions to revisit. "
            "clean should be a concise bullet text (keep links)."
        )
        resp = openrouter_chat("openrouter/devstral-2-2512:free", system, raw_text) or ""
        try:
            obj = json.loads(resp)
            section = str(obj.get("category") or "Inbox (uncategorized)")
            clean = str(obj.get("clean") or raw_text).strip()
        except Exception:
            section, clean = "Inbox (uncategorized)", raw_text
        bullet = f"{now} — {clean}"

    else:
        # Simple inbox append for quote/link/gift/food
        section = "Inbox"
        bullet = f"{now} — {raw_text.strip()}"

    text = path.read_text(encoding="utf-8")
    new_text = insert_bullet_under_section(text, section, bullet)
    path.write_text(new_text, encoding="utf-8")

    note_rel = str(path.relative_to(VAULT))
    return note_rel, section


def main() -> int:
    last_id = load_last_id()
    msgs = read_recent_messages(limit=25)
    if not msgs:
        return 0

    # Find newest message that we haven't processed.
    # Messages are usually newest-first; sort by id if present.
    def msg_id(m: dict[str, Any]) -> str:
        return str(m.get("id") or m.get("messageId") or "")

    # Prefer numeric sort if possible
    def sort_key(m: dict[str, Any]) -> int:
        mid = msg_id(m)
        try:
            return int(mid)
        except Exception:
            return 0

    msgs_sorted = sorted(msgs, key=sort_key)

    # Process any new messages after last_id (in order), but stop after first command we handle.
    for m in msgs_sorted:
        mid = msg_id(m)
        if not mid:
            continue
        if last_id and sort_key({"id": mid}) <= sort_key({"id": last_id}):
            continue

        text = str(m.get("text") or m.get("message") or m.get("body") or "")
        cmd = parse_command(text)
        if not cmd:
            # Still advance last_id so we don't re-scan forever.
            save_last_id(mid)
            last_id = mid
            continue

        if not cmd.text:
            notify_tony(f"Quick-capture: I saw /{cmd.kind} but no content. Example: /{cmd.kind} your idea here")
            save_last_id(mid)
            return 0

        try:
            note_rel, section = append_capture(cmd.kind, cmd.text)
            notify_tony(f"Saved ✅ /{cmd.kind} → {note_rel} (section: {section})")
        except Exception as e:
            log(f"append_capture failed: {e}")
            notify_tony(f"Quick-capture error saving /{cmd.kind}. I logged it; try again.")

        save_last_id(mid)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
