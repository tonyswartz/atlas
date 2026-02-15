#!/usr/bin/env python3
"""
Shared Agent Memory System

Provides shared key-value store with TTL and locking for inter-agent coordination.
Prevents race conditions when multiple agents access shared resources.

Usage:
    from agents.shared_memory import SharedMemory

    memory = SharedMemory()

    # Set value with TTL
    memory.set("current_print", {"file": "bracket.gcode"}, ttl=3600)

    # Get value
    print_info = memory.get("current_print")

    # Acquire lock for critical section
    with memory.lock("tony_tasks_md"):
        # Safe to modify file
        sync_tasks()
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Any, Optional
import fcntl


class SharedMemory:
    """Shared key-value store with TTL and locking"""

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "data" / "agent_shared_memory.json"

        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.storage_path.exists():
            self._save_data({})

    def _load_data(self) -> dict:
        """Load data from disk with file locking"""
        with open(self.storage_path, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return data

    def _save_data(self, data: dict):
        """Save data to disk with file locking"""
        with open(self.storage_path, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock for writing
            try:
                json.dump(data, f, indent=2)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _cleanup_expired(self, data: dict) -> dict:
        """Remove expired entries"""
        now = datetime.now()
        cleaned = {}

        for key, entry in data.items():
            if "expires_at" in entry:
                expires_at = datetime.fromisoformat(entry["expires_at"])
                if expires_at <= now:
                    continue  # Skip expired

            cleaned[key] = entry

        return cleaned

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """
        Set value with optional TTL.

        Args:
            key: Key name
            value: Value (must be JSON-serializable)
            ttl_seconds: Time-to-live in seconds (None = never expires)
        """
        data = self._load_data()
        data = self._cleanup_expired(data)

        entry = {
            "value": value,
            "set_at": datetime.now().isoformat()
        }

        if ttl_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            entry["expires_at"] = expires_at.isoformat()

        data[key] = entry
        self._save_data(data)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value by key.

        Args:
            key: Key name
            default: Default value if key not found or expired

        Returns:
            Value or default
        """
        data = self._load_data()
        data = self._cleanup_expired(data)

        if key not in data:
            return default

        return data[key]["value"]

    def delete(self, key: str) -> bool:
        """
        Delete key.

        Returns:
            True if key existed and was deleted
        """
        data = self._load_data()

        if key in data:
            del data[key]
            self._save_data(data)
            return True

        return False

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired"""
        data = self._load_data()
        data = self._cleanup_expired(data)
        return key in data

    def keys(self) -> list[str]:
        """Get all non-expired keys"""
        data = self._load_data()
        data = self._cleanup_expired(data)
        return list(data.keys())

    def clear(self):
        """Clear all data"""
        self._save_data({})

    @contextmanager
    def lock(self, resource: str, timeout: int = 30):
        """
        Acquire lock for shared resource.

        Usage:
            with memory.lock("tony_tasks_md"):
                # Critical section - safe to modify resource
                modify_tony_tasks()

        Args:
            resource: Resource identifier
            timeout: Max seconds to wait for lock

        Raises:
            TimeoutError: If lock not acquired within timeout
        """
        lock_key = f"__lock__{resource}"
        acquired = False
        start = time.time()

        # Try to acquire lock
        while time.time() - start < timeout:
            data = self._load_data()
            data = self._cleanup_expired(data)

            if lock_key not in data:
                # Lock available - acquire it
                self.set(lock_key, {
                    "acquired_by": resource,
                    "acquired_at": datetime.now().isoformat()
                }, ttl_seconds=timeout)
                acquired = True
                break

            # Lock held by someone else - wait
            time.sleep(0.1)

        if not acquired:
            raise TimeoutError(f"Could not acquire lock for {resource} within {timeout}s")

        try:
            yield
        finally:
            # Release lock
            self.delete(lock_key)

    def get_locks(self) -> list[dict]:
        """Get all active locks"""
        data = self._load_data()
        data = self._cleanup_expired(data)

        locks = []
        for key, entry in data.items():
            if key.startswith("__lock__"):
                resource = key.replace("__lock__", "")
                locks.append({
                    "resource": resource,
                    "acquired_by": entry["value"]["acquired_by"],
                    "acquired_at": entry["value"]["acquired_at"],
                    "expires_at": entry.get("expires_at")
                })

        return locks

    def stats(self) -> dict:
        """Get memory statistics"""
        data = self._load_data()
        all_keys = len(data)

        data = self._cleanup_expired(data)
        active_keys = len(data)
        expired_keys = all_keys - active_keys

        locks = sum(1 for k in data.keys() if k.startswith("__lock__"))
        data_keys = active_keys - locks

        return {
            "total_keys": active_keys,
            "data_keys": data_keys,
            "active_locks": locks,
            "expired_keys": expired_keys
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Shared agent memory CLI")
    parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set key-value pair")
    parser.add_argument("--get", metavar="KEY", help="Get value by key")
    parser.add_argument("--delete", metavar="KEY", help="Delete key")
    parser.add_argument("--exists", metavar="KEY", help="Check if key exists")
    parser.add_argument("--keys", action="store_true", help="List all keys")
    parser.add_argument("--locks", action="store_true", help="Show active locks")
    parser.add_argument("--stats", action="store_true", help="Show memory statistics")
    parser.add_argument("--clear", action="store_true", help="Clear all data")
    parser.add_argument("--ttl", type=int, help="TTL in seconds for --set")

    args = parser.parse_args()

    memory = SharedMemory()

    if args.set:
        key, value = args.set
        # Try to parse as JSON, fallback to string
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass

        memory.set(key, value, ttl_seconds=args.ttl)
        print(f"✓ Set {key} = {value}")
        if args.ttl:
            print(f"  TTL: {args.ttl}s")

    elif args.get:
        value = memory.get(args.get)
        if value is None:
            print(f"Key '{args.get}' not found")
        else:
            print(json.dumps(value, indent=2))

    elif args.delete:
        deleted = memory.delete(args.delete)
        if deleted:
            print(f"✓ Deleted {args.delete}")
        else:
            print(f"Key '{args.delete}' not found")

    elif args.exists:
        exists = memory.exists(args.exists)
        print(f"{args.exists}: {'exists' if exists else 'not found'}")

    elif args.keys:
        keys = memory.keys()
        print(f"Keys ({len(keys)}):")
        for key in keys:
            if not key.startswith("__lock__"):
                value = memory.get(key)
                print(f"  {key}: {json.dumps(value)[:60]}")

    elif args.locks:
        locks = memory.get_locks()
        print(f"Active Locks ({len(locks)}):")
        for lock in locks:
            print(f"  {lock['resource']}")
            print(f"    Acquired by: {lock['acquired_by']}")
            print(f"    Acquired at: {lock['acquired_at']}")
            print(f"    Expires at: {lock.get('expires_at', 'never')}")

    elif args.stats:
        stats = memory.stats()
        print("Shared Memory Statistics:")
        print(f"  Total keys: {stats['total_keys']}")
        print(f"  Data keys: {stats['data_keys']}")
        print(f"  Active locks: {stats['active_locks']}")
        print(f"  Expired keys cleaned: {stats['expired_keys']}")

    elif args.clear:
        memory.clear()
        print("✓ Cleared all shared memory")

    else:
        parser.print_help()
