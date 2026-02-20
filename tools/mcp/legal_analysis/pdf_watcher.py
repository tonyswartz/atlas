#!/usr/bin/env python3
"""
Legal File Sanitization Watcher

Monitors ~/Dropbox/MCP Analysis/originals/ for new files.
When detected:
1. For PDFs: Extracts text and sanitizes to .txt file
2. For transcripts: Sanitizes text content
3. Saves sanitized .txt to ~/Dropbox/MCP Analysis/sanitized/
4. Saves PII mapping to .sanitization_maps/
5. Keeps original in originals/ folder

SECURITY: MCP server ONLY has access to sanitized/ folder - cannot see originals.

Run via launchd for automatic background monitoring.
"""

import time
import sys
from pathlib import Path
from datetime import datetime
from sanitize_to_text import TextSanitizer, save_sanitization_map

# Directories
BASE_DIR = Path.home() / "Library/CloudStorage/Dropbox/MCP Analysis"
ORIGINALS_DIR = BASE_DIR / "originals"
SANITIZED_DIR = BASE_DIR / "sanitized"
MAPS_DIR = BASE_DIR / ".sanitization_maps"

# State file to track processed PDFs
STATE_FILE = Path.home() / "atlas/data/pdf_watcher_state.txt"


def get_processed_files() -> set:
    """Load list of already-processed PDF filenames."""
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.touch()
        return set()

    with open(STATE_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())


def mark_file_processed(filename: str) -> None:
    """Add filename to processed list."""
    with open(STATE_FILE, 'a') as f:
        f.write(f"{filename}\n")


def process_new_files() -> None:
    """Check for new files (PDFs and transcripts) and sanitize them."""
    # Ensure directories exist
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    SANITIZED_DIR.mkdir(parents=True, exist_ok=True)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)

    # Find all PDFs and text files in originals/
    pdf_files = list(ORIGINALS_DIR.glob("*.pdf"))
    txt_files = list(ORIGINALS_DIR.glob("*.txt"))
    all_files = pdf_files + txt_files

    if not all_files:
        # No files to process - clear sanitized folder if it has files
        if any(SANITIZED_DIR.glob("*.txt")):
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No files in originals/ - clearing sanitized/")
            for txt_file in SANITIZED_DIR.glob("*.txt"):
                txt_file.unlink()
        return

    # Check for new files
    processed = get_processed_files()
    current_files = {f.name for f in all_files}
    new_files = current_files - processed

    if new_files:
        # New files detected - clear sanitized folder and state file, re-process everything
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New files detected: {len(new_files)}")
        print(f"  Clearing sanitized/ and re-processing all {len(all_files)} files...")

        for txt_file in SANITIZED_DIR.glob("*.txt"):
            try:
                txt_file.unlink()
            except Exception as e:
                print(f"  Warning: Could not delete {txt_file.name}: {e}", file=sys.stderr)

        # Clear state file so all files get re-processed
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    else:
        # No new files - nothing to do
        return

    for file_path in all_files:
        file_type = "PDF" if file_path.suffix.lower() == ".pdf" else "transcript"
        print(f"  Processing {file_type}: {file_path.name}")

        try:
            # For both PDFs and text files, output is .txt
            output_name = file_path.stem + ".txt"
            output_path = SANITIZED_DIR / output_name

            # Use TextSanitizer for all files (extracts from PDF if needed)
            sanitizer = TextSanitizer()

            if file_path.suffix.lower() == ".pdf":
                # Extract text from PDF and sanitize
                sanitized_text, mapping = sanitizer.sanitize_pdf_to_text(file_path)
            else:
                # Read text file and sanitize
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                sanitizer._extract_names(text)
                sanitized_text = sanitizer._sanitize_text(text)
                mapping = sanitizer.entity_map

            # Save sanitized text
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(sanitized_text)

            # Save mapping
            uuid = save_sanitization_map(file_path, mapping, MAPS_DIR)

            print(f"  ✓ Sanitized text saved: {output_path.name}")
            print(f"  ✓ Mapping saved: {uuid}.json")
            print(f"  ✓ Redacted {len(mapping)} entities")
            for initials, name in sorted(mapping.items()):
                print(f"    {initials} ← {name}")

            # Mark as processed
            mark_file_processed(file_path.name)

        except Exception as e:
            print(f"  ✗ ERROR processing {file_path.name}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()


def watch_loop(interval: int = 30) -> None:
    """Run continuous watch loop."""
    print(f"Legal File Sanitization Watcher started")
    print(f"Monitoring: {ORIGINALS_DIR}")
    print(f"Output to: {SANITIZED_DIR}")
    print(f"Watching: *.pdf, *.txt (transcripts)")
    print(f"Security: MCP server ONLY has access to sanitized/ folder")
    print(f"Check interval: {interval}s\n")

    while True:
        try:
            process_new_files()
        except Exception as e:
            print(f"Error in watch loop: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

        time.sleep(interval)


def main():
    """CLI interface."""
    import argparse

    parser = argparse.ArgumentParser(description="PDF Redaction Watcher")
    parser.add_argument('--once', action='store_true', help='Run once and exit (default: continuous loop)')
    parser.add_argument('--interval', type=int, default=30, help='Check interval in seconds (default: 30)')

    args = parser.parse_args()

    if args.once:
        # Single run mode (for testing)
        process_new_files()
    else:
        # Continuous watch mode (for launchd)
        watch_loop(interval=args.interval)


if __name__ == "__main__":
    main()
