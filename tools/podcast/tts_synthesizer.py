#!/usr/bin/env python3
"""
Podcast TTS Synthesizer

Converts approved podcast scripts to speech using ElevenLabs or Deepgram.

Usage:
    python tools/podcast/tts_synthesizer.py --episode-id 20260210-170000-explore
    python tools/podcast/tts_synthesizer.py --test --text "Testing voice synthesis"
"""

import sys
import json
import yaml
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import urllib.request
import urllib.error

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.common.credentials import get_credential


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def strip_script_metadata(script: str) -> str:
    """
    Strip metadata header from script before TTS.

    Removes lines like:
    - # Title
    - **Word count**: ...
    - **Duration**: ...
    - **Purpose**: ...
    - ---
    - Section markers like [HOOK - 15 seconds]

    Also normalizes paragraph breaks to improve TTS pacing.
    Returns only the actual spoken content.
    """
    import re

    lines = script.split('\n')
    clean_lines = []
    skip_mode = True  # Skip until we find actual content

    for line in lines:
        stripped = line.strip()

        # Skip metadata lines
        if skip_mode:
            # Skip title headers
            if stripped.startswith('#'):
                continue
            # Skip metadata fields
            if stripped.startswith('**') and ':' in stripped:
                continue
            # Skip horizontal rules
            if stripped == '---':
                continue
            # Skip section markers like [HOOK - 15 seconds]
            if stripped.startswith('[') and stripped.endswith(']'):
                continue
            # Skip empty lines at the start
            if not stripped:
                continue
            # Found actual content - stop skipping
            skip_mode = False

        # Keep all lines after we find content
        if not skip_mode:
            # Still skip section markers in the middle (with or without bold)
            # Examples: [HOOK - 15 seconds], **[HOOK - 15 seconds]**, [STORY]
            if '[' in stripped and ']' in stripped:
                # Extract the bracketed part
                if re.match(r'^(\*\*)?(\[.*?\])(\*\*)?$', stripped):
                    continue
            clean_lines.append(line)

    # Join lines
    text = '\n'.join(clean_lines).strip()

    # Remove **Notes** section at the end (metadata that shouldn't be spoken)
    # This can appear as **Notes**: or **Notes**:
    notes_pattern = r'\n\s*\*\*Notes\*\*:?.*$'
    text = re.sub(notes_pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Replace multiple consecutive newlines (paragraph breaks) with double newline
    # This helps TTS interpret pauses more consistently
    text = re.sub(r'\n\n+', '\n\n', text)

    return text.strip()


def call_elevenlabs(text: str, voice_id: str, config: dict, output_file: Path):
    """
    Call ElevenLabs TTS API.

    Args:
        text: Script text to synthesize
        voice_id: ElevenLabs voice ID
        config: TTS configuration from podcast.yaml
        output_file: Where to save the audio
    """
    api_key = get_credential("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not found in envchain or .env")

    tts_config = config["tts"]["elevenlabs"]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }

    voice_settings = {
        "stability": tts_config["stability"],
        "similarity_boost": tts_config["similarity_boost"],
        "style": tts_config.get("style", 0.0),
        "use_speaker_boost": tts_config.get("use_speaker_boost", True),
    }

    # Add speed if configured (range: 0.7-1.2, default: 1.0)
    if "speed" in tts_config:
        voice_settings["speed"] = tts_config["speed"]

    payload = json.dumps({
        "text": text,
        "model_id": tts_config["model"],
        "voice_settings": voice_settings
    }).encode()

    print(f"Calling ElevenLabs API...")
    print(f"  Voice ID: {voice_id}")
    print(f"  Model: {tts_config['model']}")
    print(f"  Text length: {len(text)} characters")

    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            # Stream audio chunks to file
            with open(output_file, "wb") as f:
                chunk_size = 8192
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)

            print(f"✅ Audio saved to: {output_file}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"ElevenLabs API error: {e.code} - {error_body}")


def get_audio_duration(audio_file: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_file)
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return float(result.stdout.strip())

    except Exception as e:
        print(f"Warning: Could not determine audio duration: {e}")

    return 0.0


def split_into_paragraphs(script_text: str) -> list[dict]:
    """
    Split script into paragraphs (by double newlines).
    Returns list of paragraph dicts with text and metadata.
    """
    paragraphs = []
    # Split by double newlines (paragraph breaks)
    raw_paragraphs = script_text.split('\n\n')

    char_offset = 0
    for i, text in enumerate(raw_paragraphs):
        text = text.strip()
        if not text:  # Skip empty paragraphs
            char_offset += 2  # Account for the \n\n
            continue

        paragraphs.append({
            "number": len(paragraphs),
            "text": text,
            "start_char": char_offset,
            "end_char": char_offset + len(text),
            "word_count": len(text.split())
        })

        char_offset += len(text) + 2  # +2 for \n\n

    return paragraphs


def concatenate_audio_files(audio_files: list[Path], output_file: Path, silence_duration: float = 0.7):
    """
    Concatenate multiple audio files with silence between paragraphs.

    Args:
        audio_files: List of audio files to concatenate
        output_file: Output file path
        silence_duration: Silence duration in seconds between paragraphs (default: 0.7s)
    """
    if not audio_files:
        raise ValueError("No audio files to concatenate")

    # Generate silence file
    silence_file = output_file.parent / "silence.mp3"

    silence_result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(silence_duration),
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(silence_file)
    ], capture_output=True, text=True, timeout=10)

    if silence_result.returncode != 0:
        raise RuntimeError(f"Failed to generate silence: {silence_result.stderr}")

    # Create concat file list with silence between paragraphs
    concat_list = output_file.parent / "concat_list.txt"

    with open(concat_list, "w") as f:
        for i, audio_file in enumerate(audio_files):
            # Escape single quotes in path
            path_str = str(audio_file.absolute()).replace("'", "'\\''")
            f.write(f"file '{path_str}'\n")

            # Add silence between paragraphs (but not after the last one)
            if i < len(audio_files) - 1:
                silence_path_str = str(silence_file.absolute()).replace("'", "'\\''")
                f.write(f"file '{silence_path_str}'\n")

    try:
        # Use ffmpeg concat demuxer
        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",  # Copy without re-encoding
            str(output_file)
        ], capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")

    finally:
        # Clean up temporary files
        if concat_list.exists():
            concat_list.unlink()
        if silence_file.exists():
            silence_file.unlink()

    print(f"✅ Concatenated {len(audio_files)} paragraphs with {silence_duration}s pauses")


def synthesize_episode(episode_id: str):
    """Synthesize audio for an episode."""
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

    # Load approved script
    script_path = episode_dir / "script_approved.md"
    if not script_path.exists():
        raise FileNotFoundError(f"Approved script not found: {script_path}")

    script_text = script_path.read_text(encoding="utf-8")

    # Strip metadata header (word count, duration, etc.) before TTS
    script_text = strip_script_metadata(script_text)

    # Apply pronunciation fixes
    from tools.podcast.pronunciation import load_pronunciation_dict, apply_pronunciation_fixes

    pron_dict = load_pronunciation_dict()
    # Check for one-off fixes in state
    one_off_fixes = state.get("pronunciation_fixes", {})

    if pron_dict or one_off_fixes:
        print(f"\nApplying pronunciation fixes...")
        script_text, fixes_applied = apply_pronunciation_fixes(script_text, pron_dict, one_off_fixes)
        if fixes_applied:
            for fix in fixes_applied:
                print(f"  • {fix}")
        else:
            print("  (no fixes needed)")
    else:
        print("\nNo pronunciation dictionary found, using script as-is")

    print(f"Synthesizing audio for: {podcast_config['name']}")
    print(f"Episode ID: {episode_id}")
    print(f"Script length: {len(script_text)} characters, {len(script_text.split())} words")

    # Get voice ID
    voice_id = podcast_config.get("voice_id")
    if not voice_id or voice_id == "VOICE_ID_PLACEHOLDER":
        raise ValueError(
            f"Voice ID not configured for {podcast_name}. "
            "Please update agents/podcast/args/podcast.yaml with your ElevenLabs voice ID."
        )

    # Split script into paragraphs
    paragraphs = split_into_paragraphs(script_text)
    print(f"\n📄 Split into {len(paragraphs)} paragraphs")

    # Create paragraphs directory
    paragraphs_dir = episode_dir / "paragraphs"
    paragraphs_dir.mkdir(exist_ok=True)

    # Generate each paragraph
    provider = config["tts"]["provider"]
    paragraph_files = []
    paragraph_metadata = []

    for para in paragraphs:
        para_num = para["number"]
        para_file = paragraphs_dir / f"paragraph_{para_num:03d}.mp3"

        print(f"\n  Paragraph {para_num} ({para['word_count']} words)...")

        # Call TTS for this paragraph
        if provider == "elevenlabs":
            call_elevenlabs(para["text"], voice_id, config, para_file)
        else:
            raise ValueError(f"Unsupported TTS provider: {provider}")

        # Verify paragraph audio created
        if not para_file.exists() or para_file.stat().st_size == 0:
            raise RuntimeError(f"Paragraph audio not created: {para_file}")

        # Get duration
        para_duration = get_audio_duration(para_file)

        # Store metadata
        paragraph_metadata.append({
            "number": para_num,
            "text": para["text"][:200] + "..." if len(para["text"]) > 200 else para["text"],  # Truncate for storage
            "file": para_file.name,
            "duration": round(para_duration, 2),
            "word_count": para["word_count"],
            "char_range": [para["start_char"], para["end_char"]]
        })

        paragraph_files.append(para_file)

        print(f"    ✅ {para_file.name} ({para_duration:.1f}s)")

    # Save paragraph metadata
    metadata_file = paragraphs_dir / "paragraph_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump({"paragraphs": paragraph_metadata}, f, indent=2)

    print(f"\n📝 Saved paragraph metadata to {metadata_file.name}")

    # Concatenate all paragraphs into voice_raw.mp3
    output_file = episode_dir / "voice_raw.mp3"
    print(f"\n🔗 Concatenating {len(paragraph_files)} paragraphs...")
    concatenate_audio_files(paragraph_files, output_file)

    # Verify final audio created
    if not output_file.exists() or output_file.stat().st_size == 0:
        raise RuntimeError(f"Final audio file not created or empty: {output_file}")

    # Get total duration
    duration = get_audio_duration(output_file)
    duration_int = int(duration)

    print(f"\n✅ Audio synthesis complete!")
    print(f"   File: {output_file}")
    print(f"   Size: {output_file.stat().st_size / 1024:.1f} KB")
    print(f"   Duration: {duration_int//60}:{duration_int%60:02d}")

    # Update state
    state["status"] = "voice_generated"
    state["voice_generated_at"] = datetime.now().isoformat()
    state["voice_file"] = str(output_file)
    state["actual_duration_seconds"] = duration_int
    state["tts_provider"] = provider

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
    print(f"\n🔄 Triggering audio mixing...")
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


def test_synthesis(text: str):
    """Test TTS synthesis with sample text."""
    config = load_config()

    print(f"Testing TTS synthesis...")
    print(f"Text: {text[:100]}...\n")

    # Use first podcast's voice ID for testing
    first_podcast = list(config["podcasts"].values())[0]
    voice_id = first_podcast.get("voice_id")

    if not voice_id or voice_id == "VOICE_ID_PLACEHOLDER":
        raise ValueError(
            "Voice ID not configured. "
            "Please update agents/podcast/args/podcast.yaml with your ElevenLabs voice ID."
        )

    # Output to temp file
    output_file = REPO_ROOT / "data" / "voice_test.mp3"
    output_file.parent.mkdir(exist_ok=True)

    # Call TTS
    provider = config["tts"]["provider"]

    if provider == "elevenlabs":
        call_elevenlabs(text, voice_id, config, output_file)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")

    # Get duration
    duration = get_audio_duration(output_file)

    print(f"\n✅ Test complete!")
    print(f"   File: {output_file}")
    print(f"   Duration: {int(duration)//60}:{int(duration)%60:02d}")
    print(f"\nPlay with: afplay {output_file}")


def synthesize_next_paragraph_telegram(episode_id: str, paragraph_num: int):
    """
    Generate a single paragraph and send to Telegram for approval.
    Used in --telegram-approval mode.
    """
    from tools.podcast.paragraph_approval_state import (
        init_episode, mark_paragraph_pending, get_episode_state
    )
    from tools.common.credentials import get_telegram_token

    config = load_config()

    # Load episode directory and state
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
            raise ValueError(f"Unknown podcast short name: {podcast_name_short}")
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

    # Load and process script
    script_path = episode_dir / "script_approved.md"
    if not script_path.exists():
        raise FileNotFoundError(f"Approved script not found: {script_path}")

    script_text = script_path.read_text(encoding="utf-8")
    script_text = strip_script_metadata(script_text)

    # Apply pronunciation fixes
    from tools.podcast.pronunciation import load_pronunciation_dict, apply_pronunciation_fixes

    pron_dict = load_pronunciation_dict()
    one_off_fixes = state.get("pronunciation_fixes", {})
    script_text, _ = apply_pronunciation_fixes(script_text, pron_dict, one_off_fixes)

    # Split into paragraphs
    paragraphs = split_into_paragraphs(script_text)

    # Initialize state if this is the first paragraph
    if paragraph_num == 0:
        init_episode(episode_id, len(paragraphs))
        print(f"\n📄 Initialized {len(paragraphs)} paragraphs for Telegram approval")

    # Validate paragraph number
    if paragraph_num >= len(paragraphs):
        raise ValueError(f"Paragraph {paragraph_num} out of range (0-{len(paragraphs)-1})")

    para = paragraphs[paragraph_num]

    # Create paragraphs directory
    paragraphs_dir = episode_dir / "paragraphs"
    paragraphs_dir.mkdir(exist_ok=True)

    # Generate paragraph audio
    voice_id = podcast_config.get("voice_id")
    if not voice_id or voice_id == "VOICE_ID_PLACEHOLDER":
        raise ValueError(f"Voice ID not configured for {podcast_name}")

    para_file = paragraphs_dir / f"paragraph_{paragraph_num:03d}.mp3"

    print(f"\n🎙️ Generating paragraph {paragraph_num}/{len(paragraphs)-1} ({para['word_count']} words)...")

    provider = config["tts"]["provider"]
    if provider == "elevenlabs":
        call_elevenlabs(para["text"], voice_id, config, para_file)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")

    if not para_file.exists() or para_file.stat().st_size == 0:
        raise RuntimeError(f"Paragraph audio not created: {para_file}")

    para_duration = get_audio_duration(para_file)

    print(f"   ✅ Generated {para_file.name} ({para_duration:.1f}s)")

    # Update metadata
    metadata_file = paragraphs_dir / "paragraph_metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)
    else:
        metadata = {"paragraphs": []}

    # Update or add this paragraph's metadata
    para_meta = {
        "number": paragraph_num,
        "text": para["text"][:200] + "..." if len(para["text"]) > 200 else para["text"],
        "file": para_file.name,
        "duration": round(para_duration, 2),
        "word_count": para["word_count"],
        "char_range": [para["start_char"], para["end_char"]]
    }

    # Replace existing or append
    existing_idx = next((i for i, p in enumerate(metadata["paragraphs"]) if p["number"] == paragraph_num), None)
    if existing_idx is not None:
        metadata["paragraphs"][existing_idx] = para_meta
    else:
        metadata["paragraphs"].append(para_meta)

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    # Send to Telegram
    token = get_telegram_token()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found")

    chat_id = config["telegram"].get("chat_id")
    if "CHAT_ID_HERE" in str(chat_id):
        chat_id = config["telegram"].get("fallback_chat_id", 8241581699)

    # Full paragraph text
    message = f"""🎙️ **Paragraph {paragraph_num + 1}/{len(paragraphs)}** ({para['word_count']} words, {para_duration:.1f}s)

_{para["text"]}_

Reply:
• **good** / **✓** → approve and continue
• **redo** → regenerate this paragraph
• **stop** → pause workflow"""

    # Send text message
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": str(chat_id),
        "text": message,
        "parse_mode": "Markdown"
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            response = json.loads(resp.read())
            text_message_id = response.get("result", {}).get("message_id")
    except Exception as e:
        raise RuntimeError(f"Failed to send Telegram message: {e}")

    # Send audio file
    audio_url = f"https://api.telegram.org/bot{token}/sendAudio"

    result = subprocess.run([
        "curl", "-s",
        "-F", f"chat_id={chat_id}",
        "-F", f"audio=@{para_file}",
        "-F", f"title=Paragraph {paragraph_num + 1}",
        "-F", f"performer={podcast_config['name']}",
        "-F", f"reply_to_message_id={text_message_id}",
        audio_url
    ], capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        raise RuntimeError(f"Failed to send audio: {result.stderr}")

    audio_response = json.loads(result.stdout)
    if not audio_response.get("ok"):
        raise RuntimeError(f"Telegram audio upload failed: {audio_response.get('description')}")

    # Save message ID and chat ID to state
    mark_paragraph_pending(episode_id, paragraph_num, text_message_id, int(chat_id))

    print(f"   📱 Sent to Telegram (message {text_message_id}, chat {chat_id})")
    print(f"\n✅ Paragraph {paragraph_num + 1}/{len(paragraphs)} sent. Waiting for approval...")


def main():
    parser = argparse.ArgumentParser(description="Synthesize podcast audio using TTS")
    parser.add_argument("--episode-id", help="Episode ID to synthesize")
    parser.add_argument("--test", action="store_true", help="Test mode")
    parser.add_argument("--text", help="Text for test mode")
    parser.add_argument("--telegram-approval", action="store_true", help="Generate one paragraph and send to Telegram for approval")
    parser.add_argument("--paragraph-num", type=int, help="Specific paragraph number to generate (for --telegram-approval mode)")

    args = parser.parse_args()

    if args.test:
        if not args.text:
            parser.error("--test requires --text")
        test_synthesis(args.text)
    elif args.telegram_approval:
        if not args.episode_id:
            parser.error("--telegram-approval requires --episode-id")

        # Determine paragraph number
        if args.paragraph_num is not None:
            para_num = args.paragraph_num
        else:
            # Find next paragraph from state
            from tools.podcast.paragraph_approval_state import get_episode_state, get_next_paragraph_number

            episode_state = get_episode_state(args.episode_id)
            if episode_state:
                para_num = get_next_paragraph_number(args.episode_id)
                if para_num is None:
                    print("All paragraphs are either pending approval or completed.")
                    sys.exit(0)
            else:
                # Start from paragraph 0
                para_num = 0

        synthesize_next_paragraph_telegram(args.episode_id, para_num)
    elif args.episode_id:
        synthesize_episode(args.episode_id)
    else:
        parser.error("Either --episode-id or --test required")


if __name__ == "__main__":
    main()
