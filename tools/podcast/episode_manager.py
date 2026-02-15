#!/usr/bin/env python3
"""
Podcast Episode Manager

CLI utility for managing podcast episodes - status, retries, cleanup.

Usage:
    python tools/podcast/episode_manager.py --action list
    python tools/podcast/episode_manager.py --episode-id 20260210-170000-explore
    python tools/podcast/episode_manager.py --episode-id 20260210-170000-explore --retry script
    python tools/podcast/episode_manager.py --episode-id 20260210-170000-explore --mark-published
    python tools/podcast/episode_manager.py --action archive --before 2025-01-01
"""

import sys
import json
import yaml
import argparse
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def list_episodes(podcast_filter: str = None, status_filter: str = None):
    """List all episodes."""
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = "SELECT episode_id, podcast_name, title, status, created_at, duration_seconds FROM episodes"
    conditions = []
    params = []

    if podcast_filter:
        conditions.append("podcast_name = ?")
        params.append(podcast_filter)

    if status_filter:
        conditions.append("status = ?")
        params.append(status_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    episodes = cursor.fetchall()
    conn.close()

    if not episodes:
        print("No episodes found")
        return

    print(f"\nFound {len(episodes)} episode(s):\n")
    print(f"{'Episode ID':<30} {'Podcast':<15} {'Status':<20} {'Duration':<10} {'Title':<40}")
    print("-" * 120)

    for row in episodes:
        episode_id, podcast_name, title, status, created_at, duration = row
        duration_str = f"{duration//60}:{duration%60:02d}" if duration else "N/A"
        title_short = (title[:37] + "...") if title and len(title) > 40 else (title or "")
        print(f"{episode_id:<30} {podcast_name:<15} {status:<20} {duration_str:<10} {title_short:<40}")


def show_episode(episode_id: str):
    """Show detailed episode information."""
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"❌ Episode not found: {episode_id}")
        sys.exit(1)

    # Column names
    columns = [
        "episode_id", "podcast_name", "title", "status", "created_at",
        "idea_captured_at", "script_draft_at", "script_approved_at",
        "voice_generated_at", "mixed_at", "published_at",
        "duration_seconds", "character_count", "word_count",
        "publish_date", "audio_url", "episode_dir"
    ]

    print(f"\n📋 Episode Details:\n")
    for i, col in enumerate(columns):
        value = row[i] if row[i] else "N/A"
        print(f"  {col:<25}: {value}")

    # Load state.json for additional info
    episode_dir = Path(row[-1])  # Last column is episode_dir
    state_path = episode_dir / "state.json"

    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)

        print(f"\n📄 State File ({state_path}):\n")
        print(json.dumps(state, indent=2))


def retry_stage(episode_id: str, stage: str):
    """Retry a specific stage for an episode."""
    config = load_config()
    episodes_dir = REPO_ROOT / config["paths"]["episodes_dir"]
    episode_dir = episodes_dir / episode_id

    if not episode_dir.exists():
        print(f"❌ Episode directory not found: {episode_dir}")
        sys.exit(1)

    print(f"🔄 Retrying stage '{stage}' for episode: {episode_id}")

    if stage == "script":
        script_generator = REPO_ROOT / "tools" / "podcast" / "script_generator.py"
        subprocess.run([sys.executable, str(script_generator), "--episode-id", episode_id])

    elif stage == "tts":
        tts_synthesizer = REPO_ROOT / "tools" / "podcast" / "tts_synthesizer.py"
        subprocess.run([sys.executable, str(tts_synthesizer), "--episode-id", episode_id])

    elif stage == "mix":
        audio_mixer = REPO_ROOT / "tools" / "podcast" / "audio_mixer.py"
        subprocess.run([sys.executable, str(audio_mixer), "--episode-id", episode_id])

    else:
        print(f"❌ Unknown stage: {stage}")
        print("Available stages: script, tts, mix")
        sys.exit(1)


def mark_published(episode_id: str):
    """Mark episode as published."""
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE episodes
        SET status = 'published',
            published_at = ?
        WHERE episode_id = ?
    """, (datetime.now().isoformat(), episode_id))

    if cursor.rowcount == 0:
        print(f"❌ Episode not found: {episode_id}")
        conn.close()
        sys.exit(1)

    conn.commit()
    conn.close()

    print(f"✅ Episode marked as published: {episode_id}")

    # Also update state.json
    episodes_dir = REPO_ROOT / config["paths"]["episodes_dir"]
    episode_dir = episodes_dir / episode_id
    state_path = episode_dir / "state.json"

    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)

        state["status"] = "published"
        state["published_at"] = datetime.now().isoformat()

        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)


def archive_episodes(before_date: str):
    """Archive episodes before a certain date."""
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]
    episodes_dir = REPO_ROOT / config["paths"]["episodes_dir"]
    archive_dir = episodes_dir.parent / "podcast_episodes_archive"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT episode_id, episode_dir
        FROM episodes
        WHERE created_at < ? AND status = 'published'
    """, (before_date,))

    episodes = cursor.fetchall()
    conn.close()

    if not episodes:
        print(f"No published episodes found before {before_date}")
        return

    archive_dir.mkdir(exist_ok=True)

    print(f"Archiving {len(episodes)} episode(s) to: {archive_dir}")

    for episode_id, episode_path in episodes:
        src = Path(episode_path)
        dst = archive_dir / episode_id

        if src.exists():
            shutil.move(str(src), str(dst))
            print(f"  ✅ Archived: {episode_id}")

    print(f"\n✅ Archive complete")


def main():
    parser = argparse.ArgumentParser(description="Manage podcast episodes")
    parser.add_argument("--action", choices=["list", "archive"], help="Action to perform")
    parser.add_argument("--episode-id", help="Specific episode to show/modify")
    parser.add_argument("--podcast", choices=["explore", "sololaw", "832weekends"], help="Filter by podcast")
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--retry", choices=["script", "tts", "mix"], help="Retry a specific stage")
    parser.add_argument("--mark-published", action="store_true", help="Mark episode as published")
    parser.add_argument("--before", help="Archive episodes before this date (YYYY-MM-DD)")

    args = parser.parse_args()

    if args.action == "list":
        list_episodes(args.podcast, args.status)

    elif args.action == "archive":
        if not args.before:
            parser.error("--action archive requires --before DATE")
        archive_episodes(args.before)

    elif args.episode_id:
        if args.retry:
            import subprocess
            retry_stage(args.episode_id, args.retry)
        elif args.mark_published:
            mark_published(args.episode_id)
        else:
            show_episode(args.episode_id)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
