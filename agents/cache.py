#!/usr/bin/env python3
"""
Agent Result Caching System

Decorators for caching expensive agent operations.
Reduces API calls, improves response times, handles rate limits gracefully.

Usage:
    from agents.cache import cache_result, invalidate_cache

    @cache_result(ttl=3600, key_fn=lambda case_id: f"case_{case_id}")
    def get_case_info(case_id: int):
        # Expensive DB query
        return query_legalkanban(case_id)

    @invalidate_cache(keys=["case_{case_id}"])
    def update_case(case_id: int, data: dict):
        # Invalidates cached case data
        update_legalkanban(case_id, data)
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Any, Optional


class AgentCache:
    """Simple file-based cache for agent results"""

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent / "data" / "agent_cache"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key"""
        # Hash key to avoid filesystem issues
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value.

        Returns:
            Cached value or None if not found/expired
        """
        cache_file = self._get_cache_file(key)

        if not cache_file.exists():
            return None

        try:
            with open(cache_file) as f:
                data = json.load(f)

            # Check expiration
            if "expires_at" in data:
                expires_at = datetime.fromisoformat(data["expires_at"])
                if datetime.now() >= expires_at:
                    cache_file.unlink()  # Remove expired
                    return None

            return data["value"]

        except (json.JSONDecodeError, KeyError):
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """
        Set cached value with optional TTL.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_seconds: Time-to-live in seconds (None = never expires)
        """
        cache_file = self._get_cache_file(key)

        data = {
            "key": key,
            "value": value,
            "cached_at": datetime.now().isoformat()
        }

        if ttl_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            data["expires_at"] = expires_at.isoformat()

        with open(cache_file, 'w') as f:
            json.dump(data, f, indent=2)

    def delete(self, key: str) -> bool:
        """
        Delete cached value.

        Returns:
            True if key existed and was deleted
        """
        cache_file = self._get_cache_file(key)

        if cache_file.exists():
            cache_file.unlink()
            return True

        return False

    def clear(self):
        """Clear all cached values"""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()

    def stats(self) -> dict:
        """Get cache statistics"""
        total = 0
        expired = 0
        valid = 0
        size_bytes = 0

        for cache_file in self.cache_dir.glob("*.json"):
            total += 1
            size_bytes += cache_file.stat().st_size

            try:
                with open(cache_file) as f:
                    data = json.load(f)

                if "expires_at" in data:
                    expires_at = datetime.fromisoformat(data["expires_at"])
                    if datetime.now() >= expires_at:
                        expired += 1
                    else:
                        valid += 1
                else:
                    valid += 1

            except (json.JSONDecodeError, KeyError):
                pass

        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": expired,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / 1024 / 1024, 2)
        }


# Global cache instance
_cache = AgentCache()


def cache_result(ttl: int = 3600, key_fn: Optional[Callable] = None):
    """
    Decorator to cache function results.

    Args:
        ttl: Time-to-live in seconds (default: 1 hour)
        key_fn: Function to generate cache key from arguments
                If None, uses function name + args

    Example:
        @cache_result(ttl=600, key_fn=lambda spool_id: f"spool_{spool_id}")
        def get_spool_info(spool_id: int):
            return query_jeevesui(spool_id)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_fn:
                cache_key = key_fn(*args, **kwargs)
            else:
                # Default: function name + args hash
                args_str = json.dumps([args, kwargs], sort_keys=True, default=str)
                args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:12]
                cache_key = f"{func.__name__}_{args_hash}"

            # Try cache first
            cached = _cache.get(cache_key)
            if cached is not None:
                return cached

            # Cache miss - execute function
            result = func(*args, **kwargs)

            # Store result
            _cache.set(cache_key, result, ttl_seconds=ttl)

            return result

        # Attach cache control methods
        wrapper.cache_clear = lambda: _cache.clear()
        wrapper.cache_delete = lambda *args, **kwargs: _cache.delete(
            key_fn(*args, **kwargs) if key_fn else f"{func.__name__}"
        )

        return wrapper

    return decorator


def invalidate_cache(keys: list[str]):
    """
    Decorator to invalidate cache keys after function execution.

    Args:
        keys: List of cache key patterns with {{variable}} placeholders

    Example:
        @invalidate_cache(keys=["case_{{case_id}}", "tasks_{{case_id}}"])
        def update_case(case_id: int, data: dict):
            # Invalidates cached case and task data
            update_legalkanban(case_id, data)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Execute function
            result = func(*args, **kwargs)

            # Invalidate cache keys
            # Build variable mapping from args
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            variables = bound.arguments

            for key_pattern in keys:
                # Interpolate variables into key
                cache_key = key_pattern
                for var_name, var_value in variables.items():
                    placeholder = f"{{{{{var_name}}}}}"
                    cache_key = cache_key.replace(placeholder, str(var_value))

                _cache.delete(cache_key)

            return result

        return wrapper

    return decorator


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent cache CLI")
    parser.add_argument("--stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--clear", action="store_true", help="Clear all cached data")
    parser.add_argument("--get", metavar="KEY", help="Get cached value")
    parser.add_argument("--delete", metavar="KEY", help="Delete cached value")

    args = parser.parse_args()

    if args.stats:
        stats = _cache.stats()
        print("\nCache Statistics:")
        print(f"  Total entries: {stats['total_entries']}")
        print(f"  Valid entries: {stats['valid_entries']}")
        print(f"  Expired entries: {stats['expired_entries']}")
        print(f"  Size: {stats['size_mb']} MB")
        print()

    elif args.clear:
        _cache.clear()
        print("✓ Cleared all cached data")

    elif args.get:
        value = _cache.get(args.get)
        if value is None:
            print(f"Key '{args.get}' not found or expired")
        else:
            print(json.dumps(value, indent=2))

    elif args.delete:
        deleted = _cache.delete(args.delete)
        if deleted:
            print(f"✓ Deleted cache key '{args.delete}'")
        else:
            print(f"Key '{args.delete}' not found")

    else:
        parser.print_help()
