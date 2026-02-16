"""
Browser CLI: sends actions to the browser server (Safari via Selenium).

Requires the browser server to be running: python tools/browser/browser_server.py

Outputs JSON to stdout for the tool runner. Exit 0 on success, non-zero on failure.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _url():
    port = os.environ.get("BROWSER_SERVER_PORT", "19527")
    return f"http://127.0.0.1:{port}/"


def _post(payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    token = os.environ.get("BROWSER_SERVER_AUTH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        _url(),
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        if "Connection refused" in str(e.reason) or "refused" in str(e).lower():
            return {
                "ok": False,
                "error": "Browser server not running. Start it with: python tools/browser/browser_server.py",
            }
        return {"ok": False, "error": str(e)}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid server response: {e}"}


def main():
    ap = argparse.ArgumentParser(description="Send browser actions to the Safari server.")
    ap.add_argument("--action", required=True, choices=["navigate", "snapshot", "click", "type", "screenshot", "close", "status"])
    ap.add_argument("--url", help="For navigate: URL to open.")
    ap.add_argument("--selector", help="For click/type: CSS selector, or use --by xpath and pass XPath.")
    ap.add_argument("--by", default="css", choices=["css", "xpath", "id", "name"], help="How to find element (default: css).")
    ap.add_argument("--text", help="For type: text to type into the element.")
    ap.add_argument("--max-chars", type=int, default=50000, help="For snapshot: max chars of page content (default 50000).")
    args = ap.parse_args()

    payload = {"action": args.action}
    if args.url:
        payload["url"] = args.url
    if args.selector:
        payload["selector"] = args.selector
    if args.by:
        payload["by"] = args.by
    if args.text is not None:
        payload["text"] = args.text
    if args.max_chars:
        payload["max_chars"] = args.max_chars

    result = _post(payload)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
