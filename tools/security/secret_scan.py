#!/usr/bin/env python3
"""Scan tracked files for accidental secret patterns. Exit 1 if any found.

Run from repo root:
  python3 tools/security/secret_scan.py [path ...]
With no paths, scans all files tracked by git (respecting .gitignore).
Use in pre-commit to block commits that contain secrets.

Patterns:
  - Telegram bot token: digits:alphanumeric (e.g. 1234567890:AAH...)
  - Generic API key / token: long base64-like or alphanumeric strings in docs
  - Common env var names with obvious secret values on same line
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Patterns that indicate a likely secret (match must be in a line we consider risky)
PATTERNS = [
    (
        "telegram_bot_token",
        re.compile(r"\d{8,11}\s*:\s*[A-Za-z0-9_-]{35,}"),
        "Telegram bot token (digits:alphanumeric); use .env or envchain",
    ),
    (
        "generic_token_like",
        re.compile(r"(?:token|secret|password|api_key|apikey)\s*[=:]\s*['\"]?[A-Za-z0-9_-]{32,}['\"]?", re.I),
        "Token/secret/password with long value; use placeholder or env",
    ),
    (
        "bearer_or_key_in_xml",
        re.compile(r"<string>[A-Za-z0-9_-]{30,}</string>"),
        "Long string in plist/XML (could be token); use placeholder",
    ),
]

# Files/dirs we never scan (binary, generated, or allowed to have long strings)
SKIP_PATHS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pyc",
    ".db",
    ".sqlite",
    "package-lock.json",
    "poetry.lock",
    ".env",
    ".env.example",
    "secret_scan.py",  # this script
}

# Only run pattern "bearer_or_key_in_xml" in these extensions (to avoid false positives in code)
XML_LIKE_EXTENSIONS = {".md", ".xml", ".plist", ".yaml", ".yml", ".json"}


def is_skipped(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT) if path.is_absolute() else path
    parts = rel.parts
    for skip in SKIP_PATHS:
        if skip in parts or path.name == skip or path.suffix == skip:
            return True
    return False


def get_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        return []
    raw = result.stdout.decode("utf-8", errors="replace").strip("\0")
    if not raw:
        return []
    return [REPO_ROOT / p for p in raw.split("\0") if p.strip()]


def scan_file(path: Path, results: list[tuple[str, int, str, str]]) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    rel = path.relative_to(REPO_ROOT)
    ext = path.suffix.lower()
    for name, pattern, msg in PATTERNS:
        if name == "bearer_or_key_in_xml" and ext not in XML_LIKE_EXTENSIONS:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                # Allow intentional placeholders (don't flag lines that already say REDACTED etc.)
                lower = line.lower()
                if "redact" in lower or "placeholder" in lower or "use_env" in lower:
                    continue
                results.append((str(rel), i, name, msg))


def main() -> int:
    if len(sys.argv) > 1:
        paths = []
        for p in sys.argv[1:]:
            path = Path(p).resolve()
            if not path.is_file():
                print(f"Skip (not file): {path}", file=sys.stderr)
                continue
            paths.append(path)
    else:
        paths = get_tracked_files()

    results: list[tuple[str, int, str, str]] = []
    for path in paths:
        if is_skipped(path):
            continue
        if not path.is_file():
            continue
        scan_file(path, results)

    if not results:
        print("OK: no secret patterns found.")
        return 0

    print("SECRET SCAN FAILED: possible secrets in tracked files.", file=sys.stderr)
    for rel, line_no, name, msg in results:
        print(f"  {rel}:{line_no} [{name}] — {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
