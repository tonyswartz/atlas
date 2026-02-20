#!/usr/bin/env python3
"""
PDF Redaction Tool v3 - Direct search approach

Instead of regex on extracted text, directly search for PII terms on each page.
This preserves PDF formatting and ensures accurate redaction.
"""

import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List

try:
    import fitz  # pymupdf
except ImportError:
    print("ERROR: pymupdf not installed. Run: pip install pymupdf")
    exit(1)


class PDFRedactor:
    """Redacts PII from legal PDFs using direct page search."""

    def __init__(self):
        self.entity_map = {}
        self.redaction_count = 0
        self.names_registry = set()

    def redact_pdf(self, input_path: Path, output_path: Path) -> Dict[str, str]:
        """Redact PII from PDF."""
        doc = fitz.open(input_path)
        self.entity_map = {}
        self.redaction_count = 0

        # First pass: extract all text to find names
        print("  Pass 1: Extracting names from document...")
        full_text = ""
        for page in doc:
            full_text += page.get_text()

        self._extract_names(full_text)
        print(f"  Found {len(self.names_registry)} unique names to redact")

        # Second pass: Redact all PII on each page
        print("  Pass 2: Redacting PII...")
        for page_num, page in enumerate(doc):
            page_redactions = 0

            # Redact all names found in first pass
            for name in sorted(self.names_registry, key=len, reverse=True):
                instances = page.search_for(name)
                for rect in instances:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    page_redactions += 1
                    self.redaction_count += 1

                # Also search for last name only
                parts = name.split()
                if len(parts) >= 2:
                    last_name = parts[-1].strip('.,')
                    if len(last_name) > 3:
                        instances = page.search_for(last_name)
                        for rect in instances:
                            page.add_redact_annot(rect, fill=(0, 0, 0))
                            page_redactions += 1
                            self.redaction_count += 1

            # Redact fixed patterns (case numbers, SSN, etc.)
            page_redactions += self._redact_fixed_patterns(page)

            # Apply all redactions on this page
            if page_redactions > 0:
                result = page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_REMOVE,
                    text=fitz.PDF_REDACT_TEXT_REMOVE
                )
                print(f"    Page {page_num + 1}: {page_redactions} redactions")

        # Save
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()

        return self.entity_map

    def _extract_names(self, text: str) -> None:
        """Extract names from structured document fields."""

        # Defendant/Attorney/Officer fields - match multi-word names (2-4 words)
        # Captures: "John Smith", "John A. Smith", "Alexander Field Fredrickson"
        # Stop at newline, Birth Date, DOB, SSN, or other field markers
        name_field_pattern = r'(Defendant|Attorney|Prosecutor|Officer|Deputy|Trooper):\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})(?=\s*(?:\n|Birth|DOB|SSN|IR|$))'
        for match in re.finditer(name_field_pattern, text):
            name = match.group(2).strip()
            # Clean up any trailing punctuation from the name
            name = re.sub(r'[,.]$', '', name)
            # Skip form field labels that aren't names
            if 'Signature' in name or 'Printed' in name or 'Attorney' in name:
                continue
            if name and len(name.split()) >= 2:  # Must be at least 2 words
                self.names_registry.add(name)
                self._add_to_map(name)

        # State v. [Name] captions
        for match in re.finditer(r'State v\.?\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})', text):
            name = match.group(1).strip()
            name = re.sub(r'[,.]$', '', name)
            if name and len(name.split()) >= 2:
                self.names_registry.add(name)
                self._add_to_map(name)

        # Names with titles (Deputy Smith, Officer Jones)
        title_pattern = r'(Deputy|Officer|Trooper|Sgt\.) ([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})'
        for match in re.finditer(title_pattern, text):
            name = match.group(2).strip()
            name = re.sub(r'[,.]$', '', name)
            if name and len(name.split()) >= 2:
                self.names_registry.add(name)
                self._add_to_map(name)

        # Names in letterheads (common at top of first page)
        # Look for full names on their own lines in first 2000 chars
        header = text[:2000]
        letterhead_pattern = r'^([A-Z][a-z]{2,}) ([A-Z]\. )?([A-Z][a-z]{2,})$'
        for match in re.finditer(letterhead_pattern, header, re.MULTILINE):
            parts = [match.group(1)]
            if match.group(2):
                parts.append(match.group(2).strip())
            parts.append(match.group(3))
            name = ' '.join(parts)
            # Skip legal terms, form field labels, common non-names
            excluded_terms = [
                'Superior Court', 'District Court', 'County Attorney', 'Prosecuting Attorney',
                'Signature Printed', 'Printed Name', 'Birth Date', 'Date Time'
            ]
            if name not in excluded_terms and not any(term in name for term in ['Signature', 'Printed']):
                self.names_registry.add(name)
                self._add_to_map(name)

    def _redact_fixed_patterns(self, page: fitz.Page) -> int:
        """Redact fixed PII patterns (SSN, DOB, case numbers, etc.)."""
        count = 0
        page_text = page.get_text()

        patterns = {
            # SSN: 123-45-6789
            r'\b\d{3}-\d{2}-\d{4}\b': '[SSN]',

            # Case/IR numbers
            r'\b(?:Case|Cause|IR) #?:?\s*[A-Z]?\d{2,}-?\d{3,}\b': '[CASE]',
            r'\bS\d{2}-\d{5}\b': '[CASE]',  # S26-02014 format

            # Phone numbers
            r'\(\d{3}\) \d{3}-\d{4}': '[PHONE]',
            r'\d{3}-\d{3}-\d{4}': '[PHONE]',

            # License plates (2-3 letters + 3-4 digits)
            r'\b[A-Z]{2,3}\d{3,4}\b': '[PLATE]',

            # Driver's license (Washington format: 12 chars alphanumeric)
            r'\b[A-Z]{1,}[0-9]{3,}[A-Z0-9]{3,}\b': '[LICENSE]',

            # Badge numbers
            r'Badge #?\s*\d{3,6}': '[BADGE]',

            # Addresses (simple pattern)
            r'\b\d+ [A-Z][a-z]+ (?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln)\b': '[ADDRESS]',
        }

        for pattern, replacement in patterns.items():
            for match in re.finditer(pattern, page_text):
                match_text = match.group(0)
                instances = page.search_for(match_text)
                for rect in instances:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    count += 1

        return count

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


def save_sanitization_map(pdf_path: Path, mapping: Dict[str, str], output_dir: Path) -> str:
    """Save PII mapping to JSON."""
    unique_str = f"{pdf_path.name}_{datetime.now().isoformat()}"
    uuid = hashlib.md5(unique_str.encode()).hexdigest()[:16]

    map_data = {
        "uuid": uuid,
        "original_file": str(pdf_path),
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
        print("Usage: python redact_pdf_v3.py <input.pdf> <output.pdf>")
        sys.exit(1)

    input_path = Path(sys.argv[1]).expanduser()
    output_path = Path(sys.argv[2]).expanduser()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    print(f"Redacting: {input_path.name}")

    redactor = PDFRedactor()
    mapping = redactor.redact_pdf(input_path, output_path)

    # Save mapping
    map_dir = Path.home() / "Library/CloudStorage/Dropbox/MCP Analysis/.sanitization_maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    uuid = save_sanitization_map(input_path, mapping, map_dir)

    print(f"\n✓ Redacted PDF saved: {output_path.name}")
    print(f"✓ Mapping saved: {uuid}.json")
    print(f"✓ Total redactions: {redactor.redaction_count}")
    print(f"\nName mappings ({len(mapping)}):")
    for initials, name in sorted(mapping.items()):
        print(f"  {initials} ← {name}")


if __name__ == "__main__":
    main()
