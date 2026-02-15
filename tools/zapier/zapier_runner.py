#!/usr/bin/env python3
"""
Zapier MCP runner — standalone script called by tool_runner via subprocess.

Connects to the Zapier MCP endpoint (URL from .env MCP key), calls a single
tool, and prints the result to stdout.  Follows the GOTCHA subprocess pattern:
no direct imports from sibling packages.

Usage:
  python3 tools/zapier/zapier_runner.py --tool <name> --input <json>
  python3 tools/zapier/zapier_runner.py --list          # smoke-test: print available tools
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap .env  (script may be called from any cwd)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env")

MCP_URL = os.environ.get("MCP", "")

# Only these tool names may be called through this runner.
ALLOWED_TOOLS = {
    "gmail_create_draft",
    "google_calendar_retrieve_event_by_id",
    "google_calendar_find_events",
    "google_calendar_find_busy_periods_in_calendar",
    "google_calendar_find_calendars",
    "google_calendar_create_detailed_event",
    "google_calendar_move_event_to_another_calendar",
}


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def _list_tools() -> list[str]:
    """Return names of all tools exposed by the Zapier MCP endpoint."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(MCP_URL) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            return [t.name for t in resp.tools]


async def _call_tool(tool_name: str, tool_input: dict) -> str:
    """Connect, call one tool, return the text result."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(MCP_URL) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_input)
            # result.content is a list of ContentBlock; extract text from each
            texts = [block.text for block in result.content if hasattr(block, "text")]
            return "\n".join(texts) if texts else "(no output)"


# ---------------------------------------------------------------------------
# Pre-flight: fill in fields Zapier expects
# ---------------------------------------------------------------------------

def _enrich(tool_name: str, tool_input: dict) -> dict:
    """Ensure instructions and output_hint are present."""
    inp = dict(tool_input)  # shallow copy — don't mutate caller's dict

    # FIX: Zapier calendar tools have inverted time boundaries
    # end_time = EARLIER boundary, start_time = LATER boundary
    # Swap them so the bot can use normal conventions
    if tool_name in ("google_calendar_find_events", "google_calendar_find_busy_periods_in_calendar"):
        if "start_time" in inp and "end_time" in inp:
            inp["start_time"], inp["end_time"] = inp["end_time"], inp["start_time"]

    if not inp.get("instructions"):
        # Synthesise from the other params so Zapier has context
        params = {k: v for k, v in inp.items() if k not in ("instructions", "output_hint") and v}
        inp["instructions"] = f"Execute {tool_name.replace('_', ' ')}." + (
            f" Parameters: {json.dumps(params)}" if params else ""
        )

    if "output_hint" not in inp:
        inp["output_hint"] = "Return all available details in the result."

    return inp


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Call a Zapier MCP tool")
    parser.add_argument("--list", action="store_true", help="List available tools and exit")
    parser.add_argument("--tool", help="Tool name to call")
    parser.add_argument("--input", help="JSON-encoded input dict for the tool")
    args = parser.parse_args()

    if not MCP_URL:
        print(json.dumps({"success": False, "error": "MCP URL not set in .env"}))
        sys.exit(1)

    # --- list mode ---
    if args.list:
        names = asyncio.run(_list_tools())
        print(json.dumps({"tools": names}, indent=2))
        return

    # --- call mode ---
    if not args.tool:
        print(json.dumps({"success": False, "error": "Missing --tool"}))
        sys.exit(1)

    if args.tool not in ALLOWED_TOOLS:
        print(json.dumps({"success": False, "error": f"Tool '{args.tool}' not in allowlist"}))
        sys.exit(1)

    try:
        tool_input = json.loads(args.input or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {exc}"}))
        sys.exit(1)

    enriched = _enrich(args.tool, tool_input)
    result = asyncio.run(_call_tool(args.tool, enriched))
    print(result)


if __name__ == "__main__":
    main()
