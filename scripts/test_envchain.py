#!/usr/bin/env python3
"""
Full test that envchain (or .env) is providing all required env vars and tools work.

Run with:  envchain atlas python scripts/test_envchain.py
Or from repo root:  ./scripts/run_with_envchain.sh python scripts/test_envchain.py

Exits 0 if all required checks pass, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Required for core Atlas (Telegram bot, briefings, DB, MCP)
REQUIRED = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ID",
    "MCP",
    "BRAVE_API_KEY",
    "MINIMAX",
    "MINIMAX_GROUP_ID",
    "MINDSETLOG_DB_HOST",
    "MINDSETLOG_DB_PORT",
    "MINDSETLOG_DB_NAME",
    "MINDSETLOG_DB_USER",
    "MINDSETLOG_DB_PASSWORD",
    "MINDSETLOG_EMAIL",
    "MINDSETLOG_DB_URL",
]

# Optional (some tools use these)
OPTIONAL = [
    "OPENAI_API_KEY",
    "HELICONE_API_KEY",
    "OPENROUTER_API_KEY",
    "MINDSETLOG_URL",
    "MINDSETLOG_PASSWORD",
    "BROWSER_SERVER_PORT",
    "TELEGRAM_CHAT_ID",
]


def check_var(name: str, required: bool) -> tuple[bool, str]:
    val = os.environ.get(name, "").strip()
    if val:
        if "TOKEN" in name or "PASSWORD" in name or "KEY" in name or "SECRET" in name or "MCP" in name or "URL" in name:
            display = f"{name}=*** (len={len(val)})"
        else:
            display = f"{name}={val[:20]}..." if len(val) > 20 else f"{name}={val}"
        return True, display
    return False, f"{name}= (missing)" if required else f"{name}= (optional, unset)"


def test_required_vars() -> tuple[int, list[str]]:
    failed = 0
    lines = []
    for name in REQUIRED:
        ok, msg = check_var(name, required=True)
        if ok:
            lines.append(f"  OK   {msg}")
        else:
            lines.append(f"  FAIL {msg}")
            failed += 1
    return failed, lines


def test_optional_vars() -> list[str]:
    lines = []
    for name in OPTIONAL:
        ok, msg = check_var(name, required=False)
        lines.append(f"  {'OK   ' if ok else 'omit '} {msg}")
    return lines


def test_brave_search() -> tuple[bool, str]:
    """Quick Brave Search API call to verify BRAVE_API_KEY works."""
    api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not api_key:
        return False, "BRAVE_API_KEY not set"
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.search.brave.com/res/v1/web/search?q=test",
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
        if data.get("web") is not None:
            return True, "Brave Search API OK"
        return False, "Unexpected response shape"
    except Exception as e:
        return False, str(e)


def test_telegram_token_format() -> tuple[bool, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN not set"
    # Telegram bot tokens are numeric:hash
    if ":" in token and token.split(":")[0].isdigit():
        return True, "TELEGRAM_BOT_TOKEN format OK"
    return False, "TELEGRAM_BOT_TOKEN should be numeric:hash from BotFather"


def main() -> int:
    print("Atlas envchain / .env test\n")
    print("Required variables:")
    failed, required_lines = test_required_vars()
    for line in required_lines:
        print(line)
    print("\nOptional variables:")
    for line in test_optional_vars():
        print(line)
    print("\nTool checks:")
    ok, msg = test_telegram_token_format()
    print(f"  {'OK   ' if ok else 'FAIL '} Telegram token: {msg}")
    if not ok:
        failed += 1
    ok, msg = test_brave_search()
    print(f"  {'OK   ' if ok else 'FAIL '} Brave Search:   {msg}")
    if not ok:
        failed += 1
    print()
    if failed:
        print(f"Result: FAIL ({failed} check(s) failed)")
        return 1
    print("Result: OK (all required vars and tool checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
