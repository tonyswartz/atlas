#!/usr/bin/env python3
"""
Paragraph Approval Orchestrator

Handles final concatenation and mixing when all paragraphs are approved.
Also provides resume functionality for interrupted workflows.

Usage:
    python tools/podcast/paragraph_orchestrator.py --finalize <episode_id>
    python tools/podcast/paragraph_orchestrator.py --resume <episode_id>
    python tools/podcast/paragraph_orchestrator.py --status <episode_id>
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.podcast.tts_synthesizer import (
    load_config, get_audio_duration, concatenate_audio_files
)
from tools.podcast.paragraph_approval_state import (
    get_episode_state, is_all_approved, cleanup_episode, get_progress_summary
)


def finalize_episode(episode_id: str):
    """
    Concatenate all approved paragraphs and trigger audio mixing.
    Called when the last paragraph is approved.
    """
    # Verify all paragraphs are approved
    if not is_all_approved(episode_id):
        print(f"❌ Not all paragraphs are approved for {episode_id}")
        print(f"   Progress: {get_progress_summary(episode_id)}")
        sys.exit(1)

    config = load_config()

    # Resolve episode directory
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

    paragraphs_dir = episode_dir / "paragraphs"
    metadata_file = paragraphs_dir / "paragraph_metadata.json"

    if not metadata_file.exists():
        raise FileNotFoundError(f"Paragraph metadata not found: {metadata_file}")

    with open(metadata_file) as f:
        metadata = json.load(f)

    # Collect all paragraph audio files in order
    paragraph_files = []
    for para in sorted(metadata["paragraphs"], key=lambda p: p["number"]):
        para_file = paragraphs_dir / para["file"]
        if not para_file.exists():
            raise FileNotFoundError(f"Paragraph audio not found: {para_file}")
        paragraph_files.append(para_file)

    print(f"🔗 Concatenating {len(paragraph_files)} approved paragraphs...")

    # Concatenate all paragraphs
    output_file = episode_dir / "voice_raw.mp3"
    concatenate_audio_files(paragraph_files, output_file)

    # Verify concatenation
    if not output_file.exists() or output_file.stat().st_size == 0:
        raise RuntimeError(f"Concatenation failed: {output_file}")

    # Get total duration
    total_duration = get_audio_duration(output_file)
    duration_int = int(total_duration)

    print(f"✅ Concatenation complete!")
    print(f"   File: {output_file}")
    print(f"   Total duration: {duration_int//60}:{duration_int%60:02d}")

    # Update episode state
    state["status"] = "voice_generated"
    state["voice_generated_at"] = datetime.now().isoformat()
    state["voice_file"] = str(output_file)
    state["actual_duration_seconds"] = duration_int
    state["tts_provider"] = config["tts"]["provider"]

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Update database
    import sqlite3
    db_path = REPO_ROOT / config["paths"]["catalog_db"]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE episodes
        SET status = 'voice_generated',
            voice_generated_at = ?,
            duration_seconds = ?
        WHERE episode_id = ?
    """, (datetime.now().isoformat(), duration_int, episode_id))

    conn.commit()
    conn.close()

    # Trigger audio mixing
    print(f"\n🎵 Triggering audio mixing...")
    audio_mixer = REPO_ROOT / "tools" / "podcast" / "audio_mixer.py"

    result = subprocess.run(
        [sys.executable, str(audio_mixer), "--episode-id", episode_id],
        capture_output=True,
        text=True,
        timeout=300
    )

    if result.returncode == 0:
        print("✅ Audio mixing complete!")
        if result.stdout:
            print(result.stdout)

        # Clean up approval state
        cleanup_episode(episode_id)
        print(f"\n🎉 Episode {episode_id} complete and ready to publish!")
    else:
        print("❌ Audio mixing failed")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)


def resume_workflow(episode_id: str):
    """
    Resume a paused paragraph approval workflow.
    Finds the next paragraph that needs generation and triggers it.
    """
    episode_state = get_episode_state(episode_id)

    if not episode_state:
        print(f"❌ No approval state found for {episode_id}")
        print("   Start a new Telegram approval workflow with:")
        print(f"   python tools/podcast/tts_synthesizer.py --telegram-approval --episode-id {episode_id}")
        sys.exit(1)

    # Check if already complete
    if is_all_approved(episode_id):
        print(f"✅ All paragraphs already approved for {episode_id}")
        print("   Triggering final mix...")
        finalize_episode(episode_id)
        return

    # Find next paragraph
    from tools.podcast.paragraph_approval_state import get_next_paragraph_number

    next_para = get_next_paragraph_number(episode_id)

    if next_para is None:
        print(f"⏸️ Workflow paused - waiting for approval")
        print(f"   Progress: {get_progress_summary(episode_id)}")
        print("   Reply to the pending Telegram message with 'good' or 'redo'")
        return

    print(f"🔄 Resuming workflow for {episode_id}")
    print(f"   Progress: {get_progress_summary(episode_id)}")
    print(f"   Generating paragraph {next_para}...")

    # Trigger next paragraph generation
    result = subprocess.run([
        sys.executable,
        str(REPO_ROOT / "tools" / "podcast" / "tts_synthesizer.py"),
        "--telegram-approval",
        "--episode-id", episode_id,
        "--paragraph-num", str(next_para)
    ], capture_output=True, text=True, timeout=120)

    if result.returncode == 0:
        print("✅ Paragraph sent to Telegram for approval")
        if result.stdout:
            print(result.stdout)
    else:
        print("❌ Paragraph generation failed")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)


def show_status(episode_id: str):
    """Show current status of paragraph approval workflow."""
    episode_state = get_episode_state(episode_id)

    if not episode_state:
        print(f"No approval state found for {episode_id}")
        return

    print(f"Episode: {episode_id}")
    print(f"Status: {episode_state['status']}")
    print(f"Progress: {get_progress_summary(episode_id)}")
    print(f"Total paragraphs: {episode_state['total_paragraphs']}")
    print(f"Started: {episode_state.get('started_at', 'Unknown')}")
    print(f"Last updated: {episode_state.get('last_updated', 'Unknown')}")
    print()

    # Show paragraph details
    print("Paragraph status:")
    for para_num_str, para_data in sorted(episode_state.get("paragraphs", {}).items(), key=lambda x: int(x[0])):
        para_num = int(para_num_str)
        status = para_data.get("status", "unknown")
        duration = para_data.get("duration")

        status_icon = {"approved": "✅", "pending": "⏳", "regenerating": "🔄"}.get(status, "❓")

        if duration:
            print(f"  {status_icon} Paragraph {para_num}: {status} ({duration:.1f}s)")
        else:
            print(f"  {status_icon} Paragraph {para_num}: {status}")


def main():
    parser = argparse.ArgumentParser(description="Paragraph approval orchestrator")
    parser.add_argument("--finalize", metavar="EPISODE_ID", help="Finalize episode (concatenate and mix)")
    parser.add_argument("--resume", metavar="EPISODE_ID", help="Resume paused workflow")
    parser.add_argument("--status", metavar="EPISODE_ID", help="Show workflow status")

    args = parser.parse_args()

    if args.finalize:
        finalize_episode(args.finalize)
    elif args.resume:
        resume_workflow(args.resume)
    elif args.status:
        show_status(args.status)
    else:
        parser.error("Specify --finalize, --resume, or --status")


if __name__ == "__main__":
    main()
