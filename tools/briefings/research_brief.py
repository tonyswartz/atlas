#!/usr/bin/env python3
"""
Daily Research Brief - Tech + Seattle Kraken news
Delivers a detailed summary to Telegram at 3pm daily.
Tracks seen articles by topic+link so we never show the same story twice; state is pruned to last 3000.
Filters to articles published in the last 24 hours to avoid stale stories.
"""

import email.utils
import html
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

import requests

TELEGRAM_MAX_LEN = 4000
HOURS_BACK = 24  # Only show articles from the last 24 hours

# Load .env when run by cron (no shell env)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# Configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "-5254628791"  # Daily group
STATE_FILE = "/Users/printer/atlas/data/research_brief_state.json"

# Google News RSS URLs
SEARCH_URLS = {
    "Apple": "https://news.google.com/rss/search?q=Apple+company+technology+2026&hl=en-US&gl=US&ceid=US:en",
    "AI": "https://news.google.com/rss/search?q=artificial+intelligence+machine+learning+2026&hl=en-US&gl=US&ceid=US:en",
    "Bambu Lab": "https://news.google.com/rss/search?q=Bambu+Lab+3D+printing&hl=en-US&gl=US&ceid=US:en",
    "Vibe Coding": "https://news.google.com/rss/search?q=vibe+coding+software+development&hl=en-US&gl=US&ceid=US:en",
    "Seattle Kraken": "https://news.google.com/rss/search?q=Seattle+Kraken+NHL+2026&hl=en-US&gl=US&ceid=US:en"
}


def load_state():
    """Load previously seen articles (topic+link). Only new articles are shown; no repeats."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen_articles": {}, "last_check": None}


def save_state(state):
    """Save state. Prune seen_articles to last SEEN_CAP so we don't grow forever."""
    SEEN_CAP = 3000
    seen = state.get("seen_articles") or {}
    if len(seen) > SEEN_CAP:
        # Keep most recent by "found" timestamp
        by_time = sorted(seen.items(), key=lambda x: (x[1].get("found") or ""), reverse=True)
        state["seen_articles"] = dict(by_time[:SEEN_CAP])
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def strip_query_params(url: str) -> str:
    """Strip query params from URL — cleans up Google News tracking params."""
    return url.split("?")[0] if "?" in url else url


def fetch_rss(url):
    """Fetch and parse RSS feed. Extracts source name and filters to last HOURS_BACK hours."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            items = re.findall(r'<item[^>]*>(.*?)</item>', response.text, re.DOTALL)
            results = []
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=HOURS_BACK)

            # Fetch more items initially since we'll filter by date
            for item in items[:20]:
                title_match = re.search(r'<title>([^<]+)</title>', item)
                link_match = re.search(r'<link>([^<]+)</link>', item)
                # <source url="https://www.bloomberg.com">Bloomberg</source>
                source_match = re.search(r'<source\s+url="([^"]*)"[^>]*>([^<]*)</source>', item)
                # <pubDate>Sat, 15 Feb 2026 14:30:00 GMT</pubDate>
                pubdate_match = re.search(r'<pubDate>([^<]+)</pubDate>', item)

                if title_match and link_match:
                    raw_url = strip_query_params(link_match.group(1).strip())

                    # Parse publication date
                    pub_date = None
                    if pubdate_match:
                        try:
                            # email.utils.parsedate_to_datetime handles RFC 2822 format (RSS standard)
                            pub_date = email.utils.parsedate_to_datetime(pubdate_match.group(1))
                        except Exception as e:
                            print(f"  Could not parse date '{pubdate_match.group(1)}': {e}")

                    # Filter: skip if too old or no date (assume current if no date)
                    if pub_date and pub_date < cutoff:
                        continue

                    results.append({
                        "title": title_match.group(1).strip(),
                        "url": raw_url,
                        "source": source_match.group(2).strip() if source_match else "",
                        "pubdate": pub_date.isoformat() if pub_date else None
                    })

            # Return up to 10 recent articles
            return results[:10]
    except Exception as e:
        print(f"  Error fetching: {e}")
    return []



def escape_markdown(text):
    """Escape Telegram Markdown special chars so parse_mode doesn't break."""
    if not text:
        return ""
    # Telegram Markdown: _ * ` [ must be escaped
    for char in ("_", "*", "`", "["):
        text = text.replace(char, "\\" + char)
    return text


def escape_link_text(text):
    """Escape only chars that would break [text](url) in Telegram."""
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace("]", "\\]")



def clean_title(raw_title: str) -> tuple[str, str]:
    """Split 'Title - Source Name' into (title, source). Handles &amp; etc.
    Splits on last ' - ' or ' – ' (spaces required) so mid-title hyphens like 'AI-powered' survive."""
    title = html.unescape(re.sub(r'<[^>]+>', '', raw_title)).strip()
    # Split on last occurrence of " - " or " – "
    for sep in (" – ", " - "):
        idx = title.rfind(sep)
        if idx > 0:
            candidate_source = title[idx + len(sep):]
            if candidate_source and len(candidate_source) < 80:
                return title[:idx].strip(), candidate_source.strip()
    return title, ""


def format_articles(articles, max_count=5) -> list[str]:
    """Format articles as clean bullet lines: • [Title](url) — Source"""
    lines = []
    for art in articles[:max_count]:
        title, title_source = clean_title(art.get("title", ""))
        url = art.get("url", "").strip()
        # Prefer <source> tag name; fall back to source parsed from title
        source = art.get("source") or title_source
        title_safe = escape_link_text(title)
        if url:
            line = f"• [{title_safe}]({url})"
            if source:
                line += f" — {source}"
            lines.append(line)
        else:
            lines.append(f"• {escape_markdown(title)}")
    return lines


def send_telegram(message):
    """Send one message to Telegram."""
    if not TELEGRAM_TOKEN:
        print("No Telegram token configured")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("Message sent")
        else:
            print(f"Failed: {response.text}")
    except Exception as e:
        print(f"Error: {e}")


def send_telegram_chunked(full_text):
    """Send full_text in one or more messages, splitting at newlines if over limit."""
    if not full_text.strip():
        return
    if len(full_text) <= TELEGRAM_MAX_LEN:
        send_telegram(full_text)
        return
    chunks = []
    current = []
    current_len = 0
    for line in full_text.split("\n"):
        line_len = len(line) + 1
        if current_len + line_len > TELEGRAM_MAX_LEN and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        chunks.append("\n".join(current))
    for i, chunk in enumerate(chunks):
        if i > 0:
            chunk = f"🔍 *3pm Research Brief* (continued)\n\n{chunk}"
        send_telegram(chunk)
        if i < len(chunks) - 1:
            time.sleep(0.3)


def main():
    """Run research brief."""
    print(f"[{datetime.now()}] Running research brief...")
    
    state = load_state()
    all_results = {}
    new_articles = 0
    
    for topic, url in SEARCH_URLS.items():
        print(f"  Searching: {topic}")
        articles = []
        entries = fetch_rss(url)
        
        for entry in entries:
            title = entry.get('title', '')
            link = entry.get('url', '')
            
            key = f"{topic}:{link}"
            if key not in state["seen_articles"] and title:
                state["seen_articles"][key] = {
                    "topic": topic,
                    "title": title,
                    "url": link,
                    "found": datetime.now().isoformat()
                }
                articles.append(entry)
                new_articles += 1
        
        if articles:
            all_results[topic] = articles
    
    # Build message per topic to avoid truncation
    TOPIC_ORDER = ["Apple", "AI", "Bambu Lab", "Vibe Coding", "Seattle Kraken"]
    if all_results:
        date_str = datetime.now().strftime("%b %d, %Y")

        # Send one message per topic
        for i, topic in enumerate(TOPIC_ORDER):
            if topic not in all_results:
                continue

            if i == 0:
                header = f"📰 *Research Brief — {topic}* ({date_str})"
            else:
                header = f"📰 *Research Brief — {topic}*"

            lines = format_articles(all_results[topic], max_count=5)
            message = header + "\n\n" + "\n".join(lines)

            if i == len([t for t in TOPIC_ORDER if t in all_results]) - 1:
                message += f"\n\n_{new_articles} new articles total_"

            send_telegram(message)
            if i < len(TOPIC_ORDER) - 1:
                time.sleep(0.3)

        print(f"  Sent {new_articles} new articles")
    else:
        send_telegram("🔍 *3pm Research Brief* — no new articles today.")
        print("  No new articles")
    
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    print(f"[{datetime.now()}] Complete")


if __name__ == "__main__":
    main()
