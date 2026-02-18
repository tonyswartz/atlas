#!/usr/bin/env python3
"""
Paragraph Approval State Manager

Tracks paragraph-by-paragraph synthesis progress for podcast episodes.
State stored in data/podcast_paragraph_state.json.

State format:
{
  "sololaw-030": {
    "status": "awaiting_approval",  # awaiting_approval | generating | completed
    "total_paragraphs": 15,
    "current_paragraph": 2,
    "paragraphs": {
      "0": {"status": "approved", "message_id": 12340, "duration": 12.5},
      "1": {"status": "approved", "message_id": 12341, "duration": 15.2},
      "2": {"status": "pending", "message_id": 12342}
    },
    "started_at": "2026-02-17T10:30:00",
    "last_updated": "2026-02-17T10:35:00"
  }
}
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

REPO_ROOT = Path(__file__).parent.parent.parent
STATE_FILE = REPO_ROOT / "data" / "podcast_paragraph_state.json"


def load_state() -> dict:
    """Load paragraph approval state from disk."""
    if not STATE_FILE.exists():
        return {}

    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict):
    """Save paragraph approval state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def init_episode(episode_id: str, total_paragraphs: int) -> dict:
    """
    Initialize paragraph approval state for an episode.

    Returns the initialized state dict.
    """
    state = load_state()

    episode_state = {
        "status": "generating",
        "total_paragraphs": total_paragraphs,
        "current_paragraph": 0,
        "paragraphs": {},
        "started_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat()
    }

    state[episode_id] = episode_state
    save_state(state)

    return episode_state


def get_episode_state(episode_id: str) -> Optional[dict]:
    """Get state for a specific episode."""
    state = load_state()
    return state.get(episode_id)


def mark_paragraph_pending(episode_id: str, paragraph_num: int, message_id: int, chat_id: int = None):
    """Mark a paragraph as pending approval (sent to Telegram)."""
    state = load_state()

    if episode_id not in state:
        raise ValueError(f"Episode {episode_id} not initialized")

    para_data = {
        "status": "pending",
        "message_id": message_id,
        "sent_at": datetime.now().isoformat()
    }

    if chat_id is not None:
        para_data["chat_id"] = chat_id

    state[episode_id]["paragraphs"][str(paragraph_num)] = para_data
    state[episode_id]["current_paragraph"] = paragraph_num
    state[episode_id]["status"] = "awaiting_approval"
    state[episode_id]["last_updated"] = datetime.now().isoformat()

    save_state(state)


def mark_paragraph_approved(episode_id: str, paragraph_num: int, duration: Optional[float] = None):
    """Mark a paragraph as approved."""
    state = load_state()

    if episode_id not in state:
        raise ValueError(f"Episode {episode_id} not initialized")

    para_str = str(paragraph_num)
    if para_str not in state[episode_id]["paragraphs"]:
        raise ValueError(f"Paragraph {paragraph_num} not found in state")

    state[episode_id]["paragraphs"][para_str]["status"] = "approved"
    state[episode_id]["paragraphs"][para_str]["approved_at"] = datetime.now().isoformat()

    if duration is not None:
        state[episode_id]["paragraphs"][para_str]["duration"] = duration

    state[episode_id]["last_updated"] = datetime.now().isoformat()

    # Check if all paragraphs are approved
    total = state[episode_id]["total_paragraphs"]
    approved_count = sum(
        1 for p in state[episode_id]["paragraphs"].values()
        if p["status"] == "approved"
    )

    if approved_count >= total:
        state[episode_id]["status"] = "all_approved"
    else:
        state[episode_id]["status"] = "ready_for_next"

    save_state(state)


def mark_paragraph_regenerating(episode_id: str, paragraph_num: int):
    """Mark a paragraph as being regenerated."""
    state = load_state()

    if episode_id not in state:
        raise ValueError(f"Episode {episode_id} not initialized")

    para_str = str(paragraph_num)
    if para_str not in state[episode_id]["paragraphs"]:
        state[episode_id]["paragraphs"][para_str] = {}

    state[episode_id]["paragraphs"][para_str]["status"] = "regenerating"
    state[episode_id]["paragraphs"][para_str]["regenerate_requested_at"] = datetime.now().isoformat()
    state[episode_id]["status"] = "generating"
    state[episode_id]["last_updated"] = datetime.now().isoformat()

    save_state(state)


def get_next_paragraph_number(episode_id: str) -> Optional[int]:
    """
    Get the next paragraph number to generate.
    Returns None if all paragraphs are done or episode not found.
    """
    state = load_state()

    if episode_id not in state:
        return None

    episode_state = state[episode_id]
    total = episode_state["total_paragraphs"]

    # Find the next paragraph that needs generation
    for i in range(total):
        para_str = str(i)
        if para_str not in episode_state["paragraphs"]:
            return i

        para_status = episode_state["paragraphs"][para_str]["status"]
        if para_status in ("pending", "regenerating"):
            # Still waiting on this one
            return None

    # All paragraphs processed
    return None


def find_episode_by_message_id(message_id: int, chat_id: int = None) -> Optional[tuple[str, int]]:
    """
    Find episode_id and paragraph_num for a given Telegram message ID.
    If chat_id is provided, also verifies it matches.
    Returns (episode_id, paragraph_num) or None if not found.
    """
    state = load_state()

    for episode_id, episode_state in state.items():
        for para_num_str, para_data in episode_state.get("paragraphs", {}).items():
            if para_data.get("message_id") == message_id:
                # If chat_id verification is requested, check it matches
                if chat_id is not None:
                    stored_chat_id = para_data.get("chat_id")
                    if stored_chat_id is not None and stored_chat_id != chat_id:
                        # Message ID matches but chat ID doesn't - skip
                        continue

                return (episode_id, int(para_num_str))

    return None


def is_all_approved(episode_id: str) -> bool:
    """Check if all paragraphs are approved for an episode."""
    state = load_state()

    if episode_id not in state:
        return False

    episode_state = state[episode_id]
    total = episode_state["total_paragraphs"]

    approved_count = sum(
        1 for p in episode_state.get("paragraphs", {}).values()
        if p.get("status") == "approved"
    )

    return approved_count >= total


def cleanup_episode(episode_id: str):
    """Remove episode from state (after final mix is done)."""
    state = load_state()

    if episode_id in state:
        del state[episode_id]
        save_state(state)


def get_progress_summary(episode_id: str) -> str:
    """Get a human-readable progress summary."""
    state = load_state()

    if episode_id not in state:
        return f"Episode {episode_id} not found in state"

    episode_state = state[episode_id]
    total = episode_state["total_paragraphs"]

    approved = sum(
        1 for p in episode_state.get("paragraphs", {}).values()
        if p.get("status") == "approved"
    )

    pending = sum(
        1 for p in episode_state.get("paragraphs", {}).values()
        if p.get("status") == "pending"
    )

    return f"{approved}/{total} approved, {pending} pending"


if __name__ == "__main__":
    # Test/debug usage
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            state = load_state()
            print(json.dumps(state, indent=2))
        elif sys.argv[1] == "clear":
            if len(sys.argv) > 2:
                cleanup_episode(sys.argv[2])
                print(f"Cleared {sys.argv[2]}")
            else:
                print("Usage: paragraph_approval_state.py clear <episode_id>")
    else:
        print("Usage:")
        print("  paragraph_approval_state.py status")
        print("  paragraph_approval_state.py clear <episode_id>")
