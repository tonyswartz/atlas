#!/usr/bin/env python3
"""
HTTP/SSE wrapper for legal analysis MCP server.
Exposes the MCP server over HTTP for ChatGPT Desktop integration.

Usage:
    python3 server_http.py --port 8000

Then use ngrok to expose over HTTPS:
    ngrok http 8000
"""

import asyncio
import argparse
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

# Import the MCP app from the main server
from server import mcp


def create_sse_handler():
    """Create SSE endpoint handler for MCP."""
    async def handle_sse(request):
        async with SseServerTransport("/messages") as transport:
            await mcp.run(
                transport.read_stream,
                transport.write_stream,
                mcp.create_initialization_options()
            )
    return handle_sse


async def handle_messages(request):
    """Handle SSE messages endpoint."""
    async with SseServerTransport("/messages") as transport:
        await mcp.run(
            transport.read_stream,
            transport.write_stream,
            mcp.create_initialization_options()
        )


# Create Starlette app with SSE endpoint
app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_messages),
    ],
)


def main():
    parser = argparse.ArgumentParser(description="Legal Analysis MCP HTTP Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run server on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    print(f"🔌 Legal Analysis MCP Server starting on http://{args.host}:{args.port}")
    print(f"📁 Monitoring: ~/Library/CloudStorage/Dropbox/MCP Analysis/")
    print(f"🔒 Privacy: All sanitization happens locally")
    print()
    print("To expose via HTTPS for ChatGPT Desktop:")
    print(f"  ngrok http {args.port}")
    print()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
