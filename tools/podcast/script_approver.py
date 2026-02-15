#!/usr/bin/env python3
"""
Podcast Script Approver

Polls for script approvals and triggers voice synthesis.

Usage:
    python tools/podcast/script_approver.py  # Check all pending scripts
    python tools/podcast/script_approver.py --episode-id 20260210-170000-explore  # Approve specific episode
"""

import sys
import json
import yaml
import argparse
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_config():
    """Load podcast configuration."""
    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_pending_episodes():
    """Get all episodes waiting for script approval."""
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT episode_id, podcast_name, title, episode_dir, script_draft_at
        FROM episodes
        WHERE status = 'script_draft'
        ORDER BY created_at ASC
    """)

    episodes = cursor.fetchall()
    conn.close()

    return [
        {
            "episode_id": row[0],
            "podcast_name": row[1],
            "title": row[2],
            "episode_dir": row[3],
            "script_draft_at": row[4],
        }
        for row in episodes
    ]


def check_approval(episode_dir: Path) -> bool:
    """
    Check if episode has been approved.

    Approval methods:
    1. File marker: episode_dir/.approved exists
    2. State file: state.json has "approved": true
    """
    # Method 1: Check for .approved file marker
    approval_marker = episode_dir / ".approved"
    if approval_marker.exists():
        return True

    # Method 2: Check state.json
    state_path = episode_dir / "state.json"
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
            if state.get("approved"):
                return True

    return False


def approve_episode(episode_id: str, episode_dir: Path):
    """Approve episode script and trigger TTS."""
    print(f"✅ Approving episode: {episode_id}")

    # Copy script_draft.md to script_approved.md
    draft_path = episode_dir / "script_draft.md"
    approved_path = episode_dir / "script_approved.md"

    if not draft_path.exists():
        print(f"❌ Script draft not found: {draft_path}")
        return False

    shutil.copy(draft_path, approved_path)
    print(f"   Copied: {draft_path.name} → {approved_path.name}")

    # Update state.json
    state_path = episode_dir / "state.json"
    with open(state_path) as f:
        state = json.load(f)

    state["status"] = "script_approved"
    state["script_approved_at"] = datetime.now().isoformat()
    state["approved"] = True

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"   Updated state: script_approved")

    # Update database
    config = load_config()
    db_path = REPO_ROOT / config["paths"]["catalog_db"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE episodes
        SET status = 'script_approved',
            script_approved_at = ?
        WHERE episode_id = ?
    """, (datetime.now().isoformat(), episode_id))

    conn.commit()
    conn.close()

    print(f"   Database updated")

    # Trigger TTS synthesis
    trigger_tts(episode_id)

    return True


def trigger_tts(episode_id: str):
    """Trigger TTS synthesis for approved episode."""
    print(f"\n🔄 Triggering TTS synthesis...")

    tts_synthesizer = REPO_ROOT / "tools" / "podcast" / "tts_synthesizer.py"

    import subprocess
    result = subprocess.run(
        [sys.executable, str(tts_synthesizer), "--episode-id", episode_id],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("✅ TTS synthesis complete")
        if result.stdout:
            print(result.stdout)
    else:
        print("❌ TTS synthesis failed")
        if result.stderr:
            print(result.stderr)


def poll_approvals():
    """Poll all pending episodes for approvals."""
    pending = get_pending_episodes()

    if not pending:
        print("ℹ️  No episodes waiting for approval")
        return

    print(f"Found {len(pending)} episode(s) waiting for approval:\n")

    approved_count = 0

    for episode in pending:
        episode_dir = Path(episode["episode_dir"])

        print(f"Checking: {episode['episode_id']}")
        print(f"  Title: {episode['title']}")
        print(f"  Directory: {episode_dir}")

        if check_approval(episode_dir):
            print(f"  ✅ APPROVED - Processing...")
            approve_episode(episode["episode_id"], episode_dir)
            approved_count += 1
            print()
        else:
            print(f"  ⏳ Waiting for approval")
            print(f"     To approve: touch {episode_dir}/.approved")
            print()

    if approved_count > 0:
        print(f"\n✅ Approved {approved_count} episode(s)")
    else:
        print(f"\nℹ️  No new approvals")


def manual_approve(episode_id: str):
    """Manually approve a specific episode."""
    config = load_config()
    episodes_dir = REPO_ROOT / config["paths"]["episodes_dir"]
    episode_dir = episodes_dir / episode_id

    if not episode_dir.exists():
        print(f"❌ Episode not found: {episode_id}")
        sys.exit(1)

    # Check current status
    state_path = episode_dir / "state.json"
    with open(state_path) as f:
        state = json.load(f)

    if state["status"] != "script_draft":
        print(f"⚠️  Episode not in draft status (current: {state['status']})")
        print(f"   Continue anyway? [y/N] ", end="")
        response = input().strip().lower()
        if response != "y":
            print("Aborted")
            sys.exit(0)

    approve_episode(episode_id, episode_dir)


def main():
    parser = argparse.ArgumentParser(description="Poll for script approvals and trigger TTS")
    parser.add_argument(
        "--episode-id",
        help="Manually approve specific episode"
    )

    args = parser.parse_args()

    if args.episode_id:
        manual_approve(args.episode_id)
    else:
        poll_approvals()


if __name__ == "__main__":
    main()
