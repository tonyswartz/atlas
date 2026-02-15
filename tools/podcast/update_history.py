#!/usr/bin/env python3
"""
Update Episode History

Maintains a history file per podcast in Obsidian (titles, show notes, duration, published date).
One doc per show: e.g. "Explore with Tony - Episode History.md" in vault Podcasts folder.

Usage:
    python tools/podcast/update_history.py --episode-id explore-001
"""

import sys
import json
import yaml
import argparse
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def update_history(episode_id: str):
    """
    Add episode to podcast history file.

    Args:
        episode_id: Episode ID (e.g., explore-001)
    """
    config = load_config()

    # Parse episode ID (e.g. explore-001, 832weekends-019)
    parts = episode_id.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid episode ID: {episode_id}")

    podcast_name = parts[0]
    episode_number = parts[1]

    if podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    podcast_config = config["podcasts"][podcast_name]

    # Load episode state
    episodes_dir = REPO_ROOT / config["paths"]["episodes_dir"]
    episode_dir = episodes_dir / podcast_name / episode_number
    state_path = episode_dir / "state.json"

    if not state_path.exists():
        raise FileNotFoundError(f"Episode state not found: {state_path}")

    with open(state_path) as f:
        state = json.load(f)

    # Load show notes
    show_notes_file = episode_dir / "show_notes.txt"
    show_notes = show_notes_file.read_text(encoding="utf-8") if show_notes_file.exists() else state.get("idea", "")

    title = state.get("title", episode_id)

    # Write to Obsidian vault (one doc per show)
    obsidian_base = Path(config["paths"]["obsidian_podcasts"])
    obsidian_base.mkdir(parents=True, exist_ok=True)
    history_file = obsidian_base / f"{podcast_config['name']} - Episode History.md"

    # Read existing history
    if history_file.exists():
        existing_content = history_file.read_text(encoding="utf-8")
    else:
        existing_content = f"# {podcast_config['name']} - Episode History\n\n"
        existing_content += f"**Description**: {podcast_config['description']}\n"
        existing_content += f"**Target Length**: {podcast_config['target_length']}\n"
        existing_content += f"**Tone**: {podcast_config['tone']}\n\n"
        existing_content += "---\n\n"

    # Check if episode already exists in history
    episode_marker = f"## Episode {episode_number}"
    if episode_marker in existing_content:
        print(f"ℹ️  Episode {episode_number} already in history, updating...")
        # Remove old entry
        lines = existing_content.split("\n")
        new_lines = []
        skip_until_next_episode = False

        for line in lines:
            if line.startswith(f"## Episode {episode_number}"):
                skip_until_next_episode = True
            elif line.startswith("## Episode ") and skip_until_next_episode:
                skip_until_next_episode = False
                new_lines.append(line)
            elif not skip_until_next_episode:
                new_lines.append(line)

        existing_content = "\n".join(new_lines).rstrip() + "\n\n"

    # Add new episode entry
    new_entry = f"## Episode {episode_number}: {title}\n\n"
    new_entry += f"**Published**: {state.get('uploaded_at', state.get('mixed_at', 'Not yet published'))}\n"
    new_entry += f"**Duration**: {state.get('actual_duration_seconds', 0) // 60}:{state.get('actual_duration_seconds', 0) % 60:02d}\n\n"
    new_entry += f"**Show Notes**:\n{show_notes}\n\n"
    new_entry += "---\n\n"

    # Append to history
    history_content = existing_content + new_entry

    # Write updated history
    history_file.write_text(history_content, encoding="utf-8")

    print(f"✅ Updated history: {history_file}")
    print(f"   Episode: {episode_number}")
    print(f"   Title: {title}")

    return history_file


def main():
    parser = argparse.ArgumentParser(description="Update podcast episode history")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., explore-001)")

    args = parser.parse_args()

    try:
        update_history(args.episode_id)
    except Exception as e:
        print(f"❌ Failed to update history: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
