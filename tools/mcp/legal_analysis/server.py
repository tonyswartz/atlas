#!/usr/bin/env python3
"""
MCP Server for Legal Case Analysis

Provides tools for ChatGPT to analyze legal case files with client data sanitization.
All sensitive data processing happens locally - only sanitized text is passed to ChatGPT.

Tools:
- list_case_files: List available case files in monitored directory
- read_case_sanitized: Read and sanitize a case file
- analyze_suppression_issues: Read, sanitize, and format for 4th Amendment analysis
- analyze_breath_test: Read, sanitize, and format for breath/blood test analysis
- analyze_probable_cause: Read, sanitize, and format for probable cause analysis
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import hashlib

# MCP SDK
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# PDF processing
try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)

# OCR for scanned PDFs
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    OCR_AVAILABLE = True
    print("INFO: OCR support enabled (handles scanned PDFs)", file=sys.stderr)
except ImportError as e:
    OCR_AVAILABLE = False
    print("WARNING: OCR not available - scanned PDFs won't be readable", file=sys.stderr)
    print(f"         Install with: brew install tesseract && pip3 install pytesseract pdf2image", file=sys.stderr)

# NLP for entity recognition - disabled on Python 3.14+
# spaCy has compatibility issues with Python 3.14 (Pydantic v1 incompatibility)
# Regex-based sanitization is robust and sufficient for legal documents
nlp = None
print("INFO: Using regex-based sanitization (Python 3.14+ compatible)", file=sys.stderr)
print("      This catches: names in captions, case numbers, SSN, DOB, phones, addresses, plates", file=sys.stderr)

# Configuration
# SECURITY: MCP server ONLY has access to sanitized/ folder
# Original PDFs live in originals/ folder which MCP cannot access
# Watcher service processes originals → sanitized .txt files
CASE_FILES_DIR = Path.home() / "Library/CloudStorage/Dropbox/MCP Analysis/sanitized"
SANITIZATION_MAPS_DIR = Path.home() / "atlas/data/legal_sanitization_maps"

# Create directories if they don't exist
CASE_FILES_DIR.mkdir(parents=True, exist_ok=True)
SANITIZATION_MAPS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize MCP server
app = Server("legal-analysis")


class CaseSanitizer:
    """Sanitizes legal case files by removing PII and client information."""

    def __init__(self):
        self.entity_map = {}
        self.person_counter = 0
        self.location_counter = 0
        self.org_counter = 0

    def sanitize_text(self, text: str) -> tuple[str, dict]:
        """
        Sanitize text by replacing PII with placeholders.

        Two-pass approach:
        1. Extract names from structured fields (Defendant:, Officer:, etc.)
        2. Replace ALL occurrences of those names throughout document

        Returns (sanitized_text, mapping_dict)
        """
        sanitized = text
        self.entity_map = {}
        names_registry = set()  # Track all names to replace globally

        # Pass 1: Named Entity Recognition with spaCy
        if nlp:
            doc = nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    placeholder = self._get_person_placeholder(ent.text)
                    sanitized = sanitized.replace(ent.text, placeholder)
                elif ent.label_ == "GPE":  # Geo-political entity
                    placeholder = self._get_location_placeholder(ent.text)
                    sanitized = sanitized.replace(ent.text, placeholder)
                elif ent.label_ == "ORG":
                    placeholder = self._get_org_placeholder(ent.text)
                    sanitized = sanitized.replace(ent.text, placeholder)

        # Pass 2: Regex patterns for legal-specific entities

        # Names in legal document fields - stop at field terminators
        # Defendant: Name (stops at Birth Date, DOB, SSN, etc.)
        # Captures 2-4 word names (First Middle? Last)
        name_field_pattern = r'(Defendant|Attorney|Prosecutor|Plaintiff|Respondent|Petitioner|Counsel for|Client(?:\s+Name)?|Subject(?:\s+Name)?|Officer(?:\s+Name)?|Deputy(?:\s+Name)?|Arresting Officer):\s+([A-Z][a-z]+(?:\s+[A-Z][a-z.]+){1,3})(?=\s+(?:Birth Date|DOB|SSN|IR #|\n|\t|$))'
        for match in re.finditer(name_field_pattern, text):
            name = match.group(2).strip()
            names_registry.add(name)  # Add to global registry
            placeholder = self._get_person_placeholder(name)
            # Replace the whole match including the field label
            full_match = match.group(0)
            sanitized = sanitized.replace(full_match, f"{match.group(1)}: {placeholder}")

        # Case captions: "State v. Smith" -> "State v. [PERSON_1]"
        for match in re.finditer(r'(State|People|Commonwealth)\s+v\.?\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+)', text):
            name = match.group(2).strip()
            names_registry.add(name)  # Add to global registry
            placeholder = self._get_person_placeholder(name)
            sanitized = sanitized.replace(match.group(0), f"{match.group(1)} v. {placeholder}")

        # Names with titles: Deputy Smith, Officer Jones, Trooper Brown, Sgt. Adams
        title_name_pattern = r'\b(Deputy|Officer|Trooper|Sgt\.?|Sergeant|Detective|Det\.?|Agent|Dr\.?|Mr\.?|Ms\.?|Mrs\.?)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)?)'
        for match in re.finditer(title_name_pattern, text):
            name = match.group(2).strip()
            if len(name.split()) >= 2 or len(name) > 4:  # Must be full name or longer single name
                names_registry.add(name)  # Add to global registry
                placeholder = self._get_person_placeholder(name)
                sanitized = sanitized.replace(match.group(0), f"{match.group(1)} {placeholder}")

        # Full names in filename contexts (common in legal documents)
        # e.g., "Alexander Fredrickson - Discovery.pdf" pattern in headers/footers
        filename_name_pattern = r'\b([A-Z][a-z]{3,})\s+([A-Z]\.?\s+)?([A-Z][a-z]{3,})\s*-\s*(Discovery|Report|File|Document|Case)'
        for match in re.finditer(filename_name_pattern, text):
            # Construct full name (first + optional middle initial + last)
            parts = [match.group(1)]
            if match.group(2):
                parts.append(match.group(2).strip())
            parts.append(match.group(3))
            full_name = ' '.join(parts)
            names_registry.add(full_name)  # Add to global registry
            placeholder = self._get_person_placeholder(full_name)
            sanitized = sanitized.replace(full_name, placeholder)

        # Names on their own line (common in letterheads)
        # Match: FirstName Middle.Initial LastName on its own line at start of document
        # Only in first 1000 chars to avoid false positives in body text
        if len(text) > 100:
            header = text[:1000]
            letterhead_pattern = r'^\s*([A-Z][a-z]{2,})\s+([A-Z]\.?\s+)?([A-Z][a-z]{2,})\s*$'
            for match in re.finditer(letterhead_pattern, header, re.MULTILINE):
                parts = [match.group(1)]
                if match.group(2):
                    parts.append(match.group(2).strip())
                parts.append(match.group(3))
                full_name = ' '.join(parts)
                # Only if it looks like a real name (not legal terms)
                if full_name not in ['United States', 'Superior Court', 'District Court', 'County Attorney',
                                     'Prosecuting Attorney', 'Public Defender', 'Law Enforcement']:
                    names_registry.add(full_name)  # Add to global registry
                    placeholder = self._get_person_placeholder(full_name)
                    sanitized = sanitized.replace(full_name, placeholder)

        # Case numbers - multiple formats
        # Format 1: CR-2024-12345, CV-2024-123, No. 12345
        case_num_pattern = r'\b(?:CR|CV|No\.?|Case|Cause)\s*[#:]?\s*[-:]?\s*\d{4}[-:]?\d+\b'
        for match in re.finditer(case_num_pattern, text, re.IGNORECASE):
            placeholder = f"[CASE_NUM_{len([k for k in self.entity_map.keys() if k.startswith('[CASE_NUM')])+1:03d}]"
            self.entity_map[placeholder] = match.group(0)
            sanitized = sanitized.replace(match.group(0), placeholder)

        # Format 2: Simple 4-6 digit case numbers after "Cause #:" or "Case #:"
        simple_case_pattern = r'(Cause|Case)\s*#:\s*(\d{4,6})'
        for match in re.finditer(simple_case_pattern, text, re.IGNORECASE):
            case_num = match.group(2)
            placeholder = f"[CASE_NUM_{len([k for k in self.entity_map.keys() if k.startswith('[CASE_NUM')])+1:03d}]"
            self.entity_map[placeholder] = match.group(0)  # Store full match
            sanitized = sanitized.replace(match.group(0), f"{match.group(1)} #: {placeholder}")

        # IR numbers, incident report numbers
        ir_pattern = r'\b(?:IR|Incident|Report)\s*[#:]?\s*[A-Z]?\d{2,}-?\d{4,}\b'
        for match in re.finditer(ir_pattern, text, re.IGNORECASE):
            placeholder = f"[CASE_NUM_{len([k for k in self.entity_map.keys() if k.startswith('[CASE_NUM')])+1:03d}]"
            self.entity_map[placeholder] = match.group(0)
            sanitized = sanitized.replace(match.group(0), placeholder)

        # SSN: 123-45-6789 -> [SSN_REDACTED]
        sanitized = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]', sanitized)

        # Phone numbers: (555) 123-4567 -> [PHONE_REDACTED]
        sanitized = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE_REDACTED]', sanitized)

        # Dates of birth (but keep arrest dates, test dates)
        # Match DOB with or without label
        sanitized = re.sub(r'(?:DOB|Birth\s+Date|Date\s+of\s+Birth):?\s*\d{1,2}/\d{1,2}/\d{4}',
                          lambda m: m.group(0).split(':')[0] + ': [REDACTED]' if ':' in m.group(0) else '[REDACTED]',
                          sanitized, flags=re.IGNORECASE)
        # Also catch standalone DOB dates right after defendant name
        sanitized = re.sub(r'(\[PERSON_\d+\])\s+(\d{1,2}/\d{1,2}/\d{4})',
                          r'\1 [REDACTED]',
                          sanitized)
        sanitized = re.sub(r'born\s+(?:on\s+)?\d{1,2}/\d{1,2}/\d{4}', 'born [REDACTED]', sanitized, flags=re.IGNORECASE)

        # License plates: ABC1234 -> [PLATE_###]
        plate_pattern = r'\b[A-Z]{2,3}[-\s]?\d{3,4}\b'
        for match in re.finditer(plate_pattern, text):
            if not self._is_legal_citation(match.group(0)):  # Don't redact citations
                placeholder = f"[PLATE_{len([k for k in self.entity_map.keys() if k.startswith('[PLATE')])+1:03d}]"
                self.entity_map[placeholder] = match.group(0)
                sanitized = sanitized.replace(match.group(0), placeholder)

        # Addresses (but preserve general locations needed for context)
        # Street addresses: 123 Main Street -> [ADDRESS_###]
        address_pattern = r'\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b'
        for match in re.finditer(address_pattern, text):
            placeholder = f"[ADDRESS_{len([k for k in self.entity_map.keys() if k.startswith('[ADDRESS')])+1:03d}]"
            self.entity_map[placeholder] = match.group(0)
            sanitized = sanitized.replace(match.group(0), placeholder)

        # Serial numbers (firearms, equipment, etc.)
        # Match patterns like: ABC123456, 12-345678, SN: 123456
        serial_pattern = r'\b(?:Serial\s+(?:Number|#)?:?\s*)?([A-Z]{2,}\d{5,}|\d{2,}-\d{5,})\b'
        for match in re.finditer(serial_pattern, text, re.IGNORECASE):
            placeholder = f"[SERIAL_{len([k for k in self.entity_map.keys() if k.startswith('[SERIAL')])+1:03d}]"
            self.entity_map[placeholder] = match.group(0)
            sanitized = sanitized.replace(match.group(0), placeholder)

        # Badge numbers
        badge_pattern = r'(?:Badge|ID)\s*#?:?\s*(\d{3,6})\b'
        for match in re.finditer(badge_pattern, text, re.IGNORECASE):
            placeholder = f"[BADGE_{len([k for k in self.entity_map.keys() if k.startswith('[BADGE')])+1:03d}]"
            self.entity_map[placeholder] = match.group(0)
            sanitized = sanitized.replace(match.group(0), placeholder)

        # FINAL PASS: Replace ALL occurrences of names in registry throughout document
        # This catches names in narrative text ("approached Fredrickson", "Alexander said", etc.)
        for full_name in sorted(names_registry, key=len, reverse=True):  # Longest first to avoid partial matches
            if full_name in self.entity_map.values():
                # Find the placeholder for this name
                placeholder = [k for k, v in self.entity_map.items() if v == full_name][0]
            else:
                # Create new placeholder
                placeholder = self._get_person_placeholder(full_name)

            # Replace full name with word boundaries
            sanitized = re.sub(rf'\b{re.escape(full_name)}\b', placeholder, sanitized)

            # Also replace individual name parts (first/last name used alone)
            # But only if they're substantial (>3 chars) to avoid false positives
            parts = full_name.split()
            for part in parts:
                part_clean = part.rstrip('.,')  # Remove trailing punctuation
                if len(part_clean) > 3 and part_clean not in ['Field', 'Birth', 'Date']:  # Skip common words
                    # Replace with word boundaries to avoid partial matches
                    sanitized = re.sub(rf'\b{re.escape(part_clean)}\b', placeholder, sanitized)
                    # Also catch form field concatenations like "LASTFredrickson", "FIRSTAlexander"
                    sanitized = re.sub(rf'(LAST|FIRST|NAME:?){re.escape(part_clean)}\b',
                                     rf'\1{placeholder}', sanitized, flags=re.IGNORECASE)

        # Final cleanup: catch any remaining bare case numbers (single letter + 4-6 digits)
        sanitized = re.sub(r'\b([A-Z])\s+(\d{4,6})\b', r'\1 [CASE_NUM_XXX]', sanitized)

        return sanitized, self.entity_map

    def _get_person_placeholder(self, name: str) -> str:
        """Get or create placeholder for a person's name using initials."""
        # Check if we already have a placeholder for this name
        for placeholder, original in self.entity_map.items():
            if original == name and not placeholder.startswith('['):
                return placeholder

        # Create initials-based placeholder
        # "Alexander Field Fredrickson" -> "AFF"
        # "Gregory L. Zempel" -> "GLZ"
        # "John Smith" -> "JS"
        parts = name.split()
        initials = ''.join([p[0].upper() for p in parts if p and len(p) > 0 and p[0].isupper() and p not in ['.', ',']])

        # If we already have this initials, add number
        base_initials = initials
        counter = 1
        while initials in self.entity_map.values():
            initials = f"{base_initials}{counter}"
            counter += 1

        self.entity_map[initials] = name
        return initials

    def _get_location_placeholder(self, location: str) -> str:
        """Get or create placeholder for a location."""
        for placeholder, original in self.entity_map.items():
            if original == location and placeholder.startswith('[LOCATION_'):
                return placeholder

        self.location_counter += 1
        placeholder = f"[LOCATION_{self.location_counter}]"
        self.entity_map[placeholder] = location
        return placeholder

    def _get_org_placeholder(self, org: str) -> str:
        """Get or create placeholder for an organization."""
        for placeholder, original in self.entity_map.items():
            if original == org and placeholder.startswith('[ORG_'):
                return placeholder

        self.org_counter += 1
        placeholder = f"[ORG_{self.org_counter}]"
        self.entity_map[placeholder] = org
        return placeholder

    @staticmethod
    def _is_legal_citation(text: str) -> bool:
        """Check if text looks like a legal citation (don't redact these)."""
        # Pattern for citations like "123 Wash. 2d 456"
        return bool(re.match(r'\d+\s+[A-Z][a-z]+\.?\s*\d*d?\s*\d+', text))


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF file. Automatically uses OCR for scanned documents."""

    # Try pdfplumber first (fast, works for text-layer PDFs)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"

            # Check if we got meaningful text (at least 100 chars)
            if len(text.strip()) > 100:
                print(f"INFO: Extracted {len(text)} chars using text layer (fast)", file=sys.stderr)
                return text

            # If very little text, this is likely a scanned PDF
            print(f"WARNING: Only {len(text.strip())} chars extracted - appears to be scanned PDF", file=sys.stderr)

    except Exception as e:
        print(f"WARNING: pdfplumber extraction failed: {e}", file=sys.stderr)

    # Fall back to OCR for scanned documents
    if OCR_AVAILABLE:
        print("INFO: Running OCR (this may take 10-30 seconds)...", file=sys.stderr)
        try:
            # Convert PDF pages to images
            images = convert_from_path(pdf_path, dpi=300)

            text = ""
            for i, image in enumerate(images):
                print(f"      OCR page {i+1}/{len(images)}...", file=sys.stderr)
                # Run Tesseract OCR on each page
                page_text = pytesseract.image_to_string(image, lang='eng')
                text += page_text + "\n\n"

            print(f"INFO: OCR complete - extracted {len(text)} chars", file=sys.stderr)
            return text

        except Exception as e:
            raise ValueError(f"OCR failed: {e}")
    else:
        raise ValueError(
            "This appears to be a scanned PDF but OCR is not available. "
            "Install Tesseract with: brew install tesseract && "
            "pip3 install pytesseract pdf2image"
        )


def save_sanitization_map(file_path: Path, mapping: dict) -> str:
    """Save sanitization mapping to local file. Returns UUID for reference."""
    # Generate UUID from file path and timestamp
    file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    uuid = f"{file_hash}_{timestamp}"

    map_file = SANITIZATION_MAPS_DIR / f"{uuid}.json"
    with open(map_file, 'w') as f:
        json.dump({
            'uuid': uuid,
            'original_file': str(file_path),
            'timestamp': timestamp,
            'mapping': mapping
        }, f, indent=2)

    return uuid


def save_analysis_to_obsidian(analysis_text: str, sanitized_text: str, mapping: dict) -> Path:
    """
    Save sanitized analysis to Obsidian vault.

    Filename format: YYYY-MM-DD [ClientInitials].md
    Example: 2026-01-28 AFF.md

    Returns path to saved file.
    """
    obsidian_dir = Path.home() / 'Library/CloudStorage/Dropbox/Obsidian/Tony\'s Vault/MCP Legal'
    obsidian_dir.mkdir(parents=True, exist_ok=True)

    # Extract client initials (first person in mapping)
    client_initials = None
    for placeholder, original in mapping.items():
        if not placeholder.startswith('['):  # It's initials, not [PERSON_1] format
            client_initials = placeholder
            break

    if not client_initials:
        client_initials = "UNK"  # Unknown

    # Extract violation/stop date from sanitized text
    # Look for "Vio. Date:", "Violation Date:", or dates in first 500 chars
    date_match = re.search(r'(?:Vio\.?|Violation)\s+Date:?\s*(\d{1,2}/\d{1,2}/\d{2,4})', sanitized_text[:500])
    if date_match:
        date_str = date_match.group(1)
        # Parse and reformat to YYYY-MM-DD
        try:
            from datetime import datetime as dt
            parsed = dt.strptime(date_str, "%m/%d/%Y" if len(date_str) > 8 else "%m/%d/%y")
            file_date = parsed.strftime("%Y-%m-%d")
        except:
            file_date = datetime.now().strftime("%Y-%m-%d")
    else:
        # Use today's date
        file_date = datetime.now().strftime("%Y-%m-%d")

    # Create filename
    filename = f"{file_date} {client_initials}.md"
    file_path = obsidian_dir / filename

    # Write analysis (no coversheet - straight to content)
    with open(file_path, 'w') as f:
        f.write(analysis_text)

    return file_path


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="list_case_files",
            description="List available case files in the monitored directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern to filter files (e.g., '*DUI*', '*.pdf')"
                    }
                }
            }
        ),
        Tool(
            name="read_case_sanitized",
            description="Read a case file and return sanitized text (all PII removed)",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the file to read (relative to case files directory)"
                    }
                },
                "required": ["filename"]
            }
        ),
        Tool(
            name="detect_case_type",
            description="Auto-detect case type by reading the document and identifying DUI indicators (breath/blood test, BAC, field sobriety, implied consent) vs. general criminal. Returns detected type with evidence for user confirmation before analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the case file to detect (optional - if not provided, detects ALL files in folder)",
                    }
                }
            }
        ),
        Tool(
            name="analyze_dui_criminal",
            description="Comprehensive DUI criminal defense analysis under Washington law - checks reasonable suspicion, probable cause, 4th/5th Amendment issues, breath/blood test compliance, warrant issues, and suppression opportunities",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the case file to analyze (optional - if not provided, analyzes ALL files in folder)",
                    }
                }
            }
        ),
        Tool(
            name="analyze_dui_dol_hearing",
            description="DUI DOL implied consent hearing analysis - focuses on license suspension issues, DOL hearing defenses, implied consent warnings, refusal consequences, and administrative hearing strategy under Washington law",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the case file to analyze (optional - if not provided, analyzes ALL files in folder)",
                    }
                }
            }
        ),
        Tool(
            name="analyze_criminal_case",
            description="General criminal defense analysis for non-DUI cases - examines reasonable suspicion, probable cause, search & seizure, Miranda, charging issues, and defense opportunities under Washington law",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Name of the case file to analyze (optional - if not provided, analyzes ALL files in folder)",
                    }
                }
            }
        ),
        Tool(
            name="save_analysis",
            description="Save a completed legal analysis to Obsidian vault. Use this AFTER generating an analysis. Filename format: YYYY-MM-DD [ClientInitials].md",
            inputSchema={
                "type": "object",
                "properties": {
                    "analysis_content": {
                        "type": "string",
                        "description": "The full analysis text to save (must use initials like AFF, not full names)"
                    },
                    "client_initials": {
                        "type": "string",
                        "description": "Client initials (e.g., 'AFF', 'JS')"
                    },
                    "case_date": {
                        "type": "string",
                        "description": "Case/violation date in YYYY-MM-DD format (optional - uses today if not provided)"
                    }
                },
                "required": ["analysis_content", "client_initials"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    if name == "list_case_files":
        pattern = arguments.get("pattern")

        if pattern:
            files = sorted(CASE_FILES_DIR.glob(pattern))
        else:
            # Only list .txt files (all originals are pre-sanitized to .txt by watcher)
            files = sorted(CASE_FILES_DIR.glob("*.txt"), key=lambda f: f.name)

        if not files:
            search_desc = f"matching '{pattern}'" if pattern else "(*.txt)"
            return [TextContent(
                type="text",
                text=f"No sanitized files found {search_desc} in {CASE_FILES_DIR.name}/\n\n"
                     f"Drop PDF or transcript files in originals/ folder.\n"
                     f"Watcher service will auto-sanitize them to .txt files here."
            )]

        file_list = []
        for f in files:
            file_list.append(f"- {f.name} ({f.stat().st_size // 1024} KB)")

        return [TextContent(
            type="text",
            text=f"Found {len(files)} sanitized case files:\n\n" + "\n".join(file_list) +
                 f"\n\n**Security:** These are pre-sanitized .txt files. Original PDFs are not accessible to this server."
        )]

    elif name == "read_case_sanitized":
        filename = arguments["filename"]

        # Ensure it's a .txt file
        if not filename.endswith(".txt"):
            return [TextContent(
                type="text",
                text=f"ERROR: Only .txt files are accessible. "
                     f"Original PDFs must be placed in originals/ folder for auto-sanitization."
            )]

        file_path = CASE_FILES_DIR / filename

        if not file_path.exists():
            return [TextContent(
                type="text",
                text=f"ERROR: File not found: {filename}\n\n"
                     f"Available files: Use list_case_files to see sanitized .txt files."
            )]

        # Read pre-sanitized text file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"ERROR: Failed to read text file: {e}"
            )]

        # Second pass sanitization for safety (defense in depth)
        sanitizer = CaseSanitizer()
        sanitized_text, mapping = sanitizer.sanitize_text(text)

        # Save mapping locally if any additional redactions were made
        if mapping:
            uuid = save_sanitization_map(file_path, mapping)
            redaction_note = f"(Server made {len(mapping)} additional redactions - UUID: {uuid})"
        else:
            redaction_note = "(Pre-sanitized by watcher service - no additional redactions needed)"

        # Return sanitized text
        return [TextContent(
            type="text",
            text=f"**SANITIZED CASE FILE: {filename}**\n"
                 f"{redaction_note}\n\n"
                 f"{sanitized_text}\n\n"
                 f"---\n"
                 f"**Security:** This file was pre-sanitized to .txt by watcher service. "
                 f"Original PDF is not accessible to this server. "
                 f"All client names, case numbers, and PII have been redacted. "
                 f"Analysis should reference initials (e.g., AFF, JS)."
        )]

    elif name == "detect_case_type":
        filename = arguments.get("filename")

        # Read and sanitize file(s)
        if filename:
            file_path = CASE_FILES_DIR / filename
            if not file_path.exists():
                return [TextContent(type="text", text=f"ERROR: File not found: {filename}")]

            try:
                text = extract_pdf_text(file_path)
                sanitizer = CaseSanitizer()
                sanitized_text, mapping = sanitizer.sanitize_text(text)
                files_analyzed = [filename]
            except Exception as e:
                return [TextContent(type="text", text=f"ERROR: Failed to read PDF: {e}")]
        else:
            # Batch mode - analyze all files
            files = sorted(CASE_FILES_DIR.glob("*.pdf"))
            if not files:
                return [TextContent(type="text", text="No PDF files found in drop folder")]

            sanitized_text = ""
            files_analyzed = []
            for file_path in files:
                try:
                    text = extract_pdf_text(file_path)
                    sanitizer = CaseSanitizer()
                    s_text, mapping = sanitizer.sanitize_text(text)
                    sanitized_text += f"\n{s_text}\n"
                    files_analyzed.append(file_path.name)
                except Exception as e:
                    sanitized_text += f"\nERROR reading {file_path.name}: {e}\n"

        # Auto-detect case type based on content
        text_lower = sanitized_text.lower()

        # DUI indicators
        dui_indicators = {
            "breath_test": any(phrase in text_lower for phrase in ["breath test", "datamaster", "bac", "breath sample", "alco-sensor"]),
            "blood_test": any(phrase in text_lower for phrase in ["blood test", "blood draw", "blood sample", "toxicology"]),
            "field_sobriety": any(phrase in text_lower for phrase in ["field sobriety", "sfst", "horizontal gaze", "walk and turn", "one leg stand", "hgn"]),
            "dui_charge": any(phrase in text_lower for phrase in ["dui", "dwi", "driving under the influence", "actual physical control", "reckless driving"]),
            "implied_consent": any(phrase in text_lower for phrase in ["implied consent", "rcw 46.20.308", "license suspension", "dol hearing"]),
            "bac_reading": bool(re.search(r'\b0\.\d{2,3}\b', text_lower)),  # Matches BAC like 0.08, 0.125
        }

        dui_count = sum(dui_indicators.values())

        # DOL hearing specific indicators
        dol_indicators = {
            "dol_hearing": "dol hearing" in text_lower or "department of licensing" in text_lower,
            "license_suspension": "license suspension" in text_lower or "license revocation" in text_lower,
            "implied_consent_warning": "implied consent" in text_lower and ("warning" in text_lower or "advisement" in text_lower),
            "refusal": "refused" in text_lower and ("breath" in text_lower or "test" in text_lower),
        }

        dol_count = sum(dol_indicators.values())

        # Determine case type
        if dui_count >= 2 and dol_count >= 2:
            detected_type = "DUI with DOL hearing issues"
            recommendation = "analyze_dui_criminal AND analyze_dui_dol_hearing"
        elif dui_count >= 2:
            detected_type = "DUI criminal case"
            recommendation = "analyze_dui_criminal"
        elif dol_count >= 2:
            detected_type = "DUI DOL hearing"
            recommendation = "analyze_dui_dol_hearing"
        else:
            detected_type = "General criminal case (non-DUI)"
            recommendation = "analyze_criminal_case"

        # Build evidence list
        evidence = []
        if dui_indicators["breath_test"]:
            evidence.append("✓ Breath test mentioned")
        if dui_indicators["blood_test"]:
            evidence.append("✓ Blood test mentioned")
        if dui_indicators["field_sobriety"]:
            evidence.append("✓ Field sobriety tests documented")
        if dui_indicators["dui_charge"]:
            evidence.append("✓ DUI/DWI charge present")
        if dui_indicators["bac_reading"]:
            evidence.append("✓ BAC reading found")
        if dui_indicators["implied_consent"]:
            evidence.append("✓ Implied consent language")
        if dol_indicators["dol_hearing"]:
            evidence.append("✓ DOL hearing referenced")
        if dol_indicators["license_suspension"]:
            evidence.append("✓ License suspension issue")
        if dol_indicators["refusal"]:
            evidence.append("✓ Test refusal documented")

        if not evidence:
            evidence.append("⚠ No DUI-specific indicators found")

        # Format response
        files_list = "\n".join([f"  - {f}" for f in files_analyzed])
        evidence_list = "\n".join([f"  {e}" for e in evidence])

        response = (
            f"**CASE TYPE DETECTION**\n\n"
            f"**Files Analyzed:**\n{files_list}\n\n"
            f"**Detected Type:** {detected_type}\n\n"
            f"**Evidence:**\n{evidence_list}\n\n"
            f"**Recommended Analysis:** {recommendation}\n\n"
            f"---\n\n"
            f"**Please confirm:** Is this detection correct, or should I analyze as:\n"
            f"  • DUI criminal case\n"
            f"  • DUI DOL hearing\n"
            f"  • General criminal case\n"
            f"  • Both DUI criminal AND DOL hearing"
        )

        return [TextContent(type="text", text=response)]

    elif name == "analyze_dui_criminal":
        filename = arguments.get("filename")

        # If filename provided, analyze single file; otherwise batch analyze all files
        if filename:
            result = await call_tool("read_case_sanitized", {"filename": filename})
            sanitized_text = result[0].text
            file_context = f"**FILE: {filename}**\n\n"
        else:
            # Batch mode - get all files
            files = sorted(CASE_FILES_DIR.glob("*.pdf"))
            if not files:
                return [TextContent(type="text", text="No PDF files found in drop folder")]

            file_context = f"**BATCH ANALYSIS: {len(files)} files**\n\n"
            sanitized_text = ""
            for i, file_path in enumerate(files, 1):
                file_context += f"{i}. {file_path.name}\n"
                try:
                    text = extract_pdf_text(file_path)
                    sanitizer = CaseSanitizer()
                    s_text, mapping = sanitizer.sanitize_text(text)
                    uuid = save_sanitization_map(file_path, mapping)
                    sanitized_text += f"\n{'='*80}\n## FILE {i}: {file_path.name}\n{'='*80}\n\n{s_text}\n\n"
                except Exception as e:
                    sanitized_text += f"\n{'='*80}\n## FILE {i}: {file_path.name}\n{'='*80}\nERROR: {e}\n\n"
            file_context += "\n"

        # Washington DUI-specific criminal analysis prompt
        prompt = (
            f"{file_context}"
            f"{sanitized_text}\n\n"
            f"---\n\n"
            f"**COMPREHENSIVE DUI CRIMINAL DEFENSE ANALYSIS (Washington State)**\n\n"
            f"Analyze all files above for DUI defense issues under Washington law (RCW 46.61.502/504):\n\n"
            f"## 1. INITIAL STOP\n"
            f"**Reasonable Suspicion** (RCW 10.31.100, State v. Ladson)\n"
            f"- What facts justified the stop?\n"
            f"- Weaving within lane? (State v. Prado - insufficient alone)\n"
            f"- Equipment violations? (Pretext stops analysis)\n"
            f"- Anonymous tips? (Navarette v. California standard)\n"
            f"- Suppression likelihood: High/Medium/Low\n\n"
            f"## 2. ARREST & PROBABLE CAUSE\n"
            f"**Probable Cause for DUI Arrest** (State v. O'Neill)\n"
            f"- Observable facts at time of arrest:\n"
            f"  - Driving behavior\n"
            f"  - Physical appearance (eyes, odor, speech, balance)\n"
            f"  - Field sobriety tests (if any - were they properly administered?)\n"
            f"  - Statements/admissions\n"
            f"  - PBT results (admissible for PC, not at trial)\n"
            f"- Timing: When did PC attach?\n"
            f"- Weaknesses in PC?\n\n"
            f"## 3. BREATH/BLOOD TEST ISSUES\n"
            f"**Test Compliance** (RCW 46.61.506, WAC 448-14)\n"
            f"- Implied consent warnings given? (RCW 46.20.308)\n"
            f"- 15-minute observation period? (WAC 448-14-020)\n"
            f"- Operator certification current?\n"
            f"- Machine certification current? (annual calibration)\n"
            f"- Testing procedure followed? (two valid tests within 0.02)\n"
            f"- Blood draw (if applicable): Proper warrant/consent? Qualified phlebotomist?\n"
            f"- Refusal issues: Proper refusal warnings?\n"
            f"- Suppression opportunities?\n\n"
            f"## 4. SEARCH & SEIZURE\n"
            f"**4th Amendment Issues**\n"
            f"- Vehicle searches: Lawful? (Arizona v. Gant - search incident to arrest)\n"
            f"- Inventory searches: Proper policy followed?\n"
            f"- Consent searches: Voluntary?\n"
            f"- Warrant issues (if applicable): Supported by PC? Properly executed?\n\n"
            f"## 5. MIRANDA & STATEMENTS\n"
            f"**5th Amendment Issues**\n"
            f"- Custodial interrogation: When did custody begin?\n"
            f"- Miranda warnings: Given before questioning?\n"
            f"- Invocation: Did client invoke? Was it honored?\n"
            f"- Voluntariness of statements\n"
            f"- Suppressible statements?\n\n"
            f"## 6. PROCEDURAL/TECHNICAL ISSUES\n"
            f"- Dash cam/body cam: Gaps in recording?\n"
            f"- Chain of custody (blood samples)\n"
            f"- Discovery violations\n"
            f"- Speedy trial issues\n"
            f"- Brady/Giglio material\n\n"
            f"## 7. WASHINGTON-SPECIFIC DEFENSES\n"
            f"- Rising BAC defense (State v. Shumaker)\n"
            f"- Mouth alcohol (State v. Mecham)\n"
            f"- Medical conditions affecting tests\n"
            f"- Radio frequency interference\n\n"
            f"**SUMMARY:**\n"
            f"Provide:\n"
            f"1. **Strongest Defense Issues** (prioritized 1-3)\n"
            f"2. **Motion Strategy** (CrR 3.5, 3.6 - what to file)\n"
            f"3. **Trial Themes** (if motions fail)\n"
            f"4. **Plea Leverage** (how issues affect negotiation)\n"
            f"5. **Case Assessment** (Dismissal likely? Reduction? Trial?)\n"
        )

        return [TextContent(type="text", text=prompt)]

    elif name == "analyze_dui_dol_hearing":
        filename = arguments.get("filename")

        # If filename provided, analyze single file; otherwise batch analyze all files
        if filename:
            result = await call_tool("read_case_sanitized", {"filename": filename})
            sanitized_text = result[0].text
            file_context = f"**FILE: {filename}**\n\n"
        else:
            # Batch mode
            files = sorted(CASE_FILES_DIR.glob("*.pdf"))
            if not files:
                return [TextContent(type="text", text="No PDF files found in drop folder")]

            file_context = f"**BATCH ANALYSIS: {len(files)} files**\n\n"
            sanitized_text = ""
            for i, file_path in enumerate(files, 1):
                file_context += f"{i}. {file_path.name}\n"
                try:
                    text = extract_pdf_text(file_path)
                    sanitizer = CaseSanitizer()
                    s_text, mapping = sanitizer.sanitize_text(text)
                    uuid = save_sanitization_map(file_path, mapping)
                    sanitized_text += f"\n{'='*80}\n## FILE {i}: {file_path.name}\n{'='*80}\n\n{s_text}\n\n"
                except Exception as e:
                    sanitized_text += f"\n{'='*80}\n## FILE {i}: {file_path.name}\n{'='*80}\nERROR: {e}\n\n"
            file_context += "\n"

        # Washington DOL hearing-specific analysis
        prompt = (
            f"{file_context}"
            f"{sanitized_text}\n\n"
            f"---\n\n"
            f"**DUI DOL IMPLIED CONSENT HEARING ANALYSIS (Washington State)**\n\n"
            f"Analyze for license suspension hearing defenses under RCW 46.20.308:\n\n"
            f"## 1. HEARING ELIGIBILITY & TIMING\n"
            f"- Was hearing requested within 7 days? (RCW 46.20.308(8))\n"
            f"- Was temporary license issued?\n"
            f"- Suspension start date?\n"
            f"- Prior offenses affecting suspension length?\n\n"
            f"## 2. FOUR ISSUES FOR DOL HEARING\n"
            f"Per RCW 46.20.308(9), DOL can only consider:\n\n"
            f"**Issue 1: Lawful Arrest**\n"
            f"- Was officer lawfully present? (Community caretaking? Traffic stop?)\n"
            f"- Reasonable suspicion for stop?\n"
            f"- Probable cause for arrest?\n"
            f"- State v. Prado weaving analysis\n"
            f"- Arrest timing (before or after test?)\n\n"
            f"**Issue 2: Reasonable Grounds**\n"
            f"- Did officer have reasonable grounds to believe:\n"
            f"  (a) Person drove while under influence, AND\n"
            f"  (b) Person was under influence?\n"
            f"- What facts supported this belief?\n"
            f"- Weaker standard than probable cause\n"
            f"- Focus on officer's articulable basis\n\n"
            f"**Issue 3: Implied Consent Warnings** (CRITICAL)\n"
            f"- Were warnings given per RCW 46.20.308(2)?\n"
            f"- Required warning elements:\n"
            f"  □ Advise of right to additional test\n"
            f"  □ Advise refusal will result in revocation/denial\n"
            f"  □ Advise refusal may be used in criminal trial\n"
            f"  □ Advise that test refusal = 1 year minimum suspension\n"
            f"  □ If prior offense: 2 years or longer\n"
            f"  □ If CDL: disqualification\n"
            f"- Warnings must be substantially compliant (State v. MacDonald)\n"
            f"- Were warnings given BEFORE refusal/test?\n"
            f"- Were warnings clear and understandable?\n"
            f"- Language barriers?\n\n"
            f"**Issue 4: Refusal or Test Result**\n"
            f"FOR REFUSAL CASES:\n"
            f"- Did person refuse?\n"
            f"- Was refusal unequivocal?\n"
            f"- Physical inability to provide sample? (dental issues, etc.)\n"
            f"- Did person attempt but fail? (distinguish from refusal)\n"
            f"- Unconscious/medical emergency? (no refusal - draw blood)\n\n"
            f"FOR TEST RESULT CASES (BAC ≥ 0.08 or THC ≥ 5.0):\n"
            f"- BAC result?\n"
            f"- Test compliance:\n"
            f"  □ 15-minute observation? (WAC 448-14-020)\n"
            f"  □ Operator certified?\n"
            f"  □ Machine certified?\n"
            f"  □ Two valid tests within 0.02?\n"
            f"- Was sample taken within 2 hours of driving?\n\n"
            f"## 3. HEARING STRATEGY\n"
            f"**Burden of Proof:**\n"
            f"- DOL has burden on all four issues\n"
            f"- Preponderance of evidence standard\n"
            f"- Challenge: Which issue is weakest?\n\n"
            f"**Common Defenses:**\n"
            f"- Improper warnings (most common win)\n"
            f"- No reasonable grounds\n"
            f"- Unlawful stop/arrest\n"
            f"- Test not within 2 hours\n"
            f"- Test procedure violations\n"
            f"- Refusal was actually inability\n\n"
            f"**Discovery Requests:**\n"
            f"- Dash cam/body cam\n"
            f"- Officer training records (implied consent warnings)\n"
            f"- Machine calibration records\n"
            f"- Operator certification\n"
            f"- Prior discipline/Brady material\n\n"
            f"## 4. IGNITION INTERLOCK ELIGIBILITY\n"
            f"- Can client get IID during suspension? (RCW 46.20.720)\n"
            f"- Waiting periods for IID eligibility\n"
            f"- Cost-benefit of IID vs. full suspension\n\n"
            f"**HEARING ASSESSMENT:**\n"
            f"Provide:\n"
            f"1. **Likelihood of Success** (Win/Lose/50-50)\n"
            f"2. **Strongest Issue** to challenge\n"
            f"3. **Weakest DOL Evidence** (focus cross-exam here)\n"
            f"4. **Discovery Needed** before hearing\n"
            f"5. **Stipulation Strategy** (stipulate to some issues to focus on strongest?)\n"
            f"6. **IID Recommendation** (fight hearing or get IID?)\n"
        )

        return [TextContent(type="text", text=prompt)]

    elif name == "analyze_criminal_case":
        filename = arguments.get("filename")

        # If filename provided, analyze single file; otherwise batch analyze all files
        if filename:
            result = await call_tool("read_case_sanitized", {"filename": filename})
            sanitized_text = result[0].text
            file_context = f"**FILE: {filename}**\n\n"
        else:
            # Batch mode
            files = sorted(CASE_FILES_DIR.glob("*.pdf"))
            if not files:
                return [TextContent(type="text", text="No PDF files found in drop folder")]

            file_context = f"**BATCH ANALYSIS: {len(files)} files**\n\n"
            sanitized_text = ""
            for i, file_path in enumerate(files, 1):
                file_context += f"{i}. {file_path.name}\n"
                try:
                    text = extract_pdf_text(file_path)
                    sanitizer = CaseSanitizer()
                    s_text, mapping = sanitizer.sanitize_text(text)
                    uuid = save_sanitization_map(file_path, mapping)
                    sanitized_text += f"\n{'='*80}\n## FILE {i}: {file_path.name}\n{'='*80}\n\n{s_text}\n\n"
                except Exception as e:
                    sanitized_text += f"\n{'='*80}\n## FILE {i}: {file_path.name}\n{'='*80}\nERROR: {e}\n\n"
            file_context += "\n"

        # General criminal defense analysis
        prompt = (
            f"{file_context}"
            f"{sanitized_text}\n\n"
            f"---\n\n"
            f"**GENERAL CRIMINAL DEFENSE ANALYSIS (Washington State)**\n\n"
            f"Comprehensive criminal defense review under Washington law:\n\n"
            f"## 1. INITIAL CONTACT & STOP\n"
            f"**Lawfulness of Stop/Seizure**\n"
            f"- Terry stop: Reasonable suspicion? (RCW 10.31.100)\n"
            f"- Traffic stop: Valid traffic infraction observed?\n"
            f"- Pretext stop analysis\n"
            f"- Consensual encounter vs. seizure\n"
            f"- Anonymous tip: Sufficient corroboration?\n"
            f"- Unlawful extension of stop?\n\n"
            f"## 2. ARREST & PROBABLE CAUSE\n"
            f"**Probable Cause Analysis**\n"
            f"- What facts supported arrest?\n"
            f"- Timing: When did PC attach?\n"
            f"- Warrantless arrest: Exigent circumstances?\n"
            f"- Misdemeanor: Committed in officer's presence?\n"
            f"- Citizen's arrest (if applicable)\n"
            f"- Weaknesses in PC?\n\n"
            f"## 3. SEARCH & SEIZURE (4th Amendment)\n"
            f"**Search Analysis**\n"
            f"- Search incident to arrest: Lawful? (Arizona v. Gant for vehicles)\n"
            f"- Consent search: Voluntary? Scope exceeded?\n"
            f"- Vehicle search: Automobile exception? Inventory?\n"
            f"- Plain view doctrine\n"
            f"- Warrant: Supported by PC? Properly executed? Staleness?\n"
            f"- Knock-and-announce violations\n"
            f"- Protective sweep: Justified?\n"
            f"- Cell phone/digital searches: Warrant required\n\n"
            f"## 4. MIRANDA & STATEMENTS (5th Amendment)\n"
            f"**Statement Analysis**\n"
            f"- Custody: When did it begin?\n"
            f"- Interrogation: Questions likely to elicit incriminating response?\n"
            f"- Miranda warnings: Given before custodial interrogation?\n"
            f"- Invocation: Right to silence? Right to attorney? Was it honored?\n"
            f"- Voluntariness: Coerced? Impaired? False promises?\n"
            f"- Booking questions exception\n"
            f"- Spontaneous statements (not interrogation)\n\n"
            f"## 5. IDENTIFICATION ISSUES\n"
            f"**Identification Procedures**\n"
            f"- Photo montage/lineup: Suggestive? (State v. Kinard)\n"
            f"- Show-up: Unduly suggestive? Necessary?\n"
            f"- In-court ID: Independent source?\n"
            f"- Eyewitness reliability factors (Manson v. Brathwaite)\n\n"
            f"## 6. CHARGING & PROCEDURAL ISSUES\n"
            f"- Charging: Sufficient probable cause? (CrR 2.1)\n"
            f"- Speedy trial: CrR 3.3 violations?\n"
            f"- Discovery: Brady violations? Giglio? CrR 4.7 compliance?\n"
            f"- Statute of limitations (RCW 9A.04.080)\n"
            f"- Jurisdiction: Proper venue?\n"
            f"- Prior convictions: Properly pleaded?\n\n"
            f"## 7. EVIDENCE ISSUES\n"
            f"**Admissibility Challenges**\n"
            f"- Hearsay exceptions: Properly applied?\n"
            f"- Expert testimony: ER 702 (Frye standard in WA)\n"
            f"- Character evidence: ER 404(b) - improper propensity?\n"
            f"- Prejudicial evidence: ER 403 analysis\n"
            f"- Authentication issues\n"
            f"- Chain of custody\n\n"
            f"## 8. WASHINGTON-SPECIFIC DEFENSES\n"
            f"- Necessity defense (State v. Diana)\n"
            f"- Duress (RCW 9A.16.060)\n"
            f"- Self-defense (RCW 9A.16.110)\n"
            f"- Defense of property\n"
            f"- Entrapment (State v. Lively)\n"
            f"- Mistake of fact\n"
            f"- Diminished capacity\n\n"
            f"## 9. SENTENCING ISSUES (if applicable)\n"
            f"- Offender score calculation\n"
            f"- Sentencing alternatives (DOSA, SSOSA, etc.)\n"
            f"- Mitigating factors\n"
            f"- Exceptional sentences\n\n"
            f"**CASE ASSESSMENT:**\n"
            f"Provide:\n"
            f"1. **Strongest Defense Issues** (prioritized top 3)\n"
            f"2. **Suppression Motions** to file (CrR 3.5, 3.6)\n"
            f"3. **Dismissal Potential** (Knapstad motion? Other?)\n"
            f"4. **Weaknesses in State's Case**\n"
            f"5. **Plea Leverage** (how issues affect negotiation)\n"
            f"6. **Trial Strategy** (if case proceeds)\n"
            f"7. **Verdict Prediction** (if tried today)\n"
        )

        return [TextContent(type="text", text=prompt)]

    elif name == "save_analysis":
        analysis_content = arguments["analysis_content"]
        client_initials = arguments["client_initials"]
        case_date = arguments.get("case_date")

        # Validate that analysis uses initials, not full names
        # Quick check for common name patterns that shouldn't be there
        suspicious_patterns = [
            r'Defendant:\s+[A-Z][a-z]+ [A-Z][a-z]+',  # "Defendant: John Smith"
            r'Officer:\s+[A-Z][a-z]+ [A-Z][a-z]+',    # "Officer: Jane Doe"
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, analysis_content):
                return [TextContent(
                    type="text",
                    text="⚠️  ERROR: Analysis contains full names instead of initials. "
                         "Please regenerate the analysis using only initials (e.g., AFF, JS) for all people."
                )]

        # Determine filename date
        if case_date:
            file_date = case_date
        else:
            file_date = datetime.now().strftime("%Y-%m-%d")

        # Save to Obsidian
        obsidian_dir = Path.home() / 'Library/CloudStorage/Dropbox/Obsidian/Tony\'s Vault/MCP Legal'
        obsidian_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{file_date} {client_initials}.md"
        file_path = obsidian_dir / filename

        with open(file_path, 'w') as f:
            f.write(analysis_content)

        return [TextContent(
            type="text",
            text=f"✓ Analysis saved to Obsidian:\n{file_path}\n\n"
                 f"Filename: {filename}"
        )]

    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


async def main():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
