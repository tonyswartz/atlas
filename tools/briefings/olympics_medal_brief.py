#!/usr/bin/env python3
"""
Olympics medal brief — 2026 Winter (Milan–Cortina).
Fetches the medal table from Wikipedia, formats top 5 countries, sends to Telegram
main chat (daily group) at 8pm. Auto-skips after games end (default 2026-02-22).
"""

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Repo root for .env
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

TELEGRAM_CHAT_ID = "-5254628791"  # Daily group (main chat)
WIKI_URL = "https://en.wikipedia.org/wiki/2026_Winter_Olympics_medal_table"
DEFAULT_END_DATE = "2026-02-22"  # Milan–Cortina closing (Tony said "2nd" — actual closing is 22nd)
TELEGRAM_MAX_LEN = 4000


def get_telegram_token():
    """Prefer envchain/env; fall back to .env."""
    token = __import__("os").environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token and not token.startswith("<"):
        return token
    return None


def fetch_medal_table() -> list[dict]:
    """Fetch Wikipedia medal table and return list of {rank, country, gold, silver, bronze, total}."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    resp = requests.get(WIKI_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the medal table (wikitable with Rank, Gold, Silver, Bronze, Total)
    tables = soup.find_all("table", class_="wikitable")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        if "rank" not in header_cells and "gold" not in header_cells:
            continue

        result = []
        prev_rank = 0
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 6:
                continue
            # Typical: Rank | Country (link) | Gold | Silver | Bronze | Total
            rank_cell = cells[0].get_text(strip=True)
            if rank_cell.isdigit():
                rank = int(rank_cell)
                prev_rank = rank
            else:
                rank = prev_rank  # Tied rank (e.g. Kazakhstan row)
            # Country: second column
            country = cells[1].get_text(strip=True)
            country = re.sub(r"\s*\*$", "", country)
            if not country or "total" in country.lower():
                continue
            # Columns 2–5: Gold, Silver, Bronze, Total
            nums = []
            for c in cells[2:6]:
                t = c.get_text(strip=True)
                nums.append(int(t) if t.isdigit() else 0)
            if len(nums) < 4:
                continue
            gold, silver, bronze, total = nums[0], nums[1], nums[2], nums[3]
            result.append({
                "rank": rank,
                "country": country,
                "gold": gold,
                "silver": silver,
                "bronze": bronze,
                "total": total,
            })
        if result:
            return result

    return []


def format_message(top5: list[dict]) -> str:
    """Format top 5 for Telegram (Markdown)."""
    lines = [
        "🏅 *2026 Winter Olympics — Medal table (top 5)*",
        "Milan–Cortina",
        "",
    ]
    for row in top5:
        lines.append(
            f"{row['rank']}. *{row['country']}* — "
            f"🥇{row['gold']} 🥈{row['silver']} 🥉{row['bronze']} (Total: {row['total']})"
        )
    lines.append("")
    lines.append("_Source: Wikipedia · Daily 8pm brief_")
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    """Send one message to the main chat (daily group)."""
    token = get_telegram_token()
    if not token:
        print("TELEGRAM_BOT_TOKEN not set; skipping send", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            return True
        print(f"Telegram error: {r.status_code} {r.text}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Olympics medal brief — top 5 to Telegram")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print message only; do not send",
    )
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        metavar="YYYY-MM-DD",
        help=f"After this date, skip sending (default: {DEFAULT_END_DATE})",
    )
    args = parser.parse_args()

    end = date.fromisoformat(args.end_date)
    today = date.today()
    if today > end:
        print(f"Olympics ended on {end}; skipping send.")
        return 0

    table = fetch_medal_table()
    if not table:
        msg = "🏅 *2026 Winter Olympics* — Could not fetch medal table. Try again later."
        if args.dry_run:
            print(msg)
            return 0
        send_telegram(msg)
        return 0

    top5 = table[:5]
    body = format_message(top5)

    if args.dry_run:
        print(body)
        return 0

    if send_telegram(body):
        print(f"[{datetime.now()}] Olympics medal brief sent.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
