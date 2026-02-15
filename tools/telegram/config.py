"""
Configuration loader.

Reads args/telegram.yaml and .env, resolves all paths relative to the repo root.
Caches config after first load.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

# Repo root is two levels up from this file (tools/telegram/config.py)
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()

# Load .env once at import time (if present). When using envchain, vars are already in os.environ.
_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

_config_cache = None


def load_config() -> dict:
    """Load and cache the telegram config from args/telegram.yaml and .env."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    yaml_path = REPO_ROOT / "args" / "telegram.yaml"
    with open(yaml_path, "r") as f:
        _config_cache = yaml.safe_load(f)

    # If allowed_user_ids is empty and TELEGRAM_ID is set in .env, use it as the single allowed user
    bot = _config_cache.setdefault("bot", {})
    allowed = bot.get("allowed_user_ids") or []
    if not allowed:
        env_id = os.environ.get("TELEGRAM_ID", "").strip()
        if env_id and env_id.isdigit():
            bot["allowed_user_ids"] = [int(env_id)]
    return _config_cache


def get_repo_root() -> Path:
    """Return the absolute path to the repo root."""
    return REPO_ROOT
