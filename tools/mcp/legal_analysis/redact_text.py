#!/usr/bin/env python3
"""
Text Redaction Tool for Transcripts

Sanitizes body cam and 911 transcripts while preserving:
- Speaker labels ([OFFICER], [DEFENDANT])
- Timestamps
- Conversation flow
"""

import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Set


class TextRedactor:
    """Redacts PII from text transcripts."""

    def __init__(self):
        self.entity_map = {}
        self.names_registry: Set[str] = set()

    def redact_text(self, input_path: Path, output_path: Path) -> Dict[str, str]:
        """Redact PII from text file and return mapping."""

        # Read original text
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()

        # Extract names first
        self._extract_names(text)
        print(f"  Found {len(self.names_registry)} unique names to redact")

        # Redact all PII
        redacted = text

        # Redact all names found
        for name in sorted(self.names_registry, key=len, reverse=True):
            initials = self._get_initials(name)
            # Replace full name
            redacted = re.sub(rf'\b{re.escape(name)}\b', initials, redacted, flags=re.IGNORECASE)

            # Also replace individual name parts (last names alone)
            parts = name.split()
            if len(parts) >= 2:
                last_name = parts[-1].strip('.,')
                if len(last_name) > 3:
                    redacted = re.sub(rf'\b{re.escape(last_name)}\b', initials, redacted, flags=re.IGNORECASE)

        # Redact fixed patterns
        redacted = self._redact_fixed_patterns(redacted)

        # Save redacted text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(redacted)

        return self.entity_map

    def _extract_names(self, text: str) -> None:
        """Extract names from transcript text."""

        # Names with titles (Deputy Smith, Officer Jones, Trooper Brown)
        title_pattern = r'\b(Deputy|Officer|Trooper|Sgt\.|Sergeant|Detective|Det\.|Agent|Dr\.|Mr\.|Ms\.|Mrs\.)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){0,2})\b'
        for match in re.finditer(title_pattern, text):
            name = match.group(2).strip()
            name = re.sub(r'[,.]$', '', name)
            if len(name.split()) >= 2 or len(name) > 4:  # Full name or substantial single name
                self.names_registry.add(name)
                self._add_to_map(name)

        # Full names in narrative (look for capitalized word patterns)
        # "My name is John Smith" or similar
        name_intro_pattern = r'(?:name is|I\'m|this is|called)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
        for match in re.finditer(name_intro_pattern, text, re.IGNORECASE):
            name = match.group(1).strip()
            name = re.sub(r'[,.]$', '', name)
            if len(name.split()) >= 2:
                self.names_registry.add(name)
                self._add_to_map(name)

    def _redact_fixed_patterns(self, text: str) -> str:
        """Redact fixed PII patterns."""

        # SSN
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)

        # Phone numbers
        text = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', text)

        # License plates
        text = re.sub(r'\b[A-Z]{2,3}[-\s]?\d{3,4}\b', '[PLATE]', text)

        # Addresses
        text = re.sub(
            r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b',
            '[ADDRESS]',
            text
        )

        # Driver's license numbers (alphanumeric)
        text = re.sub(r'\b[A-Z]{1,}[0-9]{3,}[A-Z0-9]{3,}\b', '[LICENSE]', text)

        # Badge numbers
        text = re.sub(r'(?:Badge|ID)\s*#?:?\s*\d{3,6}', '[BADGE]', text)

        return text

    def _add_to_map(self, name: str) -> None:
        """Add name to entity map with initials."""
        initials = self._get_initials(name)
        if initials not in self.entity_map:
            self.entity_map[initials] = name

    def _get_initials(self, name: str) -> str:
        """Generate initials from name."""
        parts = name.split()
        initials = ''.join([p[0].upper() for p in parts if p and p[0].isupper()])

        # Handle duplicates
        base = initials
        counter = 1
        while initials in self.entity_map:
            initials = f"{base}{counter}"
            counter += 1

        return initials


def save_sanitization_map(file_path: Path, mapping: Dict[str, str], output_dir: Path) -> str:
    """Save PII mapping to JSON."""
    unique_str = f"{file_path.name}_{datetime.now().isoformat()}"
    uuid = hashlib.md5(unique_str.encode()).hexdigest()[:16]

    map_data = {
        "uuid": uuid,
        "original_file": str(file_path),
        "timestamp": datetime.now().isoformat(),
        "mapping": mapping
    }

    map_file = output_dir / f"{uuid}.json"
    with open(map_file, 'w') as f:
        json.dump(map_data, f, indent=2)

    return uuid


def main():
    """CLI interface."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python redact_text.py <input.txt> <output.txt>")
        sys.exit(1)

    input_path = Path(sys.argv[1]).expanduser()
    output_path = Path(sys.argv[2]).expanduser()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    print(f"Redacting: {input_path.name}")

    redactor = TextRedactor()
    mapping = redactor.redact_text(input_path, output_path)

    # Save mapping
    map_dir = Path.home() / "Library/CloudStorage/Dropbox/MCP Analysis/.sanitization_maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    uuid = save_sanitization_map(input_path, mapping, map_dir)

    print(f"✓ Redacted text saved: {output_path.name}")
    print(f"✓ Mapping saved: {uuid}.json")
    print(f"\nName mappings ({len(mapping)}):")
    for initials, name in sorted(mapping.items()):
        print(f"  {initials} ← {name}")


if __name__ == "__main__":
    main()
