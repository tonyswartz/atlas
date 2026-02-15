#!/usr/bin/env python3
"""
Podcast Weekly Prompt

Sends weekly episode idea prompts to user via Telegram.

Usage:
    python tools/podcast/weekly_prompt.py --podcast explore
    python tools/podcast/weekly_prompt.py  # Auto-detect based on today's day
"""

import sys
import json
import yaml
import argparse
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


def send_telegram(message: str, chat_id: str) -> dict:
    """Send message to Telegram. Returns dict with success and message_id."""
    from tools.common.credentials import get_telegram_token

    token = get_telegram_token()
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not found")
        return {"success": False, "message_id": None}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    # Retry logic (3 attempts with exponential backoff)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    response_data = json.loads(resp.read())
                    message_id = response_data.get("result", {}).get("message_id")
                    return {"success": True, "message_id": message_id}
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                import time
                time.sleep(2 ** attempt)  # 1s, 2s, 4s

    return {"success": False, "message_id": None}


def load_ideas_suggestions(podcast_name: str, config: dict, max_suggestions: int = 3) -> list[str]:
    """Load a few idea suggestions from Obsidian Podcasts/{podcast_name}/Ideas.md."""
    obsidian_base = Path(config["paths"]["obsidian_podcasts"])
    ideas_path = obsidian_base / podcast_name / "Ideas.md"
    if not ideas_path.exists():
        return []
    try:
        text = ideas_path.read_text(encoding="utf-8")
    except Exception:
        return []
    # Collect lines that are list items (start with "- ")
    ideas = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- ") and len(line) > 2:
            ideas.append(line[2:].strip())
    if not ideas:
        return []
    # Pick up to max_suggestions (use first few for consistency, or random if you prefer)
    import random
    if len(ideas) <= max_suggestions:
        return ideas
    return random.sample(ideas, max_suggestions)


def log_prompt(podcast_name: str):
    """Log prompt to pending file."""
    config = load_config()
    pending_file = REPO_ROOT / config["telegram"]["pending_file"]

    # Ensure parent directory exists
    pending_file.parent.mkdir(parents=True, exist_ok=True)

    # Append to log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(pending_file, "a") as f:
        f.write(f"[{timestamp}] Prompt sent: {podcast_name}\n")


def send_prompt(podcast_name: str):
    """Send episode idea prompt for a specific podcast."""
    config = load_config()

    if podcast_name not in config["podcasts"]:
        print(f"❌ Unknown podcast: {podcast_name}")
        print(f"Available: {', '.join(config['podcasts'].keys())}")
        sys.exit(1)

    podcast = config["podcasts"][podcast_name]
    # Use fallback_chat_id if chat_id is placeholder
    chat_id = config["telegram"]["chat_id"]
    if "CHAT_ID_HERE" in str(chat_id):
        chat_id = config["telegram"].get("fallback_chat_id", 8241581699)

    suggestions = load_ideas_suggestions(podcast_name, config, max_suggestions=3)
    suggestion_block = ""
    reply_hint = "Reply with your idea, notes, or topic outline."
    if suggestions:
        suggestion_block = "\n**Suggestions from your list:**\n" + "\n".join(f"• {s}" for s in suggestions) + "\n\n"
        reply_hint = "Reply with one of the suggestions above, or your own idea."
    message = f"""🎙️ **{podcast['name']}** Episode Ideas

What would you like to talk about in the next episode?
{suggestion_block}{reply_hint}

_{podcast['description']}_
_Tone: {podcast['tone']}_
_Length: {podcast['target_length']}_
"""

    print(f"Sending prompt for: {podcast['name']}")
    print(f"Chat ID: {chat_id}")
    print(f"Message:\n{message}\n")

    result = send_telegram(message, str(chat_id))
    if result["success"]:
        print("✅ Prompt sent successfully")
        log_prompt(podcast_name)

        # Store message ID for reply detection
        if result["message_id"]:
            prompts_file = REPO_ROOT / "data" / "podcast_prompts.json"
            try:
                with open(prompts_file) as f:
                    prompts_data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                prompts_data = {"prompts": {}, "script_previews": {}}

            prompts_data["prompts"][str(result["message_id"])] = {
                "podcast": podcast_name,
                "sent_at": datetime.now().isoformat(),
                "chat_id": str(chat_id)
            }

            with open(prompts_file, "w") as f:
                json.dump(prompts_data, f, indent=2)

            print(f"📝 Stored prompt message ID: {result['message_id']}")

        return True
    else:
        print("❌ Failed to send prompt")
        return False


def auto_detect_podcast():
    """Auto-detect which podcast should be prompted based on today's day."""
    config = load_config()
    today = datetime.now().weekday()  # 0=Monday, 6=Sunday

    for podcast_name, podcast_config in config["podcasts"].items():
        if podcast_config.get("prompt_day") == today:
            return podcast_name

    return None


def main():
    parser = argparse.ArgumentParser(description="Send weekly podcast episode idea prompts")
    parser.add_argument(
        "--podcast",
        choices=["explore", "sololaw", "832weekends"],
        help="Which podcast to prompt (auto-detects if not specified)"
    )

    args = parser.parse_args()

    if args.podcast:
        podcast_name = args.podcast
    else:
        podcast_name = auto_detect_podcast()
        if not podcast_name:
            print("ℹ️  No podcast scheduled for today")
            print("Use --podcast to send manually")
            sys.exit(0)

    success = send_prompt(podcast_name)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
