#!/usr/bin/env python3
"""
PDF to Sanitized Text Converter

Extracts text from PDFs and sanitizes PII.
Outputs clean .txt files that MCP server can safely read.
"""

import re
import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Set

try:
    import fitz  # pymupdf for text extraction
except ImportError:
    print("ERROR: pymupdf not installed. Run: pip install pymupdf")
    exit(1)

# OCR support
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class TextSanitizer:
    """Sanitizes legal document text."""

    def __init__(self):
        self.entity_map = {}
        self.names_registry: Set[str] = set()

    def sanitize_pdf_to_text(self, pdf_path: Path) -> tuple[str, Dict[str, str]]:
        """Extract text from PDF and sanitize it."""

        # Extract text
        text = self._extract_text(pdf_path)

        # Sanitize
        sanitized = self._sanitize_text(text)

        return sanitized, self.entity_map

    def _extract_text(self, pdf_path: Path) -> str:
        """Extract text from PDF."""
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            # If no text and OCR available, try OCR
            if len(text.strip()) < 100 and OCR_AVAILABLE:
                print("  Low text content, attempting OCR...")
                images = convert_from_path(pdf_path)
                for image in images:
                    text += pytesseract.image_to_string(image)

            return text
        except Exception as e:
            raise Exception(f"Failed to extract text: {e}")

    def _sanitize_text(self, text: str) -> str:
        """Sanitize PII from text."""

        # Extract names first
        self._extract_names(text)

        sanitized = text

        # Replace all found names with initials
        for name in sorted(self.names_registry, key=len, reverse=True):
            initials = self._get_initials(name)
            # Replace full name
            sanitized = re.sub(rf'\b{re.escape(name)}\b', initials, sanitized, flags=re.IGNORECASE)

            # Replace last name alone
            parts = name.split()
            if len(parts) >= 2:
                last_name = parts[-1].strip('.,')
                if len(last_name) > 3:
                    sanitized = re.sub(rf'\b{re.escape(last_name)}\b', initials, sanitized, flags=re.IGNORECASE)

        # Redact fixed patterns
        sanitized = self._redact_fixed_patterns(sanitized)

        return sanitized

    def _extract_names(self, text: str) -> None:
        """Extract names from structured fields."""

        # Defendant/Attorney/Officer fields
        name_field_pattern = r'(Defendant|Attorney|Prosecutor|Officer|Deputy|Trooper):\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})(?=\s*(?:\n|Birth|DOB|SSN|IR|$))'
        for match in re.finditer(name_field_pattern, text):
            name = match.group(2).strip()
            name = re.sub(r'[,.]$', '', name)
            if 'Signature' in name or 'Printed' in name or 'Attorney' in name:
                continue
            if len(name.split()) >= 2:
                self.names_registry.add(name)

        # State v. [Name] captions
        for match in re.finditer(r'State v\.?\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})', text):
            name = match.group(1).strip()
            name = re.sub(r'[,.]$', '', name)
            if len(name.split()) >= 2:
                self.names_registry.add(name)

        # Names with titles
        title_pattern = r'(Deputy|Officer|Trooper|Sgt\.) ([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,3})'
        for match in re.finditer(title_pattern, text):
            name = match.group(2).strip()
            name = re.sub(r'[,.]$', '', name)
            if len(name.split()) >= 2:
                self.names_registry.add(name)

    def _redact_fixed_patterns(self, text: str) -> str:
        """Redact SSN, DOB, case numbers, etc."""

        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)
        text = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', text)
        text = re.sub(r'(?:DOB|Birth\s+Date|Date\s+of\s+Birth):?\s*\d{1,2}/\d{1,2}/\d{4}', lambda m: m.group(0).split(':')[0] + ': [REDACTED]' if ':' in m.group(0) else '[REDACTED]', text, flags=re.IGNORECASE)
        text = re.sub(r'\b[A-Z]{2,3}[-\s]?\d{3,4}\b', '[PLATE]', text)
        text = re.sub(r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b', '[ADDRESS]', text)
        text = re.sub(r'\b(?:Case|Cause|IR)\s*#?:?\s*[A-Z]?\d{2,}-?\d{3,}\b', '[CASE]', text, flags=re.IGNORECASE)
        text = re.sub(r'\bS\d{2}-\d{5}\b', '[CASE]', text)
        text = re.sub(r'(?:Badge|ID)\s*#?:?\s*\d{3,6}', '[BADGE]', text, flags=re.IGNORECASE)
        text = re.sub(r'\b[A-Z]{1,}[0-9]{3,}[A-Z0-9]{3,}\b', '[LICENSE]', text)

        return text

    def _get_initials(self, name: str) -> str:
        """Generate initials from name."""
        if name in [v for v in self.entity_map.values()]:
            return [k for k, v in self.entity_map.items() if v == name][0]

        parts = name.split()
        initials = ''.join([p[0].upper() for p in parts if p and p[0].isupper()])

        base = initials
        counter = 1
        while initials in self.entity_map:
            initials = f"{base}{counter}"
            counter += 1

        self.entity_map[initials] = name
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
    if len(sys.argv) < 3:
        print("Usage: python sanitize_to_text.py <input.pdf> <output.txt>")
        sys.exit(1)

    input_path = Path(sys.argv[1]).expanduser()
    output_path = Path(sys.argv[2]).expanduser()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    print(f"Sanitizing: {input_path.name}")

    sanitizer = TextSanitizer()
    sanitized_text, mapping = sanitizer.sanitize_pdf_to_text(input_path)

    # Save sanitized text
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(sanitized_text)

    # Save mapping
    map_dir = Path.home() / "Library/CloudStorage/Dropbox/MCP Analysis/.sanitization_maps"
    map_dir.mkdir(parents=True, exist_ok=True)
    uuid = save_sanitization_map(input_path, mapping, map_dir)

    print(f"✓ Sanitized text saved: {output_path.name}")
    print(f"✓ Mapping saved: {uuid}.json")
    print(f"✓ Redacted {len(mapping)} names")
    for initials, name in sorted(mapping.items()):
        print(f"  {initials} ← {name}")


if __name__ == "__main__":
    main()
