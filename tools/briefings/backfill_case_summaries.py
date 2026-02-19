#!/usr/bin/env python3
"""
Backfill missing case law summaries for cases already saved in Obsidian.
Generates summaries for cases that were saved before the summary feature was working.
"""

import json
import sys
from pathlib import Path

# Import from daily_brief
sys.path.insert(0, str(Path(__file__).parent))
from daily_brief import fetch_pdf_text, summarize_case_with_llm, _load_summary_cache, _save_summary_cache

def backfill_summaries():
    """Generate summaries for cases that are missing them."""

    cases_file = Path('/Users/printer/atlas/data/cases_to_backfill.json')
    if not cases_file.exists():
        print("No cases_to_backfill.json found. Run the identification script first.")
        return

    cases = json.loads(cases_file.read_text())

    print(f"Backfilling summaries for {len(cases)} cases...\n")

    cache = _load_summary_cache()
    success_count = 0
    skipped_count = 0
    error_count = 0

    for i, case in enumerate(cases, 1):
        name = case['name']
        url = case['url']
        date = case['date']

        print(f"{i}/{len(cases)}: {name[:60]}...")

        # Check if already in cache
        if url in cache:
            print(f"  ✓ Already in cache, skipping")
            skipped_count += 1
            continue

        # Fetch PDF and generate summary
        try:
            print(f"  Fetching PDF...")
            text = fetch_pdf_text(url)

            if len(text) < 200:
                print(f"  ✗ PDF too short ({len(text)} chars), skipping")
                error_count += 1
                continue

            print(f"  Generating summary...")
            summary = summarize_case_with_llm(text, name, url)

            if summary:
                print(f"  ✓ Summary generated ({len(summary)} chars)")
                success_count += 1
            else:
                print(f"  ✗ Summary generation failed")
                error_count += 1

        except Exception as e:
            print(f"  ✗ Error: {e}")
            error_count += 1

        print()

    print("\n" + "="*60)
    print(f"Backfill complete:")
    print(f"  Success: {success_count}")
    print(f"  Skipped (already cached): {skipped_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {len(cases)}")
    print("="*60)

if __name__ == "__main__":
    backfill_summaries()
