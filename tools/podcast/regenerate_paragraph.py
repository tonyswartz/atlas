#!/usr/bin/env python3
"""
Podcast Paragraph Regenerator

Regenerates a single paragraph of an episode and re-assembles the full audio.

Usage:
    python tools/podcast/regenerate_paragraph.py --episode-id sololaw-030 --paragraph-number 3
"""

import sys
import json
import yaml
import argparse
from pathlib import Path
from datetime import datetime

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.podcast.tts_synthesizer import (
    load_config,
    call_elevenlabs,
    get_audio_duration,
    strip_script_metadata,
    concatenate_audio_files
)
from tools.podcast.pronunciation import load_pronunciation_dict, apply_pronunciation_fixes


def regenerate_paragraph(episode_id: str, paragraph_number: int):
    """Regenerate a specific paragraph and reassemble audio."""
    config = load_config()

    # Load episode directory
    episodes_base = Path(config["paths"]["episodes_dir"])

    if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
        episode_dir = episodes_base / episode_id
    else:
        parts = episode_id.split("-", 1)
        podcast_name_short = parts[0]
        episode_num = parts[1]
        podcast_full_name = None
        for name, podcast_config in config["podcasts"].items():
            if name == podcast_name_short:
                podcast_full_name = podcast_config["name"]
                break
        if not podcast_full_name:
            raise ValueError(f"Unknown podcast: {podcast_name_short}")
        episode_dir = episodes_base / podcast_full_name / episode_num

    state_path = episode_dir / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Episode state not found: {state_path}")

    with open(state_path) as f:
        state = json.load(f)

    podcast_name = state.get("podcast_name")
    if not podcast_name or podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    podcast_config = config["podcasts"][podcast_name]

    # Load script and paragraph metadata
    script_path = episode_dir / "script_approved.md"
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    script_text = script_path.read_text(encoding="utf-8")
    script_text = strip_script_metadata(script_text)

    # Apply pronunciation fixes
    pron_dict = load_pronunciation_dict()
    one_off_fixes = state.get("pronunciation_fixes", {})
    script_text, fixes_applied = apply_pronunciation_fixes(script_text, pron_dict, one_off_fixes)

    if fixes_applied:
        print(f"\nApplying pronunciation fixes...")
        for fix in fixes_applied:
            print(f"  • {fix}")

    # Load paragraph metadata
    paragraphs_dir = episode_dir / "paragraphs"
    metadata_file = paragraphs_dir / "paragraph_metadata.json"

    if not metadata_file.exists():
        raise FileNotFoundError(f"Paragraph metadata not found: {metadata_file}")

    with open(metadata_file) as f:
        metadata = json.load(f)

    # Find target paragraph
    target_para = None
    for para in metadata["paragraphs"]:
        if para["number"] == paragraph_number:
            target_para = para
            break

    if not target_para:
        raise ValueError(f"Paragraph {paragraph_number} not found in metadata")

    # Split script into paragraphs
    paragraphs_text = script_text.split('\n\n')
    if paragraph_number >= len(paragraphs_text):
        raise ValueError(f"Paragraph {paragraph_number} out of range (script has {len(paragraphs_text)} paragraphs)")

    paragraph_text = paragraphs_text[paragraph_number].strip()

    print(f"\n🔄 Regenerating paragraph {paragraph_number}")
    print(f"   Text preview: {paragraph_text[:100]}...")

    # Get voice ID
    voice_id = podcast_config.get("voice_id")
    if not voice_id or voice_id == "VOICE_ID_PLACEHOLDER":
        raise ValueError(f"Voice ID not configured for {podcast_name}")

    # Generate new paragraph audio
    para_file = paragraphs_dir / f"paragraph_{paragraph_number:03d}.mp3"

    provider = config["tts"]["provider"]
    if provider == "elevenlabs":
        call_elevenlabs(paragraph_text, voice_id, config, para_file)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")

    # Verify audio created
    if not para_file.exists() or para_file.stat().st_size == 0:
        raise RuntimeError(f"Paragraph audio not created: {para_file}")

    # Get new duration
    para_duration = get_audio_duration(para_file)

    print(f"   ✅ Regenerated {para_file.name} ({para_duration:.1f}s)")

    # Update metadata
    for para in metadata["paragraphs"]:
        if para["number"] == paragraph_number:
            para["duration"] = round(para_duration, 2)
            para["regenerated_at"] = datetime.now().isoformat()
            break

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    # Re-concatenate all paragraphs
    print(f"\n🔗 Re-concatenating all paragraphs...")

    paragraph_files = []
    for para in sorted(metadata["paragraphs"], key=lambda p: p["number"]):
        pfile = paragraphs_dir / para["file"]
        if pfile.exists():
            paragraph_files.append(pfile)

    output_file = episode_dir / "voice_raw.mp3"
    concatenate_audio_files(paragraph_files, output_file)

    # Get total duration
    total_duration = get_audio_duration(output_file)
    duration_int = int(total_duration)

    print(f"\n✅ Paragraph regeneration complete!")
    print(f"   File: {output_file}")
    print(f"   Total duration: {duration_int//60}:{duration_int%60:02d}")

    # Update state
    state["voice_generated_at"] = datetime.now().isoformat()
    state["actual_duration_seconds"] = duration_int

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Update database
    import sqlite3
    db_path = REPO_ROOT / config["paths"]["catalog_db"]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE episodes
        SET voice_generated_at = ?,
            duration_seconds = ?
        WHERE episode_id = ?
    """, (datetime.now().isoformat(), duration_int, episode_id))

    conn.commit()
    conn.close()

    # Trigger audio mixing
    print(f"\n🔄 Triggering audio mixing...")
    import subprocess
    audio_mixer = REPO_ROOT / "tools" / "podcast" / "audio_mixer.py"

    result = subprocess.run(
        [sys.executable, str(audio_mixer), "--episode-id", episode_id],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("✅ Audio mixing complete")
        if result.stdout:
            print(result.stdout)
    else:
        print("❌ Audio mixing failed")
        if result.stderr:
            print(result.stderr)


def main():
    parser = argparse.ArgumentParser(description="Regenerate a specific paragraph of a podcast episode")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., sololaw-030)")
    parser.add_argument("--paragraph-number", type=int, required=True, help="Paragraph number to regenerate")

    args = parser.parse_args()

    regenerate_paragraph(args.episode_id, args.paragraph_number)


if __name__ == "__main__":
    main()
