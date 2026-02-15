#!/usr/bin/env python3
"""
Spotify Draft Uploader

Uploads podcast episodes to Spotify for Creators as drafts using Safari browser automation.

Usage:
    python tools/podcast/spotify_uploader.py --episode-id explore-001
    python tools/podcast/spotify_uploader.py --episode-id explore-001 --publish-now
"""

import sys
import json
import yaml
import argparse
import time
import urllib.request
from pathlib import Path
from datetime import datetime

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

BROWSER_SERVER = "http://127.0.0.1:19527/action"


def browser_action(action: str, **kwargs) -> dict:
    """Send action to browser server."""
    payload = {"action": action, **kwargs}
    req = urllib.request.Request(
        BROWSER_SERVER,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            if not result.get("ok"):
                raise RuntimeError(f"Browser action failed: {result.get('error')}")
            return result
    except Exception as e:
        raise RuntimeError(f"Browser server error: {e}")


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def upload_to_spotify(episode_id: str, publish_now: bool = False):
    """
    Upload episode to Spotify for Creators as a draft.

    Args:
        episode_id: Episode ID (e.g., explore-001)
        publish_now: If True, publish immediately instead of saving as draft

    Returns:
        bool: True if successful
    """
    config = load_config()

    # Parse episode ID to get podcast name and number
    parts = episode_id.split("-")
    if len(parts) != 2:
        raise ValueError(f"Invalid episode ID format: {episode_id}. Expected format: podcast-001")

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

    # Check if episode is ready (must have final audio)
    if state.get("status") != "mixed":
        raise ValueError(f"Episode not ready for upload. Status: {state.get('status')}. Need status: mixed")

    final_audio = episode_dir / "mixed_final.mp3"
    if not final_audio.exists():
        raise FileNotFoundError(f"Final audio not found: {final_audio}")

    show_notes_file = episode_dir / "show_notes.txt"
    show_notes = show_notes_file.read_text(encoding="utf-8") if show_notes_file.exists() else state.get("idea", "")

    title = state.get("title", episode_id)

    print(f"📤 Uploading to Spotify for Creators...")
    print(f"   Podcast: {podcast_config['name']}")
    print(f"   Episode: {episode_number}")
    print(f"   Title: {title}")
    print(f"   Audio: {final_audio}")
    print(f"   Publish: {'Yes' if publish_now else 'No (save as draft)'}")

    # Navigate to Spotify for Creators
    print("\n🌐 Opening Spotify for Creators...")
    browser_action("navigate", url="https://creators.spotify.com/pod/dashboard/episodes")
    time.sleep(3)  # Wait for page load

    # Click "Create episode" or "Upload" button
    print("🔘 Clicking 'Create episode' button...")
    try:
        # Try multiple possible selectors
        selectors = [
            "button:contains('Create episode')",
            "button:contains('Upload')",
            "a[href*='upload']",
            "button[data-testid='upload-button']",
        ]

        for selector in selectors:
            try:
                browser_action("click", selector=selector, by="css")
                break
            except:
                continue

        time.sleep(2)
    except Exception as e:
        print(f"⚠️  Could not find upload button. Please check the browser window.")
        print(f"   You may need to manually click 'Create episode' or 'Upload'")
        input("   Press Enter when ready to continue...")

    # Upload audio file
    print("📁 Uploading audio file...")
    print("   ⚠️  Manual step required:")
    print(f"   1. Click the file upload button in the browser")
    print(f"   2. Select: {final_audio}")
    input("   Press Enter when file is uploaded and you see the episode form...")

    # Fill in episode details
    print("\n✍️  Filling in episode details...")

    # Title field
    try:
        browser_action("type", selector="input[name='title']", text=title, by="css")
        print(f"   ✅ Title: {title}")
    except:
        print(f"   ℹ️  Please manually enter title: {title}")

    # Description/Show notes field
    try:
        browser_action("type", selector="textarea[name='description']", text=show_notes, by="css")
        print(f"   ✅ Description added")
    except:
        print(f"   ℹ️  Please manually paste show notes")

    # Season/Episode number (if available)
    try:
        browser_action("type", selector="input[name='episodeNumber']", text=episode_number, by="css")
        print(f"   ✅ Episode number: {episode_number}")
    except:
        pass  # Not all podcasts use episode numbers

    # Save as draft or publish
    if publish_now:
        print("\n📢 Publishing episode...")
        print("   ⚠️  Manual step: Click 'Publish' button")
        input("   Press Enter when published...")
    else:
        print("\n💾 Saving as draft...")
        print("   ⚠️  Manual step: Click 'Save as draft' button")
        input("   Press Enter when saved...")

    # Update episode state
    state["status"] = "published" if publish_now else "draft"
    state["uploaded_at"] = datetime.now().isoformat()
    state["spotify_status"] = "published" if publish_now else "draft"

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n✅ Episode uploaded to Spotify!")
    print(f"   Status: {'Published' if publish_now else 'Draft'}")
    print(f"   Updated state: {state_path}")

    # Update episode history
    print(f"\n📚 Updating episode history...")
    from tools.podcast.update_history import update_history
    try:
        history_file = update_history(episode_id)
        print(f"   ✅ History updated: {history_file}")
    except Exception as e:
        print(f"   ⚠️  Warning: Could not update history: {e}")
        # Don't fail the upload if history update fails

    return True


def main():
    parser = argparse.ArgumentParser(description="Upload podcast episode to Spotify for Creators")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., explore-001)")
    parser.add_argument("--publish-now", action="store_true", help="Publish immediately instead of saving as draft")

    args = parser.parse_args()

    try:
        upload_to_spotify(args.episode_id, args.publish_now)
    except Exception as e:
        print(f"\n❌ Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
