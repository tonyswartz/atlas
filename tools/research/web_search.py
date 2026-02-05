"""
Web search via Brave Search API. Returns titles, URLs, and snippets.

Requires BRAVE_API_KEY in environment (or .env). Free tier: 2,000 requests/month.
Outputs JSON for the Telegram tool runner.
"""

import argparse
import json
import os
import sys
import urllib.parse

import requests


BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


def main():
    ap = argparse.ArgumentParser(description="Search the web via Brave Search API.")
    ap.add_argument("--query", required=True, help="Search query.")
    ap.add_argument("--count", type=int, default=5, help="Max number of results (1-20). Default 5.")
    args = ap.parse_args()

    api_key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not api_key:
        print(json.dumps({"ok": False, "error": "BRAVE_API_KEY not set. Add it to .env."}))
        sys.exit(1)

    count = max(1, min(20, args.count))
    params = {"q": args.query}
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}

    try:
        r = requests.get(BRAVE_API_URL, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        msg = str(e)
        if hasattr(e, "response") and e.response is not None and e.response.status_code == 429:
            msg = "Rate limit exceeded (Brave free tier: 2000/month)."
        print(json.dumps({"ok": False, "error": msg}))
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "error": f"Invalid API response: {e}"}))
        sys.exit(1)

    # Brave returns { "web": { "results": [ { "title", "url", "description" }, ... ] } }
    web = data.get("web") or {}
    raw = web.get("results") or []
    results = []
    for i, hit in enumerate(raw):
        if i >= count:
            break
        results.append({
            "title": hit.get("title", ""),
            "url": hit.get("url", ""),
            "snippet": hit.get("description", ""),
        })
    print(json.dumps({"ok": True, "query": args.query, "results": results}))


if __name__ == "__main__":
    main()
