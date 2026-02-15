#!/usr/bin/env python3
"""
Sync Episode History from RSS

Fetches each podcast's RSS feed and writes episode number, title, and show notes
into the Obsidian episode history file. Run this to backfill or refresh history
from the live feed (Spotify/Anchor, Apple, etc.). When you publish new episodes
via the pipeline, update_history.py adds/updates that episode in the same file.

Usage:
    python tools/podcast/sync_history_from_rss.py              # all podcasts with rss_url
    python tools/podcast/sync_history_from_rss.py --podcast explore
"""

import sys
import re
import yaml
import argparse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from html import unescape

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def fetch_rss(url: str) -> str:
    """Fetch RSS feed body."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; atlas-podcast-sync/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities for plain show notes."""
    if not text:
        return ""
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_episode_item(elem) -> dict | None:
    """Extract episode number, title, description, pubDate, duration from an <item>."""
    # Title
    title_e = elem.find("title")
    title = (title_e.text or "").strip() if title_e is not None else ""

    # Episode number (itunes:episode)
    ep_e = elem.find(f"{{{ITUNES_NS}}}episode")
    if ep_e is not None and ep_e.text:
        try:
            episode_num = str(int(ep_e.text.strip()))
        except ValueError:
            episode_num = None
    else:
        episode_num = None

    # Description / show notes (may be CDATA or nested)
    desc_e = elem.find("description")
    if desc_e is not None:
        raw = (desc_e.text or "") + "".join(desc_e.itertext())
        description = strip_html(raw) if raw else ""
    else:
        description = ""

    # pubDate
    pub_e = elem.find("pubDate")
    pub_date = (pub_e.text or "").strip() if pub_e is not None else ""

    # itunes:duration (may be "HH:MM:SS" or "MM:SS" or seconds)
    dur_e = elem.find(f"{{{ITUNES_NS}}}duration")
    duration_str = (dur_e.text or "").strip() if dur_e is not None else ""

    if not title and not episode_num:
        return None

    return {
        "episode_number": episode_num,
        "title": title or f"Episode {episode_num or '?'}",
        "show_notes": description,
        "published": pub_date,
        "duration": duration_str,
    }


def get_max_episode_number_from_rss(podcast_name: str, config: dict) -> int:
    """
    Return the highest episode number on the podcast's RSS feed, or 0 if
    unavailable. Used so new episodes always use last episode number + 1.
    """
    podcasts = config.get("podcasts", {})
    if podcast_name not in podcasts:
        return 0
    rss_url = (podcasts[podcast_name].get("rss_url") or "").strip()
    if not rss_url:
        return 0
    try:
        xml_text = fetch_rss(rss_url)
        episodes = parse_rss_items(xml_text)
    except Exception:
        return 0
    max_num = 0
    for ep in episodes:
        n = ep.get("episode_number")
        if n is not None:
            try:
                max_num = max(max_num, int(n))
            except ValueError:
                pass
    return max_num


def parse_rss_items(xml_text: str) -> list[dict]:
    """Parse RSS XML and return list of episode dicts."""
    root = ET.fromstring(xml_text)
    # Handle default namespace (rss channel)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://purl.org/rss/1.0/}item")
    episodes = []
    for item in items:
        ep = parse_episode_item(item)
        if ep:
            episodes.append(ep)
    return episodes


def episode_sort_key(ep: dict):
    """Sort by episode number if present, else by published date string (newest last in feed order)."""
    num = ep.get("episode_number")
    if num is not None:
        try:
            return (0, int(num))
        except ValueError:
            pass
    return (1, ep.get("published", "") or "")


def format_duration(dur: str) -> str:
    """Convert itunes duration to M:SS or H:MM:SS for display."""
    if not dur:
        return "—"
    dur = dur.strip()
    if ":" in dur:
        return dur  # already HH:MM:SS or MM:SS
    try:
        secs = int(dur)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except ValueError:
        return dur


def build_history_md(podcast_config: dict, episodes: list[dict]) -> str:
    """Build full episode history markdown (same format as update_history)."""
    name = podcast_config["name"]
    lines = [
        f"# {name} - Episode History",
        "",
        f"**Description**: {podcast_config['description']}",
        f"**Target Length**: {podcast_config['target_length']}",
        f"**Tone**: {podcast_config['tone']}",
        "",
        "---",
        "",
    ]
    # Sort by episode number (ascending), then by publish date
    sorted_eps = sorted(episodes, key=episode_sort_key)
    for ep in sorted_eps:
        num = ep.get("episode_number") or "?"
        title = ep.get("title") or f"Episode {num}"
        lines.append(f"## Episode {num}: {title}")
        lines.append("")
        lines.append(f"**Published**: {ep.get('published') or '—'}")
        lines.append(f"**Duration**: {format_duration(ep.get('duration') or '')}")
        lines.append("")
        notes = (ep.get("show_notes") or "").strip()
        if notes:
            lines.append("**Show Notes**:")
            lines.append(notes)
        else:
            lines.append("**Show Notes**: —")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def sync_podcast_history(podcast_name: str, config: dict) -> bool:
    """Fetch RSS for one podcast and write Obsidian episode history file."""
    podcasts = config.get("podcasts", {})
    if podcast_name not in podcasts:
        print(f"❌ Unknown podcast: {podcast_name}")
        return False

    podcast_config = podcasts[podcast_name]
    rss_url = podcast_config.get("rss_url")
    if not rss_url or not rss_url.strip():
        print(f"⏭️  {podcast_config['name']}: no rss_url configured, skipping")
        return False

    rss_url = rss_url.strip()
    print(f"📡 Fetching RSS: {podcast_config['name']}")

    try:
        xml_text = fetch_rss(rss_url)
    except Exception as e:
        print(f"❌ Failed to fetch RSS: {e}")
        return False

    try:
        episodes = parse_rss_items(xml_text)
    except ET.ParseError as e:
        print(f"❌ Failed to parse RSS: {e}")
        return False

    if not episodes:
        print(f"   ⚠️  No episodes found in feed")
        episodes = []

    obsidian_base = Path(config["paths"]["obsidian_podcasts"])
    obsidian_base.mkdir(parents=True, exist_ok=True)
    history_file = obsidian_base / f"{podcast_config['name']} - Episode History.md"
    content = build_history_md(podcast_config, episodes)
    history_file.write_text(content, encoding="utf-8")

    print(f"   ✅ Wrote {len(episodes)} episodes → {history_file.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Sync episode history from podcast RSS feeds to Obsidian"
    )
    parser.add_argument(
        "--podcast",
        choices=["explore", "sololaw", "832weekends"],
        help="Sync only this podcast (default: all that have rss_url)",
    )
    args = parser.parse_args()

    config = load_config()

    if args.podcast:
        success = sync_podcast_history(args.podcast, config)
        sys.exit(0 if success else 1)
    else:
        ok = 0
        for podcast_name in config.get("podcasts", {}):
            if sync_podcast_history(podcast_name, config):
                ok += 1
        # Exit 0 if at least one had rss_url and succeeded
        sys.exit(0 if ok > 0 else 1)


if __name__ == "__main__":
    main()
