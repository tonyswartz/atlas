#!/usr/bin/env python3
"""
Smart Pacing for Podcast Audio

Analyzes script text and adjusts playback speed for better listening experience:
- Questions: Slightly slower (-5%) for emphasis
- Lists/enumerations: Slightly faster (+5%) for flow
- Key statements: Add micro-pauses before important points
- Transitions: Detect and adjust pacing
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List


def analyze_paragraph_pacing(text: str) -> Dict:
    """
    Analyze paragraph text to determine optimal pacing adjustments.

    Returns:
        {
            "speed_multiplier": float,  # 1.0 = normal, 0.95 = slower, 1.05 = faster
            "add_pause_before": bool,    # Add 0.5s pause before this paragraph
            "reason": str                # Why this adjustment was made
        }
    """
    text = text.strip()

    # Default pacing
    pacing = {
        "speed_multiplier": 1.0,
        "add_pause_before": False,
        "reason": "normal"
    }

    # Detect questions (slow down for emphasis)
    if text.endswith("?"):
        pacing["speed_multiplier"] = 0.95
        pacing["reason"] = "question (slower for emphasis)"

    # Detect lists/enumerations (speed up slightly)
    list_indicators = [
        r"first[,\s]",
        r"second[,\s]",
        r"third[,\s]",
        r"one[,\s]",
        r"two[,\s]",
        r"three[,\s]",
        r"also[,\s]",
        r"additionally[,\s]"
    ]
    if any(re.search(pattern, text.lower()) for pattern in list_indicators):
        pacing["speed_multiplier"] = 1.03
        pacing["reason"] = "list item (faster for flow)"

    # Detect key statements (add pause before)
    emphasis_indicators = [
        r"^here's the key",
        r"^here's what",
        r"^the important",
        r"^now listen",
        r"^pay attention",
        r"^this is crucial",
        r"^remember this"
    ]
    if any(re.search(pattern, text.lower()) for pattern in emphasis_indicators):
        pacing["add_pause_before"] = True
        pacing["reason"] = "emphasis statement (add pause)"

    # Detect conclusions/calls-to-action (slow down)
    if any(phrase in text.lower() for phrase in ["in conclusion", "to summarize", "action step", "here's what you"]):
        pacing["speed_multiplier"] = 0.97
        pacing["add_pause_before"] = True
        pacing["reason"] = "conclusion/CTA (slower + pause)"

    return pacing


def apply_smart_pacing(paragraph_file: Path, pacing: Dict, output_file: Path = None):
    """
    Apply pacing adjustments to a paragraph audio file.

    Args:
        paragraph_file: Input audio file
        pacing: Pacing dict from analyze_paragraph_pacing()
        output_file: Output file (defaults to overwriting input)
    """
    if output_file is None:
        output_file = paragraph_file

    speed = pacing["speed_multiplier"]

    # Only apply if speed != 1.0
    if abs(speed - 1.0) < 0.01:
        return paragraph_file

    # Use tempo filter to adjust speed without changing pitch
    temp_file = paragraph_file.parent / f"{paragraph_file.stem}_paced.mp3"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(paragraph_file),
        "-af", f"atempo={speed}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(temp_file)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        print(f"⚠️  Failed to apply pacing to {paragraph_file.name}: {result.stderr}")
        return paragraph_file

    # Replace original
    temp_file.replace(output_file)
    return output_file


def add_emphasis_pause(silence_duration: float = 0.5) -> Path:
    """
    Generate a short silence file for emphasis pauses.

    Args:
        silence_duration: Duration in seconds (default: 0.5s)

    Returns:
        Path to generated silence file
    """
    from tempfile import gettempdir
    silence_file = Path(gettempdir()) / "emphasis_pause.mp3"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(silence_duration),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(silence_file)
    ]

    subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return silence_file


def process_episode_with_smart_pacing(episode_id: str, dry_run: bool = False):
    """
    Apply smart pacing to all paragraphs in an episode.

    Args:
        episode_id: Episode ID (e.g., sololaw-030)
        dry_run: If True, only analyze and report, don't modify files
    """
    import json
    import yaml

    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    config = load_config()
    episodes_base = Path(config["paths"]["episodes_dir"])

    # Find episode directory
    if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
        parts = episode_id.split("-", 2)
        podcast_name = parts[2]
        episode_dir = episodes_base / podcast_name / episode_id
    else:
        podcast_name, ep_num = episode_id.split("-", 1)
        episode_dir = episodes_base / config["podcasts"][podcast_name]["name"] / ep_num

    # Load paragraph metadata
    metadata_file = episode_dir / "paragraphs" / "paragraph_metadata.json"
    if not metadata_file.exists():
        raise FileNotFoundError(f"Paragraph metadata not found: {metadata_file}")

    with open(metadata_file) as f:
        metadata = json.load(f)

    # Load full script for context
    script_file = episode_dir / "script_approved.md"
    if not script_file.exists():
        raise FileNotFoundError(f"Script not found: {script_file}")

    print(f"🎯 Analyzing smart pacing for {episode_id}...\n")

    adjustments_made = 0
    pauses_added = 0

    for para in metadata["paragraphs"]:
        para_num = para["number"]
        para_text = para["text"]
        para_file = episode_dir / "paragraphs" / para["file"]

        # Analyze pacing
        pacing = analyze_paragraph_pacing(para_text)

        if pacing["speed_multiplier"] != 1.0 or pacing["add_pause_before"]:
            speed_pct = int((pacing["speed_multiplier"] - 1.0) * 100)
            speed_str = f"{speed_pct:+d}%" if speed_pct != 0 else "normal"
            pause_str = " + pause" if pacing["add_pause_before"] else ""

            print(f"Para {para_num:2d}: {speed_str}{pause_str} — {pacing['reason']}")
            print(f"         '{para_text[:60]}...'")

            if not dry_run:
                # Apply speed adjustment
                if pacing["speed_multiplier"] != 1.0:
                    apply_smart_pacing(para_file, pacing)
                    adjustments_made += 1

                # Note: Pause handling would be integrated into concatenation logic
                if pacing["add_pause_before"]:
                    pauses_added += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Would apply {adjustments_made} speed adjustments and {pauses_added} emphasis pauses")

    if not dry_run and adjustments_made > 0:
        print("\n⚠️  Note: You'll need to re-concatenate paragraphs and re-mix the episode for changes to take effect")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Apply smart pacing to podcast episodes")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., sololaw-030)")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't modify files")

    args = parser.parse_args()

    process_episode_with_smart_pacing(args.episode_id, args.dry_run)


if __name__ == "__main__":
    main()
