"""Centralized credential loading for Atlas tools.

This module provides a single, robust way to load credentials that works
reliably in both launchd (with envchain) and cron (with .env fallback).

Usage:
    from tools.common.credentials import get_credential

    token = get_credential("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not available")
        sys.exit(1)
"""

import os
from pathlib import Path
from typing import Optional


# Cache for loaded .env credentials
_ENV_CACHE: dict[str, str] = {}
_ENV_LOADED = False


def _load_env_file() -> dict[str, str]:
    """Load credentials from .env file (fallback for cron jobs)."""
    global _ENV_CACHE, _ENV_LOADED

    if _ENV_LOADED:
        return _ENV_CACHE

    repo_root = Path(__file__).resolve().parent.parent.parent
    env_path = repo_root / ".env"

    if not env_path.exists():
        _ENV_LOADED = True
        return {}

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                _ENV_CACHE[key.strip()] = value.strip().strip("\"'")
    except Exception:
        pass

    _ENV_LOADED = True
    return _ENV_CACHE


def get_credential(key: str, required: bool = False) -> Optional[str]:
    """Get a credential from environment or .env file.

    Tries in order:
    1. Environment variable (set by envchain in launchd jobs)
    2. .env file (fallback for cron jobs)

    Args:
        key: Credential name (e.g., "TELEGRAM_BOT_TOKEN")
        required: If True, raises ValueError when credential not found

    Returns:
        Credential value, or None if not found and not required

    Raises:
        ValueError: If required=True and credential not found
    """
    # Try environment first (envchain sets this)
    value = os.environ.get(key, "").strip()
    if value:
        return value

    # Fall back to .env file
    env_cache = _load_env_file()
    value = env_cache.get(key, "").strip()
    if value:
        return value

    if required:
        raise ValueError(f"{key} not found in environment or .env file")

    return None


def get_telegram_token() -> Optional[str]:
    """Get TELEGRAM_BOT_TOKEN credential."""
    return get_credential("TELEGRAM_BOT_TOKEN")


def get_mindsetlog_db_url() -> Optional[str]:
    """Get MINDSETLOG_DB_URL credential."""
    return get_credential("MINDSETLOG_DB_URL")


def get_legalkanban_db_url() -> Optional[str]:
    """Get LEGALKANBAN credential."""
    return get_credential("LEGALKANBAN")
