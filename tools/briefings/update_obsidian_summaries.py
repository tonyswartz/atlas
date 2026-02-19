#!/usr/bin/env python3
"""
Update Obsidian case law files with cached summaries.
Adds holdings to cases that are missing them.
"""

import json
import re
from pathlib import Path

CASE_LAW_DIR = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Case Law/WA Criminal")
CACHE_FILE = Path('/Users/printer/atlas/data/case_law_summaries.json')

def update_obsidian_summaries():
    """Update Obsidian files with cached summaries."""

    if not CACHE_FILE.exists():
        print("No summary cache found.")
        return

    cache = json.loads(CACHE_FILE.read_text())
    print(f"Loaded {len(cache)} cached summaries\n")

    updated_count = 0
    skipped_count = 0

    for file_path in CASE_LAW_DIR.glob("*.md"):
        content = file_path.read_text()
        original_content = content

        # Find all case sections
        case_sections = re.split(r'(\n###\s+.+?\n)', content)

        # Process pairs: section header + section content
        for i in range(1, len(case_sections), 2):
            if i + 1 >= len(case_sections):
                break

            header = case_sections[i]
            section_content = case_sections[i + 1]

            # Check if this section already has a holding
            if '**Holding:**' in section_content:
                continue

            # Extract URL from section
            url_match = re.search(r'\*\*Opinion:\*\*\s+\[Link\]\((.+?)\)', section_content)
            if not url_match:
                continue

            url = url_match.group(1)

            # Check if we have a cached summary for this URL
            if url not in cache:
                continue

            summary = cache[url]
            case_name = header.replace('###', '').strip()

            print(f"Updating: {case_name[:60]}...")
            print(f"  File: {file_path.name}")
            print(f"  Summary: {summary[:80]}...")

            # Insert holding before the closing ---
            if section_content.strip().endswith('---'):
                # Remove trailing ---
                section_content = section_content.rstrip()
                if section_content.endswith('---'):
                    section_content = section_content[:-3].rstrip()

                # Add holding
                section_content += f"\n**Holding:** {summary}\n\n---\n"
            else:
                # No trailing ---, just append
                section_content += f"\n**Holding:** {summary}\n\n"

            # Update the section
            case_sections[i + 1] = section_content
            updated_count += 1
            print(f"  ✓ Added holding\n")

        # Reconstruct content
        new_content = ''.join(case_sections)

        # Only write if changed
        if new_content != original_content:
            file_path.write_text(new_content)
            print(f"  📝 Saved {file_path.name}\n")

    print("="*60)
    print(f"Update complete:")
    print(f"  Cases updated: {updated_count}")
    print("="*60)

if __name__ == "__main__":
    update_obsidian_summaries()
