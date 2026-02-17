#!/usr/bin/env python3
"""
Podcast Idea Processor

Creates episode records from user ideas and triggers script generation.

Usage:
    python tools/podcast/idea_processor.py --podcast explore --idea "My trip to Iceland"
    python tools/podcast/idea_processor.py --podcast explore --idea-file idea.txt
"""

import sys
import json
import yaml
import argparse
import sqlite3
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


def get_next_episode_number(podcast_name: str) -> int:
    """
    Get the next episode number: last episode number + 1.
    Uses the greater of (catalog DB, RSS feed) so we never reuse a number
    already on the feed.
    """
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(episode_number) FROM episodes WHERE podcast_name = ?",
        (podcast_name,),
    )
    result = cursor.fetchone()[0]
    conn.close()
    catalog_max = (result or 0)

    from tools.podcast.sync_history_from_rss import get_max_episode_number_from_rss
    rss_max = get_max_episode_number_from_rss(podcast_name, config)

    last_episode = max(catalog_max, rss_max)
    return last_episode + 1


def create_episode(podcast_name: str, idea: str, title: str = None):
    """
    Create episode record and directory structure.

    Args:
        podcast_name: Name of podcast (explore, sololaw, 832weekends)
        idea: User's episode idea text
        title: Optional episode title (defaults to truncated idea)

    Returns:
        episode_id: Created episode ID
    """
    config = load_config()

    if podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    podcast_config = config["podcasts"][podcast_name]

    # Get next episode number
    episode_number = get_next_episode_number(podcast_name)

    # Generate episode ID: {podcast_name}-{number}
    timestamp = datetime.now()
    episode_id = f"{podcast_name}-{episode_number:03d}"

    # Create nested episode directory in Obsidian: Podcasts/{display_name}/{number}/
    episodes_dir = Path(config["paths"]["episodes_dir"])
    podcast_dir = episodes_dir / podcast_config["name"]
    episode_dir = podcast_dir / f"{episode_number:03d}"
    episode_dir.mkdir(parents=True, exist_ok=True)

    # Generate title if not provided (truncate idea to 50 chars)
    if not title:
        title = idea[:50] + "..." if len(idea) > 50 else idea

    # Create initial state
    state = {
        "episode_id": episode_id,
        "podcast_name": podcast_name,
        "title": title,
        "status": "idea_captured",
        "created_at": timestamp.isoformat(),
        "idea": idea,
    }

    # Save state.json
    state_path = episode_dir / "state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Save idea.txt
    idea_path = episode_dir / "idea.txt"
    idea_path.write_text(idea, encoding="utf-8")

    print(f"✅ Episode created: {episode_id}")
    print(f"   Episode number: {episode_number:03d}")
    print(f"   Directory: {episode_dir}")
    print(f"   Title: {title}")

    # Add to database
    db_path = REPO_ROOT / config["paths"]["catalog_db"]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO episodes (
            episode_id,
            podcast_name,
            episode_number,
            title,
            status,
            created_at,
            idea_captured_at,
            episode_dir
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        episode_id,
        podcast_name,
        episode_number,
        title,
        "idea_captured",
        timestamp.isoformat(),
        timestamp.isoformat(),
        str(episode_dir),
    ))

    conn.commit()
    conn.close()

    print(f"✅ Added to database: {db_path}")

    return episode_id


def trigger_script_generation(episode_id: str):
    """Trigger script generation for an episode."""
    print(f"\n🔄 Triggering script generation...")

    script_generator = REPO_ROOT / "tools" / "podcast" / "script_generator.py"

    import subprocess
    result = subprocess.run(
        [sys.executable, str(script_generator), "--episode-id", episode_id],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("✅ Script generation complete")
        print(result.stdout)

        # Update database status to script_draft
        config = load_config()
        db_path = REPO_ROOT / config["paths"]["catalog_db"]
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE episodes
            SET status = 'script_draft',
                script_draft_at = ?
            WHERE episode_id = ?
        """, (datetime.now().isoformat(), episode_id))

        conn.commit()
        conn.close()
    else:
        print("❌ Script generation failed")
        print(result.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Create podcast episode from user idea")
    parser.add_argument(
        "--podcast",
        required=True,
        choices=["explore", "sololaw", "832weekends"],
        help="Which podcast this episode is for"
    )
    parser.add_argument(
        "--idea",
        help="Episode idea text (use --idea-file for longer text)"
    )
    parser.add_argument(
        "--idea-file",
        type=Path,
        help="Read idea from file"
    )
    parser.add_argument(
        "--title",
        help="Episode title (defaults to truncated idea)"
    )
    parser.add_argument(
        "--no-generate",
        action="store_true",
        help="Don't trigger script generation (just create episode)"
    )

    args = parser.parse_args()

    # Get idea text
    if args.idea:
        idea = args.idea
    elif args.idea_file:
        if not args.idea_file.exists():
            print(f"❌ File not found: {args.idea_file}")
            sys.exit(1)
        idea = args.idea_file.read_text(encoding="utf-8").strip()
    else:
        parser.error("Either --idea or --idea-file required")

    # Create episode
    episode_id = create_episode(args.podcast, idea, args.title)

    # Trigger script generation unless --no-generate
    if not args.no_generate:
        trigger_script_generation(episode_id)
    else:
        print(f"\nℹ️  Skipping script generation (use --episode-id {episode_id} to generate later)")


if __name__ == "__main__":
    main()
