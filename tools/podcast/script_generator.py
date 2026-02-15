#!/usr/bin/env python3
"""
Podcast Script Generator

Generates podcast scripts using Claude Sonnet 4.5 with podcast-specific hardprompts.

Usage:
    python tools/podcast/script_generator.py --episode-id 20260210-170000-explore
    python tools/podcast/script_generator.py --test --podcast explore --idea "Testing automation"
"""

import sys
import json
import yaml
import argparse
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


def load_hardprompt(podcast_name: str) -> str:
    """Load hardprompt for specific podcast."""
    hardprompt_path = REPO_ROOT / "hardprompts" / f"podcast_script_{podcast_name}.md"
    if not hardprompt_path.exists():
        raise FileNotFoundError(f"Hardprompt not found: {hardprompt_path}")
    return hardprompt_path.read_text(encoding="utf-8")


def load_context_examples(podcast_name: str) -> str:
    """Load example scripts from context directory."""
    context_path = REPO_ROOT / "agents" / "podcast" / "context" / f"{podcast_name}_examples.md"
    if context_path.exists():
        return context_path.read_text(encoding="utf-8")
    return ""


def call_minimax(hardprompt: str, user_idea: str, examples: str = "") -> str:
    """
    Call MiniMax API to generate script.

    Args:
        hardprompt: The hardprompt template with instructions
        user_idea: The user's episode idea
        examples: Optional example scripts for reference

    Returns:
        Generated script text
    """
    # Get API key from credentials
    api_key = get_credential("MINIMIAX_CODING")
    if not api_key:
        raise ValueError("MINIMIAX_CODING API key not found in envchain or .env")

    # Replace {USER_IDEA} placeholder in hardprompt
    system_prompt = hardprompt.replace("{USER_IDEA}", user_idea)

    # Build messages (MiniMax doesn't support system role, convert to user message)
    messages = []

    # Add system prompt as first user message
    messages.append({
        "role": "user",
        "content": system_prompt
    })

    # Add examples as context if available
    if examples:
        messages.append({
            "role": "user",
            "content": f"Here are some example scripts from this podcast for reference:\n\n{examples}"
        })
        messages.append({
            "role": "assistant",
            "content": "I've reviewed the example scripts and understand the style and format."
        })

    # Add the actual generation request
    messages.append({
        "role": "user",
        "content": f"Now generate a podcast script based on this idea:\n\n{user_idea}"
    })

    # Call MiniMax API (OpenAI-compatible)
    url = "https://api.minimax.io/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "MiniMax-M2.5",
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.7,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode())

            # Extract text from OpenAI-compatible response
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                # Strip <think> tags that MiniMax sometimes includes
                content = _strip_think(content)
                return content
            else:
                raise ValueError(f"Unexpected API response: {result}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise RuntimeError(f"MiniMax API error: {e.code} - {error_body}")


def _strip_think(text: str) -> str:
    """Remove <think>...</think> reasoning blocks that MiniMax includes."""
    import re
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def validate_script(script: str, podcast_config: dict) -> tuple[bool, str, dict]:
    """
    Validate script meets requirements.

    Returns:
        (is_valid, message, stats)
    """
    word_count = len(script.split())
    char_count = len(script)

    min_words = podcast_config.get("target_words_min", 450)
    max_words = podcast_config.get("target_words_max", 900)

    stats = {
        "word_count": word_count,
        "character_count": char_count,
        "estimated_duration_seconds": int(word_count / 2.5),  # ~150 words/min = 2.5 words/sec
    }

    if word_count < min_words:
        return False, f"Script too short ({word_count} words, need {min_words}+)", stats

    if word_count > max_words:
        return False, f"Script too long ({word_count} words, max {max_words})", stats

    return True, f"Script valid ({word_count} words)", stats


def send_telegram(message: str, chat_id: str = None) -> dict:
    """Send message to Telegram. Returns dict with success and message_id."""
    from tools.common.credentials import get_telegram_token

    token = get_telegram_token()
    if not token:
        print("Warning: TELEGRAM_BOT_TOKEN not found, skipping Telegram notification")
        return {"success": False, "message_id": None}

    if not chat_id:
        config = load_config()
        chat_id = config["telegram"]["chat_id"]
        # Use fallback_chat_id if chat_id is placeholder
        if "CHAT_ID_HERE" in str(chat_id):
            chat_id = config["telegram"].get("fallback_chat_id", 8241581699)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                response_data = json.loads(resp.read())
                message_id = response_data.get("result", {}).get("message_id")
                return {"success": True, "message_id": message_id}
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

    return {"success": False, "message_id": None}


def generate_script(episode_id: str):
    """
    Generate script for an episode.

    Args:
        episode_id: Episode ID (e.g., "sololaw-030" or "20260210-170000-explore")
    """
    # Load configuration
    config = load_config()

    # Load episode state first to get podcast name
    # Support both formats: "sololaw-030" and "20260210-170000-explore"
    if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
        # Old format: "20260210-170000-explore"
        episode_dir = REPO_ROOT / config["paths"]["episodes_dir"] / episode_id
    else:
        # New format: "sololaw-030" -> "sololaw/030"
        parts = episode_id.split("-", 1)
        episode_dir = REPO_ROOT / config["paths"]["episodes_dir"] / parts[0] / parts[1]

    state_path = episode_dir / "state.json"

    if not state_path.exists():
        raise FileNotFoundError(f"Episode state not found: {state_path}")

    with open(state_path) as f:
        state = json.load(f)

    # Get podcast name from state instead of parsing episode_id
    podcast_name = state.get("podcast_name")
    if not podcast_name:
        raise ValueError(f"podcast_name missing in state.json: {state_path}")

    if podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    podcast_config = config["podcasts"][podcast_name]

    # Load user idea
    idea_path = episode_dir / "idea.txt"
    if not idea_path.exists():
        raise FileNotFoundError(f"Episode idea not found: {idea_path}")

    user_idea = idea_path.read_text(encoding="utf-8").strip()

    print(f"Generating script for: {podcast_config['name']}")
    print(f"Episode ID: {episode_id}")
    print(f"User idea: {user_idea[:100]}...")

    # Load hardprompt and examples
    hardprompt = load_hardprompt(podcast_name)
    examples = load_context_examples(podcast_name)

    # Generate script
    print("\nCalling Claude API...")
    script = call_minimax(hardprompt, user_idea, examples)

    # Validate script
    is_valid, message, stats = validate_script(script, podcast_config)
    print(f"\nValidation: {message}")
    print(f"Stats: {stats['word_count']} words, ~{stats['estimated_duration_seconds']//60}:{stats['estimated_duration_seconds']%60:02d} duration")

    if not is_valid:
        print("Warning: Script validation failed, but saving anyway for manual review")

    # Save script (episodes_dir now points to Obsidian vault)
    script_path = episode_dir / "script_draft.md"
    script_path.write_text(script, encoding="utf-8")
    print(f"\nScript saved to: {script_path}")

    # Update state
    state["status"] = "script_draft"
    state["script_draft_at"] = datetime.now().isoformat()
    state["word_count"] = stats["word_count"]
    state["character_count"] = stats["character_count"]
    state["estimated_duration_seconds"] = stats["estimated_duration_seconds"]

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Send preview to Telegram
    preview = script[:500] + "..." if len(script) > 500 else script
    telegram_message = f"""🎙️ **{podcast_config['name']}** - Script Draft Ready

**Episode**: {state.get('title', episode_id)}
**Word Count**: {stats['word_count']} words
**Duration**: ~{stats['estimated_duration_seconds']//60}:{stats['estimated_duration_seconds']%60:02d}

**Preview**:
{preview}

📄 Full script: `{script_path}`

Reply **[approved]** to proceed to voice synthesis, or edit the script manually and then approve.
"""

    result = send_telegram(telegram_message)
    if result["success"]:
        print("\n✅ Preview sent to Telegram")

        # Store message ID for approval detection
        if result["message_id"]:
            prompts_file = REPO_ROOT / "data" / "podcast_prompts.json"
            try:
                with open(prompts_file) as f:
                    prompts_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                prompts_data = {"prompts": {}, "script_previews": {}}

            prompts_data["script_previews"][str(result["message_id"])] = {
                "episode_id": episode_id,
                "podcast": podcast_name,
                "sent_at": datetime.now().isoformat()
            }

            with open(prompts_file, "w") as f:
                json.dump(prompts_data, f, indent=2)

            print(f"📝 Stored script preview message ID: {result['message_id']}")

    print(f"\n✅ Script generation complete!")
    print(f"   Status: {state['status']}")
    print(f"   Next step: User approves script")


def test_generation(podcast_name: str, idea: str):
    """Test script generation without creating an episode."""
    config = load_config()

    if podcast_name not in config["podcasts"]:
        raise ValueError(f"Unknown podcast: {podcast_name}")

    podcast_config = config["podcasts"][podcast_name]

    print(f"Testing script generation for: {podcast_config['name']}")
    print(f"Test idea: {idea}\n")

    # Load hardprompt and examples
    hardprompt = load_hardprompt(podcast_name)
    examples = load_context_examples(podcast_name)

    # Generate script
    print("Calling Claude API...")
    script = call_minimax(hardprompt, idea, examples)

    # Validate
    is_valid, message, stats = validate_script(script, podcast_config)

    print(f"\n{'='*60}")
    print(f"GENERATED SCRIPT ({stats['word_count']} words)")
    print(f"{'='*60}\n")
    print(script)
    print(f"\n{'='*60}")
    print(f"Validation: {message}")
    print(f"Duration: ~{stats['estimated_duration_seconds']//60}:{stats['estimated_duration_seconds']%60:02d}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Generate podcast scripts using Claude + hardprompts")
    parser.add_argument("--episode-id", help="Episode ID to generate script for")
    parser.add_argument("--test", action="store_true", help="Test mode (no episode required)")
    parser.add_argument("--podcast", help="Podcast name for test mode (explore, sololaw, 832weekends)")
    parser.add_argument("--idea", help="Episode idea for test mode")

    args = parser.parse_args()

    if args.test:
        if not args.podcast or not args.idea:
            parser.error("--test requires --podcast and --idea")
        test_generation(args.podcast, args.idea)
    elif args.episode_id:
        generate_script(args.episode_id)
    else:
        parser.error("Either --episode-id or --test required")


if __name__ == "__main__":
    main()
