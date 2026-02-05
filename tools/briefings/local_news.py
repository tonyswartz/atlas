#!/usr/bin/env python3
"""
Local News Summary Script
Summarizes news from Ellensburg, Yakima, and Seattle sources (Daily Record, Yakima Herald,
KIRO 7, Seattle Times, KING 5, KOMO). Each story is: [Headline](link): 2–3 sentence summary.
Tracks seen articles to avoid repeats. Sends to Telegram at 12pm when run by cron.
"""

import json
import os
import re
import hashlib
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import urllib.request
import urllib.error
import ssl

# Load .env when run by cron
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8241581699")

# Config
TZ = ZoneInfo("America/Los_Angeles")
STATE_FILE = Path("/Users/printer/atlas/data/local-news-state.json")
OBSIDIAN_LOG = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/News Log.md")

SOURCES = [
    {
        "name": "Daily Record (Ellensburg)",
        "url": "https://www.dailyrecordnews.com/",
        "region": "Ellensburg"
    },
    {
        "name": "Yakima Herald",
        "url": "https://www.yakimaherald.com/",
        "region": "Yakima"
    },
    {
        "name": "KIRO 7 (Seattle)",
        "url": "https://www.kiro7.com/",
        "region": "Seattle"
    },
    {
        "name": "Seattle Times",
        "url": "https://www.seattletimes.com/",
        "region": "Seattle"
    },
    {
        "name": "KING 5 (Seattle)",
        "url": "https://www.king5.com/news/",
        "region": "Seattle"
    },
    {
        "name": "KOMO News (Seattle)",
        "url": "https://komonews.com/news",
        "region": "Seattle"
    },
]

# User agents to rotate (helps with paywalls)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Googlebot/2.1 (+http://www.google.com/bot.html)",  # Sometimes helps with paywalls
]


def load_state() -> dict:
    """Load previous run state"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"last_run": None, "seen_hashes": []}


def save_state(state: dict):
    """Save run state"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_page(url: str) -> str:
    """Fetch a page with rotating user agents"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    for ua in USER_AGENTS:
        try:
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            continue
    return ""


def extract_article_summary(html: str, max_sentences: int = 3, max_chars: int = 420) -> str:
    """Extract 2–3 sentence summary from article HTML (meta description or lead paragraphs)."""
    text = ""
    # Prefer meta description or og:description
    for pattern in [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ]:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            text = m.group(1)
            break
    if not text or len(text) < 40:
        # Fallback: first substantial paragraphs
        paragraphs = re.findall(r'<p[^>]*>([^<]+)</p>', html, re.IGNORECASE)
        for p in paragraphs:
            p = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', p)).strip()
            if len(p) > 80 and not p.lower().startswith(('subscribe', 'sign in', 'advertisement')):
                text = (text + " " + p).strip()
                if len(text) > 200:
                    break
    if not text:
        return ""
    # Decode common entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = re.sub(r'\s+', ' ', text).strip()
    # Take first 2–3 sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    out = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        out.append(s)
        if len(out) >= max_sentences or sum(len(x) for x in out) >= max_chars:
            break
    summary = " ".join(out).strip()
    if len(summary) > max_chars:
        summary = summary[: max_chars].rsplit(".", 1)[0].strip() + "."
    return summary


def fetch_article_summary(url: str) -> str:
    """Fetch article page and return 2–3 sentence summary. Returns empty string on failure."""
    if not url or not url.startswith("http"):
        return ""
    html = fetch_page(url)
    return extract_article_summary(html) if html else ""


def extract_headlines(html: str, source_name: str, base_url: str) -> list:
    """Extract headlines and links from HTML"""
    articles = []
    
    # Common patterns for news article links
    patterns = [
        # Standard article links with headlines
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{20,150})</a>',
        # Headlines in h1, h2, h3 tags
        r'<h[123][^>]*><a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a></h[123]>',
        # Article titles in specific classes
        r'class=["\'][^"\']*(?:headline|title|article-title)[^"\']*["\'][^>]*>([^<]+)<',
    ]
    
    seen_titles = set()
    
    for pattern in patterns[:2]:  # Use link-based patterns
        matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
        for match in matches:
            url, title = match
            title = re.sub(r'\s+', ' ', title).strip()
            title = re.sub(r'<[^>]+>', '', title)  # Remove any HTML tags
            
            # Filter out navigation, ads, etc.
            skip_words = ['subscribe', 'sign in', 'log in', 'menu', 'search', 'advertisement', 
                          'cookie', 'privacy', 'terms', 'contact', 'about us', 'careers',
                          'newsletter', 'facebook', 'twitter', 'instagram', 'youtube',
                          'click to create', 'user account', 'daily record', 'herald-republic',
                          'yakima herald', 'santa is coming', 'norad tracks', 'kiro 7', 'king 5',
                          'seattle times', 'komo news', 'watch live', 'get the app',
                          'weather forecast', 'weather history', '7-day', 'operation crime & justice']
            
            if any(skip in title.lower() for skip in skip_words):
                continue
            
            if len(title) < 20 or len(title) > 200:
                continue
                
            if title.lower() in seen_titles:
                continue
            
            seen_titles.add(title.lower())
            
            # Normalize URL
            if url.startswith('/'):
                url = base_url.rstrip('/') + url
            elif not url.startswith('http'):
                url = base_url.rstrip('/') + '/' + url
            
            articles.append({
                "title": title,
                "url": url,
                "source": source_name
            })
    
    return articles[:10]  # Get more initially, will filter later


def extract_kiro_headlines(html: str, base_url: str = "https://www.kiro7.com") -> list:
    """Special extraction for KIRO7 when generic extractor gets few results. Tries to get URLs from article links."""
    articles = []
    seen = set()
    base_url = base_url.rstrip("/")

    # Prefer link-based extraction so we get URLs (e.g. <a href="/news/...">Headline</a>)
    link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*(?:/news/|/weather/|/article)[^"\']*)["\'][^>]*>([^<]{20,150})</a>',
        re.IGNORECASE,
    )
    for m in link_pattern.finditer(html):
        url_path, title = m.group(1), re.sub(r"\s+", " ", m.group(2).strip())
        title = re.sub(r"<[^>]+>", "", title)
        if any(s in title.lower() for s in ("subscribe", "menu", "search", "watch", "app", "cookie")):
            continue
        if len(title) < 20 or len(title) > 200 or title.lower() in seen:
            continue
        seen.add(title.lower())
        url = url_path if url_path.startswith("http") else base_url + (url_path if url_path.startswith("/") else "/" + url_path)
        articles.append({"title": title, "url": url, "source": "KIRO 7 (Seattle)"})
        if len(articles) >= 15:
            return articles

    # Fallback: headline-only from JSON-LD / data attributes
    for pattern in [r'"headline":\s*"([^"]+)"', r'<h[234][^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h', r'data-title="([^"]+)"']:
        for title in re.findall(pattern, html, re.IGNORECASE):
            title = title.strip()
            if len(title) > 20 and title.lower() not in seen:
                seen.add(title.lower())
                articles.append({"title": title, "url": "", "source": "KIRO 7 (Seattle)"})
    return articles[:15]


def escape_telegram_markdown(text: str) -> str:
    """Escape Telegram Markdown special chars in user content so parse_mode doesn't break."""
    if not text:
        return ""
    for char in ("\\", "_", "*", "`", "[", "]"):
        text = text.replace(char, "\\" + char)
    return text


def hash_article(title: str) -> str:
    """Create a hash of article title for deduplication."""
    normalized = re.sub(r'\s+', ' ', title.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def hash_url(url: str) -> str:
    """Create a hash of article URL for deduplication (same story, different headline)."""
    u = (url or "").strip().lower()
    if not u:
        return ""
    return "u" + hashlib.md5(u.encode()).hexdigest()[:11]  # prefix so no collision with title hashes


def categorize_importance(title: str) -> int:
    """Rate importance of headline (higher = more important)"""
    title_lower = title.lower()
    
    # High importance keywords
    high = ['breaking', 'urgent', 'emergency', 'killed', 'dead', 'shooting', 'crash', 
            'fire', 'arrest', 'missing', 'storm', 'flood', 'earthquake', 'evacuation',
            'homicide', 'murder', 'fatal', 'major', 'explosion']
    
    # Medium importance
    medium = ['police', 'court', 'trial', 'charged', 'investigation', 'suspect',
              'accident', 'injury', 'hospital', 'road closure', 'weather', 'snow',
              'crime', 'theft', 'robbery', 'assault', 'lawsuit', 'verdict']
    
    # Local interest
    local = ['ellensburg', 'yakima', 'kittitas', 'seattle', 'washington', 'cwu',
             'school', 'council', 'mayor', 'county', 'state']
    
    score = 0
    if any(word in title_lower for word in high):
        score += 3
    if any(word in title_lower for word in medium):
        score += 2
    if any(word in title_lower for word in local):
        score += 1
    
    return score


def fetch_news() -> dict:
    """Fetch news from all sources"""
    all_articles = []
    
    for source in SOURCES:
        html = fetch_page(source["url"])
        if not html:
            continue
        
        articles = extract_headlines(html, source["name"], source["url"])
        if "kiro" in source["url"] and len(articles) < 3:
            # Fallback: KIRO-specific extraction when generic gets few
            articles = extract_kiro_headlines(html, source["url"])
        # Fix relative URLs
        for art in articles:
            if art.get("url") and art["url"].startswith("/"):
                art["url"] = source["url"].rstrip("/") + art["url"]
        
        for art in articles:
            art["region"] = source["region"]
            art["source"] = source["name"]
        
        all_articles.extend(articles)
    
    return all_articles


def generate_summary(articles: list, state: dict) -> str:
    """Generate summary of new articles. Skips any story we've already shown (by title or URL)."""
    seen_hashes = set(state.get("seen_hashes", []))
    new_articles = []

    for art in articles:
        title_h = hash_article(art["title"])
        url_h = hash_url(art.get("url") or "")
        # Skip if we've already shown this story (same title or same URL)
        if title_h in seen_hashes or (url_h and url_h in seen_hashes):
            continue
        art["title_hash"] = title_h
        art["url_hash"] = url_h
        art["importance"] = categorize_importance(art["title"])
        new_articles.append(art)

    if not new_articles:
        return "No new stories since last check.", "No new stories since last check."

    # Sort by importance, then by region priority (Ellensburg > Yakima > Seattle)
    region_priority = {"Ellensburg": 0, "Yakima": 1, "Seattle": 2}
    new_articles.sort(key=lambda x: (-x["importance"], region_priority.get(x["region"], 3)))

    # Group by region
    by_region = {}
    for art in new_articles:
        region = art["region"]
        if region not in by_region:
            by_region[region] = []
        by_region[region].append(art)

    # Fetch 2–3 sentence summary per article we'll show (only for those with URLs)
    to_fetch = []
    for region in ["Ellensburg", "Yakima", "Seattle"]:
        if region in by_region:
            for art in by_region[region][:5]:
                if art.get("url"):
                    to_fetch.append(art)
    for art in to_fetch:
        art["summary"] = fetch_article_summary(art["url"])
        time.sleep(0.8)  # Be nice to servers

    lines = []
    lines_telegram = []
    regions_with_content = [r for r in ["Ellensburg", "Yakima", "Seattle"] if r in by_region]
    for i, region in enumerate(regions_with_content):
        lines.append(f"**{region}:**")
        lines_telegram.append(f"*{region}:*")
        for art in by_region[region][:5]:  # Top 5 per region
            importance_marker = "🔴 " if art["importance"] >= 3 else ""
            title = art["title"]
            title = re.sub(r"\s*[-–|]\s*(Daily Record|Yakima Herald|KIRO|Associated Press).*$", "", title, flags=re.IGNORECASE)
            url = art.get("url", "").strip()
            summary = (art.get("summary") or "").strip()
            title_tg = escape_telegram_markdown(title)
            summary_tg = escape_telegram_markdown(summary)
            if url and summary:
                lines.append(f"• {importance_marker}[{title}]({url}): {summary}")
                lines_telegram.append(f"• {importance_marker}[{title_tg}]({url}): {summary_tg}")
            elif url:
                lines.append(f"• {importance_marker}[{title}]({url})")
                lines_telegram.append(f"• {importance_marker}[{title_tg}]({url})")
            else:
                lines.append(f"• {importance_marker}{title}")
                lines_telegram.append(f"• {importance_marker}{title_tg}")
        if i < len(regions_with_content) - 1:
            lines.append("")
            lines_telegram.append("")

    # Record shown stories so we don't repeat: store both title and URL hashes, cap size
    to_add = []
    for art in new_articles:
        to_add.append(art["title_hash"])
        if art.get("url_hash"):
            to_add.append(art["url_hash"])
    all_hashes = list(seen_hashes) + to_add
    state["seen_hashes"] = all_hashes[-1000:]  # keep last 1000 hashes (~500 stories with title+url)

    plain = "\n".join(lines).strip()
    telegram = "\n".join(lines_telegram).strip()
    return plain, telegram


def log_to_obsidian(summary: str, article_count: int):
    """Log run to Obsidian note"""
    now = datetime.now(TZ)
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    
    entry = f"\n## {timestamp}\n\n{summary}\n\n---\n"
    
    if OBSIDIAN_LOG.exists():
        current = OBSIDIAN_LOG.read_text()
        # Insert after header
        if current.startswith("#"):
            first_newline = current.find("\n\n")
            if first_newline > 0:
                new_content = current[:first_newline+2] + entry + current[first_newline+2:]
            else:
                new_content = current + entry
        else:
            new_content = entry + current
    else:
        new_content = f"# Local News Log\n\nAutomated news summaries from local sources.\n{entry}"
    
    OBSIDIAN_LOG.write_text(new_content)


TELEGRAM_MAX_LEN = 4000  # Stay under 4096 limit


def send_telegram(message: str) -> None:
    """Send one message to Telegram. No-op if token not configured."""
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        body = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print("Message sent to Telegram", file=__import__("sys").stderr)
    except Exception as e:
        print(f"Telegram send failed: {e}", file=__import__("sys").stderr)


def send_telegram_chunked(full_text: str) -> None:
    """Send full_text to Telegram in one or more messages, splitting at newlines if over limit."""
    if not full_text.strip():
        return
    if len(full_text) <= TELEGRAM_MAX_LEN:
        send_telegram(full_text)
        return
    chunks = []
    current = []
    current_len = 0
    for line in full_text.split("\n"):
        line_len = len(line) + 1  # +1 for newline
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
            chunk = f"📰 *Local News* (continued)\n\n{chunk}"
        send_telegram(chunk)
        if i < len(chunks) - 1:
            time.sleep(0.3)  # Slight delay between messages


def main():
    state = load_state()
    last_run = state.get("last_run")
    
    # Fetch news
    articles = fetch_news()
    
    # Generate summary (plain for print/log, escaped for Telegram)
    summary_plain, summary_telegram = generate_summary(articles, state)
    
    # Update state
    state["last_run"] = datetime.now(TZ).isoformat()
    save_state(state)
    
    # Log to Obsidian
    try:
        log_to_obsidian(summary_plain, len(articles))
    except Exception as e:
        pass  # Don't fail if logging fails
    
    # Output
    now = datetime.now(TZ)
    date_str = now.strftime("%y-%m-%d")
    day_name = now.strftime("%a")
    
    if last_run:
        last_dt = datetime.fromisoformat(last_run)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=TZ)
        ago = now - last_dt
        hours = ago.total_seconds() / 3600
        if hours < 1:
            time_str = f"{int(ago.total_seconds() / 60)}m ago"
        elif hours < 24:
            time_str = f"{hours:.0f}h ago"
        else:
            time_str = f"{hours / 24:.1f}d ago"
        header = f"📰 *Local News* (since {time_str})\n\n"
    else:
        header = "📰 *Local News*\n\n"

    print(f"📰 **Local News** (since {time_str})\n" if last_run else "📰 **Local News**\n")
    print(summary_plain)

    # Send to Telegram when run by cron (e.g. 12pm); split into multiple messages if needed
    send_telegram_chunked(header + summary_telegram)


if __name__ == "__main__":
    main()
