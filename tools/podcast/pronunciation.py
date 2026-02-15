#!/usr/bin/env python3
"""
Podcast Pronunciation Processor

Applies pronunciation fixes to scripts before TTS synthesis.
Supports permanent dictionary + one-off fixes.
"""

import re
from pathlib import Path
from typing import Dict


def load_pronunciation_dict() -> Dict[str, str]:
    """Load pronunciation dictionary from Obsidian vault."""
    dict_path = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Podcasts/Pronunciation Dictionary.md")

    if not dict_path.exists():
        return {}

    content = dict_path.read_text(encoding="utf-8")
    pronunciations = {}

    # Parse markdown list items: "- Original → Phonetic"
    pattern = r'^[-*]\s+(.+?)\s+→\s+(.+?)$'

    for line in content.split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            original = match.group(1).strip()
            phonetic = match.group(2).strip()
            pronunciations[original] = phonetic

    return pronunciations


def parse_one_off_fixes(approval_message: str) -> Dict[str, str]:
    """
    Parse one-off pronunciation fixes from approval message.

    Format: "Approved, fix: word1=pronunciation1, word2=pronunciation2"

    Returns:
        Dictionary of word → pronunciation fixes
    """
    one_off = {}

    # Look for "fix:" followed by comma-separated key=value pairs
    fix_pattern = r'fix:\s*(.+?)(?:\n|$)'
    match = re.search(fix_pattern, approval_message, re.IGNORECASE)

    if match:
        fixes_str = match.group(1)
        # Split by comma and parse each fix
        for fix in fixes_str.split(','):
            fix = fix.strip()
            if '=' in fix:
                word, pronunciation = fix.split('=', 1)
                one_off[word.strip()] = pronunciation.strip()

    return one_off


def apply_pronunciation_fixes(script: str, permanent_dict: Dict[str, str], one_off_fixes: Dict[str, str] = None) -> tuple[str, list]:
    """
    Apply pronunciation fixes to script.

    Args:
        script: The script text
        permanent_dict: Permanent pronunciation dictionary
        one_off_fixes: Optional one-off fixes for this episode

    Returns:
        (modified_script, list_of_fixes_applied)
    """
    if one_off_fixes is None:
        one_off_fixes = {}

    # Combine dictionaries (one-off overrides permanent)
    all_fixes = {**permanent_dict, **one_off_fixes}

    if not all_fixes:
        return script, []

    modified = script
    applied = []

    for original, phonetic in all_fixes.items():
        # Case-insensitive replacement, but preserve case of first letter
        pattern = re.compile(re.escape(original), re.IGNORECASE)

        # Count matches before replacing
        matches = pattern.findall(modified)
        if matches:
            modified = pattern.sub(phonetic, modified)
            applied.append(f"{original} → {phonetic} ({len(matches)}x)")

    return modified, applied


def main():
    """Test the pronunciation system."""
    import sys

    # Load dictionary
    pron_dict = load_pronunciation_dict()
    print(f"Loaded {len(pron_dict)} pronunciation rules\n")

    # Test script
    test_script = """
    Today we're talking about WIP limits and Kanban boards.
    The API endpoint uses a URL with voir dire parameters.
    """

    print("Original script:")
    print(test_script)

    # Apply fixes
    fixed, applied = apply_pronunciation_fixes(test_script, pron_dict)

    print("\nFixes applied:")
    for fix in applied:
        print(f"  • {fix}")

    print("\nFixed script:")
    print(fixed)

    # Test one-off fixes
    print("\n" + "="*60)
    print("Testing one-off fixes from approval message:\n")

    approval = "Approved, fix: attorney=uh-TUR-nee, SQL=sequel"
    one_off = parse_one_off_fixes(approval)
    print(f"Parsed one-off fixes: {one_off}\n")

    test_script2 = "The attorney used SQL for the database."
    fixed2, applied2 = apply_pronunciation_fixes(test_script2, pron_dict, one_off)

    print("Original:", test_script2)
    print("Fixed:", fixed2)
    print("Applied:", applied2)


if __name__ == "__main__":
    main()
