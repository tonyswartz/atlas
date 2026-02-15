#!/usr/bin/env python3
"""
Podcast Chapter Markers

Adds ID3 chapter markers to MP3 files for better listener navigation.
Uses paragraph metadata to create logical chapter breaks.
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def detect_chapters(paragraphs: List[Dict], min_chapter_duration: int = 90) -> List[Dict]:
    """
    Detect logical chapter breaks from paragraph metadata.

    Creates chapters by grouping paragraphs into ~60s+ segments,
    or based on natural breaks in the content.

    Args:
        paragraphs: List of paragraph metadata dicts
        min_chapter_duration: Minimum chapter length in seconds

    Returns:
        List of chapter dicts: {title, start_time, end_time}
    """
    chapters = []
    current_chapter_start = 0.0
    current_chapter_duration = 0.0
    current_paragraphs = []

    for i, para in enumerate(paragraphs):
        para_duration = para.get("duration", 0)
        current_chapter_duration += para_duration
        current_paragraphs.append(para)

        # Create chapter break if:
        # 1. We've accumulated enough duration
        # 2. OR it's the last paragraph
        is_last = (i == len(paragraphs) - 1)
        has_min_duration = current_chapter_duration >= min_chapter_duration

        if (has_min_duration or is_last) and current_paragraphs:
            # Extract chapter title from all paragraph texts in this chapter
            all_text = " ".join([p.get("text", "") for p in current_paragraphs])
            title = extract_chapter_title(all_text, len(chapters))

            chapters.append({
                "title": title,
                "start_time": current_chapter_start,
                "end_time": current_chapter_start + current_chapter_duration,
                "paragraph_count": len(current_paragraphs)
            })

            # Reset for next chapter
            current_chapter_start += current_chapter_duration
            current_chapter_duration = 0.0
            current_paragraphs = []

    return chapters


def extract_chapter_title(text: str, chapter_num: int) -> str:
    """
    Extract a logical, concise chapter title from paragraph text.

    Uses keyword detection to assign appropriate short titles.
    """
    text_lower = text.lower()

    # First chapter is always intro
    if chapter_num == 0:
        return "Introduction"

    # Detect chapter type based on content (ordered by specificity)

    # Conclusion (very specific)
    if "that's it" in text_lower or "thanks for listening" in text_lower:
        return "Conclusion"

    # Action steps (specific phrases)
    if "action step for this week" in text_lower or "open a spreadsheet" in text_lower:
        return "Action Steps"

    # Personal story (first person narrative)
    if any(phrase in text_lower for phrase in ["i know what you're thinking", "i had the same fear", "two weeks ago, i realized", "i paused consultations"]):
        return "My Story"

    # Problem scenario
    if "sound familiar" in text_lower or "here's a scenario" in text_lower:
        return "The Problem"

    # Solution introduction
    if "solution is something called" in text_lower or "wip limits" in text_lower and "kanban" in text_lower:
        return "The Solution"

    # How-to explanation
    if "walk you through" in text_lower or ("factor" in text_lower and "capacity" in text_lower):
        return "How To Calculate"

    # Default to generic chapter number
    return f"Part {chapter_num + 1}"


def add_chapters_to_mp3(audio_file: Path, chapters: List[Dict], output_file: Path = None):
    """
    Add chapter markers to MP3 file using ffmpeg metadata.

    Args:
        audio_file: Input MP3 file
        chapters: List of chapter dicts with title, start_time, end_time
        output_file: Output file (defaults to overwriting input)
    """
    if output_file is None:
        output_file = audio_file.parent / f"{audio_file.stem}_chaptered.mp3"

    # Create ffmpeg metadata file
    metadata_file = audio_file.parent / "ffmetadata.txt"

    with open(metadata_file, "w") as f:
        f.write(";FFMETADATA1\n")

        for i, chapter in enumerate(chapters):
            start_ms = int(chapter["start_time"] * 1000)
            end_ms = int(chapter["end_time"] * 1000)

            f.write(f"\n[CHAPTER]\n")
            f.write(f"TIMEBASE=1/1000\n")
            f.write(f"START={start_ms}\n")
            f.write(f"END={end_ms}\n")
            f.write(f"title={chapter['title']}\n")

    # Run ffmpeg to add chapters
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_file),
        "-i", str(metadata_file),
        "-map_metadata", "1",
        "-codec", "copy",
        str(output_file)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # Clean up metadata file
    metadata_file.unlink()

    if result.returncode != 0:
        raise RuntimeError(f"Failed to add chapters: {result.stderr}")

    print(f"✅ Added {len(chapters)} chapters to {output_file.name}")
    for i, chapter in enumerate(chapters):
        mins = int(chapter["start_time"] // 60)
        secs = int(chapter["start_time"] % 60)
        print(f"   {i+1}. {mins:02d}:{secs:02d} - {chapter['title']}")

    return output_file


def add_chapters_to_episode(episode_id: str):
    """Add chapter markers to a podcast episode."""
    import yaml

    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    episodes_base = Path(config["paths"]["episodes_dir"])

    # Find episode directory (support both formats)
    if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
        # Old format: timestamp-based
        parts = episode_id.split("-", 2)
        podcast_name = parts[2]
        episode_dir = episodes_base / podcast_name / episode_id
    else:
        # New format: podcast-episode
        podcast_name, ep_num = episode_id.split("-", 1)
        episode_dir = episodes_base / config["podcasts"][podcast_name]["name"] / ep_num

    # Load paragraph metadata
    metadata_file = episode_dir / "paragraphs" / "paragraph_metadata.json"
    if not metadata_file.exists():
        raise FileNotFoundError(f"Paragraph metadata not found: {metadata_file}")

    with open(metadata_file) as f:
        metadata = json.load(f)

    paragraphs = metadata["paragraphs"]

    # Detect chapters
    chapters = detect_chapters(paragraphs)

    # Add chapters to final audio
    audio_file = episode_dir / "mixed_final.mp3"
    if not audio_file.exists():
        raise FileNotFoundError(f"Final audio not found: {audio_file}")

    # Create chaptered version
    chaptered_file = add_chapters_to_mp3(audio_file, chapters)

    # Replace original with chaptered version
    chaptered_file.replace(audio_file)
    print(f"✅ Replaced {audio_file.name} with chaptered version")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Add chapter markers to podcast episodes")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., sololaw-030)")

    args = parser.parse_args()
    add_chapters_to_episode(args.episode_id)


if __name__ == "__main__":
    main()
