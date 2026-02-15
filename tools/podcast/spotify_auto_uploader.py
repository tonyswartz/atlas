#!/usr/bin/env python3
"""
Spotify Automated Uploader

Fully automated upload to Spotify for Creators as draft using Safari browser automation.
Requires: browser server running with upload support.

Usage:
    python tools/podcast/spotify_auto_uploader.py --episode-id explore-001
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            if not result.get("ok"):
                raise RuntimeError(f"Browser action failed: {result.get('error')}")
            return result
    except Exception as e:
        raise RuntimeError(f"Browser server error: {e}")


def wait_for_element(selector: str, by: str = "css", timeout: int = 10, interval: float = 0.5):
    """Wait for element to appear on page."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            browser_action("click", selector=selector, by=by)
            return True
        except:
            time.sleep(interval)
    raise TimeoutError(f"Element not found after {timeout}s: {selector}")


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def upload_to_spotify_auto(episode_id: str):
    """
    Fully automated upload to Spotify for Creators as draft.

    Args:
        episode_id: Episode ID (e.g., explore-001)
    """
    config = load_config()

    # Parse episode ID
    parts = episode_id.split("-")
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

    if state.get("status") != "mixed":
        raise ValueError(f"Episode not ready. Status: {state.get('status')}")

    final_audio = episode_dir / "mixed_final.mp3"
    if not final_audio.exists():
        raise FileNotFoundError(f"Audio not found: {final_audio}")

    show_notes_file = episode_dir / "show_notes.txt"
    show_notes = show_notes_file.read_text(encoding="utf-8") if show_notes_file.exists() else state.get("idea", "")

    # Format title with episode number (e.g., "Episode 029: Title")
    base_title = state.get("title", episode_id)
    episode_num_int = int(episode_number)
    full_title = f"Episode {episode_num_int:03d}: {base_title}"

    print(f"🤖 Automated Spotify Upload")
    print(f"   Podcast: {podcast_config['name']}")
    print(f"   Episode: {episode_number}")
    print(f"   Title: {full_title}")
    print(f"   Audio: {final_audio.name}")
    print(f"   Duration: {state.get('actual_duration_seconds', 0) // 60}:{state.get('actual_duration_seconds', 0) % 60:02d}")

    # Confirmation before upload
    print(f"\n⚠️  Please confirm:")
    print(f"   1. Podcast show: {podcast_config['name']}")
    print(f"   2. Episode title: {full_title}")
    print(f"   3. Episode will be saved as DRAFT (not published)")

    confirm = input("\n   Proceed with upload? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("   ❌ Upload cancelled by user")
        sys.exit(0)

    # Step 1: Navigate to Spotify for Creators
    print("\n🌐 Opening Spotify for Creators...")
    browser_action("navigate", url="https://creators.spotify.com/pod/dashboard/episodes")
    time.sleep(3)

    # Step 2: Click "Create episode" button
    print("🔘 Clicking 'Create episode'...")
    try:
        # Try common selectors for create/upload button
        selectors = [
            ("css", "button[data-testid='new-episode-button']"),
            ("css", "button:has-text('Create episode')"),
            ("css", "button:has-text('Upload')"),
            ("css", "a[href*='/episode/new']"),
            ("xpath", "//button[contains(text(), 'Create')]"),
            ("xpath", "//button[contains(text(), 'Upload')]"),
        ]

        clicked = False
        for by, selector in selectors:
            try:
                browser_action("click", selector=selector, by=by)
                clicked = True
                print(f"   ✅ Found button: {selector}")
                break
            except:
                continue

        if not clicked:
            raise RuntimeError("Could not find Create episode button")

        time.sleep(2)
    except Exception as e:
        print(f"   ⚠️  {e}")
        print("   📸 Taking screenshot...")
        result = browser_action("screenshot")
        print(f"   Screenshot available (base64: {len(result.get('image_base64', ''))} chars)")
        raise

    # Step 3: Upload audio file
    print("📁 Uploading audio file...")
    try:
        # Common file input selectors
        file_selectors = [
            ("css", "input[type='file']"),
            ("css", "input[accept*='audio']"),
            ("xpath", "//input[@type='file']"),
        ]

        uploaded = False
        for by, selector in file_selectors:
            try:
                browser_action("upload", selector=selector, by=by, file_path=str(final_audio))
                uploaded = True
                print(f"   ✅ File uploaded via: {selector}")
                break
            except:
                continue

        if not uploaded:
            raise RuntimeError("Could not find file input element")

        # Wait for upload to process
        print("   ⏳ Waiting for upload to process...")
        time.sleep(10)

    except Exception as e:
        print(f"   ❌ Upload failed: {e}")
        raise

    # Step 4: Fill in episode details
    print("\n✍️  Filling in episode details...")

    # Title
    try:
        title_selectors = [
            ("css", "input[name='title']"),
            ("css", "input[placeholder*='title' i]"),
            ("xpath", "//input[@placeholder[contains(translate(., 'TITLE', 'title'), 'title')]]"),
        ]

        for by, selector in title_selectors:
            try:
                browser_action("type", selector=selector, by=by, text=full_title, clear=True)
                print(f"   ✅ Title: {full_title}")
                break
            except:
                continue
    except Exception as e:
        print(f"   ⚠️  Could not fill title: {e}")

    # Description
    try:
        desc_selectors = [
            ("css", "textarea[name='description']"),
            ("css", "textarea[placeholder*='description' i]"),
            ("xpath", "//textarea"),
        ]

        for by, selector in desc_selectors:
            try:
                browser_action("type", selector=selector, by=by, text=show_notes, clear=True)
                print(f"   ✅ Description added ({len(show_notes)} chars)")
                break
            except:
                continue
    except Exception as e:
        print(f"   ⚠️  Could not fill description: {e}")

    # Episode number (optional)
    try:
        num_selectors = [
            ("css", "input[name='episodeNumber']"),
            ("css", "input[type='number']"),
        ]

        for by, selector in num_selectors:
            try:
                browser_action("type", selector=selector, by=by, text=episode_number, clear=True)
                print(f"   ✅ Episode number: {episode_number}")
                break
            except:
                continue
    except:
        pass  # Episode number is optional

    # Step 5: Save as draft
    print("\n💾 Saving as draft...")
    try:
        # Try to find and click "Save as draft" button
        draft_selectors = [
            ("css", "button[data-testid='save-draft-button']"),
            ("css", "button:has-text('Save as draft')"),
            ("css", "button:has-text('Save draft')"),
            ("xpath", "//button[contains(text(), 'draft') or contains(text(), 'Draft')]"),
        ]

        saved = False
        for by, selector in draft_selectors:
            try:
                browser_action("click", selector=selector, by=by)
                saved = True
                print(f"   ✅ Clicked: {selector}")
                break
            except:
                continue

        if not saved:
            print("   ⚠️  Could not find 'Save as draft' button")
            print("   📝 Manual action required: Click 'Save as draft' in the browser")
            input("   Press Enter when saved...")
        else:
            time.sleep(3)

    except Exception as e:
        print(f"   ⚠️  {e}")
        print("   📝 Manual action: Click 'Save as draft' button")
        input("   Press Enter when saved...")

    # Update episode state
    state["status"] = "draft"
    state["uploaded_at"] = datetime.now().isoformat()
    state["spotify_status"] = "draft"

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n✅ Episode uploaded to Spotify as draft!")
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
    parser = argparse.ArgumentParser(description="Automated Spotify upload")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., explore-001)")

    args = parser.parse_args()

    try:
        upload_to_spotify_auto(args.episode_id)
    except Exception as e:
        print(f"\n❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
