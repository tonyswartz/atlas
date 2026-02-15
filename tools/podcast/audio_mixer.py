#!/usr/bin/env python3
"""
Podcast Audio Mixer

Adds music bed under voice track using ffmpeg.

Usage:
    python tools/podcast/audio_mixer.py --episode-id 20260210-170000-explore
    python tools/podcast/audio_mixer.py --test --voice voice.mp3 --music music.mp3
"""

import sys
import json
import yaml
import argparse
import sqlite3
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import urllib.request

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def mix_audio(voice_file: Path, music_files: list, output_file: Path, duration: float, config: dict, episode_metadata: dict = None):
    """
    Mix voice and music using ffmpeg.

    Args:
        voice_file: Path to voice audio
        music_files: List of music bed paths (will be concatenated if multiple)
        output_file: Where to save mixed audio
        duration: Duration of voice audio in seconds
        config: Audio configuration from podcast.yaml
    """
    if not voice_file.exists():
        raise FileNotFoundError(f"Voice file not found: {voice_file}")

    # Convert single file to list for consistent handling
    if isinstance(music_files, (str, Path)):
        music_files = [music_files]

    # Validate all music files exist
    music_paths = []
    for music_file in music_files:
        music_path = Path(music_file) if isinstance(music_file, str) else music_file
        if not music_path.exists():
            raise FileNotFoundError(f"Music bed not found: {music_path}")
        music_paths.append(music_path)

    audio_config = config["audio"]

    # Calculate fade times and outro
    voice_volume = audio_config.get("voice_volume", 1.0)
    music_volume = audio_config["music_volume"]
    fade_in = audio_config["fade_in_seconds"]
    fade_out = audio_config["fade_out_seconds"]
    music_outro = audio_config.get("music_outro_seconds", 5)  # Music continues after voice ends
    silence_buffer = 2.0  # Extra seconds of silence after fade completes

    # Total duration includes voice + outro + silence buffer
    total_duration = duration + music_outro + silence_buffer
    fade_out_start = max(0, total_duration - fade_out)

    print(f"Mixing audio...")
    print(f"  Voice: {voice_file.name}")
    print(f"  Music tracks: {len(music_paths)}")
    for i, mp in enumerate(music_paths, 1):
        print(f"    {i}. {mp.name}")
    print(f"  Duration: {int(duration)//60}:{int(duration)%60:02d}")
    print(f"  Voice volume: {voice_volume}x (boost)")
    print(f"  Music volume: {music_volume}x")
    print(f"  Fade in/out: {fade_in}s / {fade_out}s")

    # Build ffmpeg command
    # Strategy:
    # 1. If multiple music files: concatenate them seamlessly
    # 2. If concatenated music is shorter than voice: loop it
    # 3. Apply volume, fades, and mix with voice

    if len(music_paths) == 1:
        # Single music file - use existing logic
        music_file = music_paths[0]

        # Get music bed duration
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(music_file)
            ],
            capture_output=True,
            text=True,
        )
        music_duration = float(result.stdout.strip()) if result.returncode == 0 else 0

        # If music is shorter than total duration (voice + outro), loop it with crossfades
        if music_duration > 0 and music_duration < total_duration:
            loops_needed = int((total_duration / music_duration) + 1)
            crossfade_duration = 2  # 2 second crossfade between loops
            print(f"  Looping music {loops_needed}x to cover {int(total_duration)}s (voice: {int(duration)}s + outro: {music_outro}s)")
            print(f"  Using {crossfade_duration}s crossfades between loops")

            # Create looped music with crossfades using acrossfade filter
            # Build filter graph for crossfading multiple loops
            looped_music = output_file.parent / "music_looped.mp3"

            # Build input list
            inputs = []
            for i in range(loops_needed):
                inputs.extend(["-i", str(music_file)])

            # Build filter for crossfading
            # For N inputs, we need N-1 crossfades
            if loops_needed == 1:
                # No crossfade needed
                filter_graph = "[0:a]"
            else:
                filter_parts = []
                current_stream = "[0:a]"
                for i in range(1, loops_needed):
                    next_stream = f"[{i}:a]"
                    output_stream = f"[cf{i}]" if i < loops_needed - 1 else ""
                    filter_parts.append(f"{current_stream}{next_stream}acrossfade=d={crossfade_duration}:c1=tri:c2=tri{output_stream}")
                    current_stream = f"[cf{i}]" if i < loops_needed - 1 else ""
                filter_graph = ";".join(filter_parts)

            concat_result = subprocess.run([
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_graph,
                "-c:a", "libmp3lame",
                "-b:a", audio_config["final_bitrate"],
                str(looped_music)
            ], capture_output=True, text=True, timeout=60)

            if concat_result.returncode != 0:
                raise RuntimeError(f"Music crossfade failed: {concat_result.stderr}")

            # Use the looped music file
            # Pad voice with silence for outro + silence buffer
            # Fade out music starting at voice end over the entire outro duration
            # This leaves silence_buffer seconds of silence after fade completes
            music_fade_start = duration  # Start fade when voice ends
            voice_padding = music_outro + silence_buffer
            filter_complex = (
                f"[0:a]apad=pad_dur={voice_padding},volume={voice_volume}[voice];"
                f"[1:a]atrim=end={total_duration},"
                f"volume={music_volume},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={music_fade_start}:d={music_outro}:curve=tri[music];"
                f"[voice][music]amix=inputs=2:duration=first"
            )

            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(voice_file),
                "-i", str(looped_music),
                "-filter_complex", filter_complex,
                "-c:a", "libmp3lame",
                "-b:a", audio_config["final_bitrate"],
                "-ar", str(audio_config["sample_rate"]),
            ]

            # Clean up looped music after mixing
            cleanup_files = [looped_music]
        else:
            # Music is longer than total duration, trim it
            # Pad voice with silence for outro + silence buffer
            # Fade out music starting at voice end over the entire outro duration
            # This leaves silence_buffer seconds of silence after fade completes
            music_fade_start = duration  # Start fade when voice ends
            voice_padding = music_outro + silence_buffer
            filter_complex = (
                f"[0:a]apad=pad_dur={voice_padding},volume={voice_volume}[voice];"
                f"[1:a]atrim=end={total_duration},"
                f"volume={music_volume},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={music_fade_start}:d={music_outro}:curve=tri[music];"
                f"[voice][music]amix=inputs=2:duration=first"
            )

            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(voice_file),
                "-i", str(music_file),
                "-filter_complex", filter_complex,
                "-c:a", "libmp3lame",
                "-b:a", audio_config["final_bitrate"],
                "-ar", str(audio_config["sample_rate"]),
            ]

            cleanup_files = []

        # Add MP3 metadata tags if provided
        if episode_metadata:
            cmd.extend([
                "-metadata", f"title={episode_metadata.get('title', 'Podcast Episode')}",
                "-metadata", f"artist={episode_metadata.get('podcast_name', 'Unknown Podcast')}",
                "-metadata", f"album={episode_metadata.get('podcast_name', 'Unknown Podcast')}",
                "-metadata", f"comment={episode_metadata.get('episode_id', '')}",
            ])

        cmd.append(str(output_file))
    else:
        # Multiple music files - concatenate them
        print(f"  Concatenating {len(music_paths)} music tracks...")

        # Get total duration of all music files
        total_music_duration = 0
        for music_path in music_paths:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(music_path)
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                total_music_duration += float(result.stdout.strip())

        print(f"  Total music duration: {int(total_music_duration)}s")

        # Build input arguments for all music files
        input_args = ["-i", str(voice_file)]
        for music_path in music_paths:
            input_args.extend(["-i", str(music_path)])

        # Build filter complex for concatenation
        # Concatenate all music tracks: [1:a][2:a][3:a]concat=n=3:v=0:a=1[musiccat]
        concat_inputs = "".join([f"[{i+1}:a]" for i in range(len(music_paths))])

        # If concatenated music is shorter than voice, loop it
        if total_music_duration > 0 and total_music_duration < duration:
            loops_needed = int((duration / total_music_duration) + 1)
            print(f"  Looping concatenated music {loops_needed}x to cover {int(duration)}s")
            filter_complex = (
                f"[0:a]volume={voice_volume}[voice];"
                f"{concat_inputs}concat=n={len(music_paths)}:v=0:a=1[musiccat];"
                f"[musiccat]aloop=loop={loops_needed}:size={int(total_music_duration * 44100)},"
                f"volume={music_volume},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out}[music];"
                f"[voice][music]amix=inputs=2:duration=first"
            )
        else:
            filter_complex = (
                f"[0:a]volume={voice_volume}[voice];"
                f"{concat_inputs}concat=n={len(music_paths)}:v=0:a=1[musiccat];"
                f"[musiccat]volume={music_volume},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out}[music];"
                f"[voice][music]amix=inputs=2:duration=first"
            )

        cmd = [
            "ffmpeg",
            "-y",
            *input_args,
            "-filter_complex", filter_complex,
            "-c:a", "libmp3lame",
            "-b:a", audio_config["final_bitrate"],
            "-ar", str(audio_config["sample_rate"]),
        ]

        # Add MP3 metadata tags if provided
        if episode_metadata:
            cmd.extend([
                "-metadata", f"title={episode_metadata.get('title', 'Podcast Episode')}",
                "-metadata", f"artist={episode_metadata.get('podcast_name', 'Unknown Podcast')}",
                "-metadata", f"album={episode_metadata.get('podcast_name', 'Unknown Podcast')}",
                "-metadata", f"comment={episode_metadata.get('episode_id', '')}",
            ])

        cmd.append(str(output_file))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")

        print(f"✅ Mixed audio saved to: {output_file}")

        # Clean up temporary files (looped music, etc.)
        if 'cleanup_files' in locals():
            for cleanup_file in cleanup_files:
                if cleanup_file.exists():
                    cleanup_file.unlink()

        # Apply loudness normalization if enabled
        if audio_config.get("loudness_normalize", False):
            print(f"\n📊 Applying loudness normalization...")
            normalize_loudness(output_file, audio_config)

    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out after 5 minutes")


def normalize_loudness(audio_file: Path, audio_config: dict):
    """
    Apply loudness normalization to match professional podcast standards.
    Uses ffmpeg's loudnorm filter with two-pass processing for accurate results.
    """
    import json
    import tempfile

    target_lufs = audio_config.get("target_lufs", -16.0)
    target_lra = audio_config.get("target_lra", 7.0)
    target_tp = audio_config.get("target_tp", -1.5)

    print(f"  Target: {target_lufs} LUFS (LRA: {target_lra}, TP: {target_tp} dB)")

    # First pass: Measure current loudness
    cmd_measure = [
        "ffmpeg",
        "-i", str(audio_file),
        "-af", f"loudnorm=I={target_lufs}:LRA={target_lra}:TP={target_tp}:print_format=json",
        "-f", "null",
        "/dev/null"
    ]

    try:
        result = subprocess.run(
            cmd_measure,
            capture_output=True,
            text=True,
            timeout=60
        )

        # Extract JSON from stderr (ffmpeg outputs to stderr)
        stderr = result.stderr
        json_start = stderr.rfind('{')
        json_end = stderr.rfind('}') + 1

        if json_start == -1 or json_end == 0:
            print("  ⚠️  Could not measure loudness, skipping normalization")
            return

        measured = json.loads(stderr[json_start:json_end])

        input_i = measured.get("input_i")
        input_tp = measured.get("input_tp")
        input_lra = measured.get("input_lra")
        input_thresh = measured.get("input_thresh")

        print(f"  Current: {input_i} LUFS")
        print(f"  Adjusting to match professional podcasts...")

        # Second pass: Apply normalization with measured values
        temp_file = audio_file.with_suffix('.normalized.mp3')

        cmd_normalize = [
            "ffmpeg",
            "-y",
            "-i", str(audio_file),
            "-af", (
                f"loudnorm=I={target_lufs}:LRA={target_lra}:TP={target_tp}:"
                f"measured_I={input_i}:measured_LRA={input_lra}:"
                f"measured_TP={input_tp}:measured_thresh={input_thresh}:"
                f"linear=true:print_format=summary"
            ),
            "-map_metadata", "0",  # Preserve metadata from input
            "-c:a", "libmp3lame",
            "-b:a", audio_config["final_bitrate"],
            "-ar", str(audio_config["sample_rate"]),
            str(temp_file)
        ]

        result = subprocess.run(
            cmd_normalize,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"  ⚠️  Normalization failed: {result.stderr}")
            return

        # Replace original with normalized version
        import shutil
        shutil.move(str(temp_file), str(audio_file))

        print(f"  ✅ Normalized to {target_lufs} LUFS")

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        print(f"  ⚠️  Normalization error: {e}")


def generate_show_notes(episode_id: str, episode_dir: Path, podcast_name: str, state: dict):
    """Generate show notes from approved script."""
    import re

    print(f"\n📝 Generating show notes...")

    # Load approved script
    script_path = episode_dir / "script_approved.md"
    if not script_path.exists():
        print(f"   ⚠️  Script not found, skipping show notes")
        return

    script = script_path.read_text(encoding="utf-8")

    # Use the original idea as the description
    idea = state.get('idea', '')

    # Extract first paragraph for summary if no idea
    if not idea:
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

        # Get first 2-3 sentences
        full_text = ' '.join(content_lines)
        sentences = re.split(r'[.!?]+\s+', full_text)
        idea = ""
        for sentence in sentences[:2]:
            if len(idea + sentence) < 250:
                idea += sentence + ". "
            else:
                break
        idea = idea.strip()

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

    show_notes_text = ''.join(notes)

    # Save to file
    output_file = episode_dir / "show_notes.txt"
    output_file.write_text(show_notes_text, encoding="utf-8")

    print(f"   ✅ Created: show_notes.txt ({len(show_notes_text)} chars)")
    print(f"   📋 Copy/paste ready for Spotify")


def export_to_obsidian(episode_id: str, episode_dir: Path, podcast_name: str, state: dict):
    """
    Export episode files to Obsidian vault.

    Copies script and audio to: ~/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/{podcast_name}/{episode_id}/
    """
    obsidian_base = Path.home() / "Library" / "CloudStorage" / "Dropbox" / "Obsidian" / "Tony's Vault" / "Podcasts"

    # Create podcast subfolder
    podcast_folder = obsidian_base / podcast_name
    # Extract episode number from episode_id (e.g., "explore-019" -> "019")
    episode_number = episode_id.split('-')[-1]
    episode_folder = podcast_folder / episode_number
    episode_folder.mkdir(parents=True, exist_ok=True)

    print(f"\n📝 Exporting to Obsidian vault...")
    print(f"   Destination: {episode_folder}")

    # Check if episode_dir is already the Obsidian vault location
    if episode_dir.resolve() == episode_folder.resolve():
        print(f"   ℹ️  Files already in Obsidian vault - skipping copy")
    else:
        # Copy script (approved version)
        script_file = episode_dir / "script_approved.md"
        if script_file.exists():
            shutil.copy(script_file, episode_folder / "script_approved.md")
            print(f"   ✅ Copied: script_approved.md")
        else:
            print(f"   ⚠️  Script not found: {script_file}")

        # Copy final audio
        audio_file = episode_dir / "mixed_final.mp3"
        if audio_file.exists():
            shutil.copy(audio_file, episode_folder / "mixed_final.mp3")
            print(f"   ✅ Copied: mixed_final.mp3 ({audio_file.stat().st_size / (1024*1024):.1f} MB)")
        else:
            print(f"   ⚠️  Audio not found: {audio_file}")

        # Copy show notes
        show_notes_file = episode_dir / "show_notes.txt"
        if show_notes_file.exists():
            shutil.copy(show_notes_file, episode_folder / "show_notes.txt")
            print(f"   ✅ Copied: show_notes.txt")
        else:
            print(f"   ⚠️  Show notes not found: {show_notes_file}")

    # Create episode metadata markdown file
    metadata_file = episode_folder / "metadata.md"
    with open(metadata_file, "w") as f:
        f.write(f"# {state.get('title', episode_id)}\n\n")
        f.write(f"**Podcast**: {podcast_name}\n")
        f.write(f"**Episode ID**: {episode_id}\n")
        f.write(f"**Created**: {state.get('created_at', 'N/A')}\n")
        f.write(f"**Duration**: {state.get('actual_duration_seconds', 0) // 60}:{state.get('actual_duration_seconds', 0) % 60:02d}\n")
        f.write(f"**Word Count**: {state.get('word_count', 'N/A')}\n\n")
        f.write(f"## Original Idea\n\n")
        f.write(f"{state.get('idea', 'N/A')}\n\n")
        f.write(f"## Files\n\n")
        f.write(f"- [[script_approved.md|Script]]\n")
        f.write(f"- [[mixed_final.mp3|Final Audio]]\n")
        f.write(f"- [[show_notes.txt|Show Notes]]\n\n")

    print(f"   ✅ Created: metadata.md")
    print(f"✅ Obsidian export complete!")

    return episode_folder


def send_telegram(message: str, audio_file: Path, chat_id: str, title: str = "Podcast Episode", performer: str = "Podcast", episode_id: str = None) -> dict:
    """Send message with audio file to Telegram. Returns dict with success and message_id."""
    from tools.common.credentials import get_telegram_token

    token = get_telegram_token()
    if not token:
        print("Warning: TELEGRAM_BOT_TOKEN not found, skipping Telegram notification")
        return {"success": False, "message_id": None}

    # First send the text message
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return {"success": False, "message_id": None}
            text_response = json.loads(resp.read())
            text_message_id = text_response.get("result", {}).get("message_id")
    except Exception as e:
        print(f"Failed to send text message: {e}")
        return {"success": False, "message_id": None}

    # Then send the audio file
    if not audio_file.exists():
        print(f"Warning: Audio file not found: {audio_file}")
        return {"success": False, "message_id": None}

    # Use curl for multipart/form-data upload (simpler than urllib multipart)
    audio_url = f"https://api.telegram.org/bot{token}/sendAudio"

    try:
        result = subprocess.run([
            "curl", "-s",
            "-F", f"chat_id={chat_id}",
            "-F", f"audio=@{audio_file}",
            "-F", f"title={title}",
            "-F", f"performer={performer}",
            audio_url
        ], capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            response = json.loads(result.stdout)
            if response.get("ok"):
                audio_message_id = response.get("result", {}).get("message_id")
                print("✅ Audio file sent to Telegram")

                # Store message ID for reply detection (use text message ID as it's more likely to be replied to)
                if episode_id and text_message_id:
                    prompts_file = REPO_ROOT / "data" / "podcast_prompts.json"
                    try:
                        with open(prompts_file) as f:
                            prompts_data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError):
                        prompts_data = {"prompts": {}, "script_previews": {}, "final_audio": {}}

                    if "final_audio" not in prompts_data:
                        prompts_data["final_audio"] = {}

                    prompts_data["final_audio"][str(text_message_id)] = {
                        "episode_id": episode_id,
                        "sent_at": datetime.now().isoformat(),
                        "chat_id": str(chat_id)
                    }

                    with open(prompts_file, "w") as f:
                        json.dump(prompts_data, f, indent=2)

                    print(f"📝 Stored audio message ID: {text_message_id}")

                return {"success": True, "message_id": text_message_id}
            else:
                print(f"Failed to send audio: {response.get('description', 'Unknown error')}")
                return {"success": False, "message_id": None}
        else:
            print(f"curl failed: {result.stderr}")
            return {"success": False, "message_id": None}

    except Exception as e:
        print(f"Failed to send audio file: {e}")
        return {"success": False, "message_id": None}


def mix_episode(episode_id: str):
    """Mix audio for an episode."""
    config = load_config()

    # Load episode state to get podcast name (support both old and new formats)
    episodes_base = Path(config["paths"]["episodes_dir"])

    if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
        # Old format: "20260210-170000-explore"
        episode_dir = episodes_base / episode_id
    else:
        # New format: "sololaw-030" -> "Solo Law Club/030"
        parts = episode_id.split("-", 1)
        podcast_name_short = parts[0]
        episode_num = parts[1]
        # Map short name to full name
        podcast_full_name = None
        for name, podcast_config in config["podcasts"].items():
            if name == podcast_name_short:
                podcast_full_name = podcast_config["name"]
                break
        if not podcast_full_name:
            raise ValueError(f"Unknown podcast short name: {podcast_name_short}")
        episode_dir = episodes_base / podcast_full_name / episode_num

    state_path = episode_dir / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Episode state not found: {state_path}")

    with open(state_path) as f:
        state = json.load(f)

    # Get podcast name from state
    podcast_name = state.get("podcast_name")
    if not podcast_name:
        raise ValueError(f"podcast_name missing in state.json")

    if podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    podcast_config = config["podcasts"][podcast_name]

    # Check for voice file
    voice_file = episode_dir / "voice_raw.mp3"
    if not voice_file.exists():
        raise FileNotFoundError(f"Voice file not found: {voice_file}")

    # Get music bed paths (support both single file and array)
    music_beds = podcast_config.get("music_beds")
    if not music_beds:
        # Fallback to old single file config
        music_bed = podcast_config.get("music_bed")
        if not music_bed:
            raise ValueError(f"Music bed not configured for {podcast_name}")
        music_beds = [music_bed]

    # Convert to absolute paths
    music_files = []
    for music_bed in music_beds:
        music_path = REPO_ROOT / music_bed
        music_files.append(music_path)

    # Get duration
    duration = state.get("actual_duration_seconds", 0)
    if duration == 0:
        print("Warning: Duration not found in state, using ffprobe...")
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(voice_file)
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            duration = float(result.stdout.strip())

    # Output file
    output_file = episode_dir / "mixed_final.mp3"

    print(f"Mixing audio for: {podcast_config['name']}")
    print(f"Episode ID: {episode_id}")

    # Prepare metadata for MP3 tags
    episode_metadata = {
        "title": state.get("title", f"Episode {episode_id}"),
        "podcast_name": podcast_config.get("name", podcast_name),
        "episode_id": episode_id
    }

    # Mix audio
    mix_audio(voice_file, music_files, output_file, duration, config, episode_metadata)

    # Verify output
    if not output_file.exists() or output_file.stat().st_size == 0:
        raise RuntimeError(f"Mixed audio not created or empty: {output_file}")

    print(f"\n✅ Audio mixing complete!")
    print(f"   File: {output_file}")
    print(f"   Size: {output_file.stat().st_size / 1024:.1f} KB")

    # Update state
    state["status"] = "mixed"
    state["mixed_at"] = datetime.now().isoformat()
    state["final_file"] = str(output_file)
    state["music_beds_used"] = [str(m) for m in music_beds]

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Update database
    db_path = REPO_ROOT / config["paths"]["catalog_db"]
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE episodes
        SET status = 'mixed',
            mixed_at = ?
        WHERE episode_id = ?
    """, (datetime.now().isoformat(), episode_id))

    conn.commit()
    conn.close()

    # Generate show notes
    generate_show_notes(episode_id, episode_dir, podcast_name, state)

    # Export to Obsidian vault
    export_to_obsidian(episode_id, episode_dir, podcast_config['name'], state)

    # Send Telegram notification
    # Use fallback_chat_id if chat_id is placeholder
    chat_id = config["telegram"]["chat_id"]
    if "CHAT_ID_HERE" in str(chat_id):
        chat_id = config["telegram"].get("fallback_chat_id", 8241581699)
    duration_min = int(duration) // 60
    duration_sec = int(duration) % 60

    message = f"""✅ **{podcast_config['name']}** - Episode Ready to Publish!

**Episode**: {state.get('title', episode_id)}
**Duration**: {duration_min}:{duration_sec:02d}
**File**: `{output_file}`

Listen to the attached audio and upload to Spotify Creators when ready.
"""

    result = send_telegram(
        message,
        output_file,
        str(chat_id),
        title=state.get('title', 'Podcast Episode'),
        performer=podcast_config['name'],
        episode_id=episode_id
    )

    if result["success"]:
        print(f"📱 Telegram notification sent (message ID: {result['message_id']})")
    else:
        print("⚠️  Telegram notification failed")


def test_mixing(voice_file: Path, music_files: list):
    """Test audio mixing."""
    config = load_config()

    print(f"Testing audio mixing...")
    print(f"  Voice: {voice_file}")
    print(f"  Music: {music_files}\n")

    # Get duration
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(voice_file)
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        duration = float(result.stdout.strip())
    else:
        print("Warning: Could not determine duration, using 180s")
        duration = 180.0

    # Output to temp file
    output_file = REPO_ROOT / "data" / "mixed_test.mp3"
    output_file.parent.mkdir(exist_ok=True)

    # Mix
    mix_audio(voice_file, music_files, output_file, duration, config)

    print(f"\n✅ Test complete!")
    print(f"   File: {output_file}")
    print(f"\nPlay with: afplay {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Mix podcast audio with music bed")
    parser.add_argument("--episode-id", help="Episode ID to mix")
    parser.add_argument("--test", action="store_true", help="Test mode")
    parser.add_argument("--voice", type=Path, help="Voice file for test mode")
    parser.add_argument("--music", type=Path, nargs="+", help="Music file(s) for test mode (can specify multiple)")

    args = parser.parse_args()

    if args.test:
        if not args.voice or not args.music:
            parser.error("--test requires --voice and --music")
        test_mixing(args.voice, args.music)
    elif args.episode_id:
        mix_episode(args.episode_id)
    else:
        parser.error("Either --episode-id or --test required")


if __name__ == "__main__":
    main()
