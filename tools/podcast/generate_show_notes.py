#!/usr/bin/env python3
"""
Podcast Show Notes Generator

Extracts show notes from approved scripts for easy copy/paste into Spotify.

Usage:
    python tools/podcast/generate_show_notes.py --episode-id 20260210-170000-explore
"""

import sys
import json
import yaml
import argparse
import re
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def extract_resources(script: str) -> list:
    """Extract resources, links, and mentions from script."""
    resources = []

    # Look for common resource patterns
    lines = script.split('\n')
    in_resources = False

    for line in lines:
        stripped = line.strip()

        # Detect resource section
        if re.search(r'\[RESOURCES?.*\]', stripped, re.IGNORECASE):
            in_resources = True
            continue

        # End of resource section
        if in_resources and re.search(r'\[(CLOSE|END).*\]', stripped, re.IGNORECASE):
            break

        # Extract resources from resource section
        if in_resources and stripped and not stripped.startswith('['):
            resources.append(stripped.lstrip('- '))

    return resources


def extract_summary(script: str, max_length: int = 300) -> str:
    """Extract or generate a brief summary from the script."""
    # Remove metadata and section markers
    lines = script.split('\n')
    content_lines = []

    for line in lines:
        stripped = line.strip()
        # Skip headers, metadata, and section markers
        if (stripped.startswith('#') or
            stripped.startswith('**') or
            stripped.startswith('[') or
            stripped == '---' or
            not stripped):
            continue
        content_lines.append(line)

    # Get first few sentences
    full_text = ' '.join(content_lines)
    sentences = re.split(r'[.!?]+\s+', full_text)

    summary = ""
    for sentence in sentences[:3]:  # First 3 sentences
        if len(summary + sentence) < max_length:
            summary += sentence + ". "
        else:
            break

    return summary.strip()


def generate_show_notes(episode_id: str, podcast_name: str, script: str, state: dict) -> str:
    """
    Generate show notes from script.

    Returns formatted show notes ready for Spotify.
    """
    config = load_config()
    podcast_config = config["podcasts"][podcast_name]

    # Use the original idea as the description
    idea = state.get('idea', '')

    # Extract first paragraph for summary if no idea
    if not idea:
        idea = extract_summary(script, max_length=250)

    # Build show notes
    notes = []

    # Description
    notes.append(f"{idea}\n\n")

    # Podcast-specific footer
    if podcast_name == "explore":
        notes.append("🎙️ Explore with Tony\n")
        notes.append("New episodes every week. Subscribe wherever you listen to podcasts.\n")
    elif podcast_name == "sololaw":
        notes.append("🎙️ Solo Law Club\n")
        notes.append("Practical frameworks for building your solo law practice. New episodes weekly.\n")
    elif podcast_name == "832weekends":
        notes.append("🎙️ 832 Weekends\n")
        notes.append("Reflections on parenting and the fleeting weekends we have together. New episodes weekly.\n")

    return ''.join(notes)


def process_episode(episode_id: str):
    """Generate show notes for an episode."""
    config = load_config()

    # Parse episode ID
    podcast_name = episode_id.split("-")[-1]

    if podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    # Load episode files
    episodes_dir = REPO_ROOT / config["paths"]["episodes_dir"]
    episode_dir = episodes_dir / episode_id

    state_path = episode_dir / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Episode state not found: {state_path}")

    with open(state_path) as f:
        state = json.load(f)

    # Load approved script
    script_path = episode_dir / "script_approved.md"
    if not script_path.exists():
        raise FileNotFoundError(f"Approved script not found: {script_path}")

    script = script_path.read_text(encoding="utf-8")

    # Generate show notes
    print(f"Generating show notes for: {podcast_name}")
    print(f"Episode ID: {episode_id}")

    show_notes = generate_show_notes(episode_id, podcast_name, script, state)

    # Save to file
    output_file = episode_dir / "show_notes.txt"
    output_file.write_text(show_notes, encoding="utf-8")

    print(f"\n✅ Show notes saved to: {output_file}")
    print(f"\n{'='*60}")
    print("SHOW NOTES (copy/paste ready):")
    print('='*60)
    print(show_notes)
    print('='*60)

    return output_file


def main():
    parser = argparse.ArgumentParser(description="Generate podcast show notes")
    parser.add_argument("--episode-id", required=True, help="Episode ID")

    args = parser.parse_args()

    try:
        process_episode(args.episode_id)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
