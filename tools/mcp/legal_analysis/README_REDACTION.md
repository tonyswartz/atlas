# Legal File Sanitization Workflow

**Privacy-first legal case analysis** with automated PII sanitization and manual verification.

## Overview

This system automatically sanitizes personally identifiable information (PII) from legal PDFs and transcripts by:
- ✅ Extracting text from PDFs (with OCR for scanned documents)
- ✅ Sanitizing all PII (names, case numbers, SSN, DOB, addresses, etc.)
- ✅ Converting to clean .txt files for analysis
- ✅ Preserving initials-based mapping (AFF ← Alexander Field Fredrickson)

**Critical Security Feature:** The MCP server (Claude) **NEVER has access to original PDFs**. Only pre-sanitized .txt files are accessible for analysis.

---

## Folder Structure

```
~/Dropbox/MCP Analysis/
├── originals/              # YOU drop PDFs/transcripts here (MCP NO ACCESS)
├── sanitized/              # Auto-sanitized .txt files (MCP ONLY READS THIS)
└── .sanitization_maps/     # PII mappings (gitignored, MCP no access)
```

---

## Complete Workflow

### 1. Drop Original File

Place your legal PDF or transcript in:
```
~/Dropbox/MCP Analysis/originals/
```

**Supported formats:**
- PDFs (including scanned documents - OCR enabled)
- Text transcripts (body cam, 911 calls)

### 2. Automatic Sanitization (30 seconds)

The file watcher runs every 30 seconds and automatically:
1. Detects new files in `originals/`
2. Extracts text from PDFs (with OCR for scanned docs)
3. Sanitizes all PII using regex patterns
4. Saves sanitized .txt to `sanitized/`
5. Saves PII mapping to `.sanitization_maps/`

**What gets sanitized:**
- ✓ Full names (client, officers, attorneys, judges) → Initials (AFF, GLZ)
- ✓ Last names used alone in narrative text
- ✓ Case numbers (all formats) → [CASE]
- ✓ SSN → [SSN]
- ✓ DOB → [REDACTED]
- ✓ Phone numbers → [PHONE]
- ✓ Addresses → [ADDRESS]
- ✓ License plates → [PLATE]
- ✓ Driver's license numbers → [LICENSE]
- ✓ Badge numbers → [BADGE]

**What gets preserved:**
- ✓ Dates (except DOB)
- ✓ Legal citations and statutes
- ✓ Narrative content and context
- ✓ Document structure in text form

**Tradeoff:** Checkboxes and visual layout are lost in text conversion, but PII sanitization is more reliable and secure.

### 3. Manual Verification (REQUIRED)

**Open the sanitized .txt file** in any text editor:
```
~/Dropbox/MCP Analysis/sanitized/YourCase.txt
```

**Verify:**
1. All client names are replaced with initials (AFF, GLZ, etc.)
2. All officer/attorney names are replaced with initials
3. Case numbers show as [CASE]
4. SSN, DOB, phones show as [SSN], [REDACTED], [PHONE]
5. Document text is readable and makes sense

**If you find missed PII:**
- Manually edit the .txt file to replace it
- Or report the pattern so we can improve the regex

### 4. Analyze with Claude

**In Claude Desktop:**
1. Ask: "List case files"
   - Shows sanitized .txt files in sanitized/ folder
2. Ask: "Detect case type for [filename.txt]"
   - Claude auto-detects: DUI criminal, DUI DOL, or general criminal
3. Confirm the detected type
4. Claude analyzes the sanitized text

**Analysis includes:**
- Strongest defense issues (top 3)
- Suppression motions to file
- Weaknesses in State's case
- Plea leverage
- Trial strategy
- Verdict prediction

**Security:** Claude only sees the pre-sanitized .txt file. Original PDF is not accessible to the MCP server.

### 5. Save Analysis to Obsidian

After Claude generates the analysis:
```
Ask: "Save this analysis"
```

Claude will:
- Verify analysis uses initials (not full names)
- Save to: `~/Obsidian/Tony's Vault/MCP Legal/YYYY-MM-DD [Initials].md`
- Format: Clean markdown with date + client initials

---

## Name Mapping Reference

The sanitization maps preserve the PII → initials mapping for your reference:

**Example mapping** (`~/Dropbox/MCP Analysis/.sanitization_maps/abc123.json`):
```json
{
  "uuid": "abc123",
  "original_file": ".../originals/Case.pdf",
  "timestamp": "2026-02-20T10:30:00",
  "mapping": {
    "AFF": "Alexander Field Fredrickson",
    "GLZ": "Gregory L. Zempel"
  }
}
```

You can reference this if you need to know which initials map to which real names.

---

## Manual Sanitization (If Needed)

If the automatic sanitization misses PII:

**Edit the .txt file directly:**
1. Open sanitized .txt file in any text editor
2. Find the missed PII (name, number, etc.)
3. Replace with appropriate placeholder:
   - Name → Initials (AFF)
   - Case number → [CASE]
   - SSN → [SSN]
   - Phone → [PHONE]
4. Save the file

**Report the pattern:**
- Let me know what pattern was missed
- I can add it to the regex patterns in `sanitize_to_text.py`

---

## Monitoring & Troubleshooting

**Check if watcher is running:**
```bash
launchctl list | grep pdf-redaction
```

**View logs:**
```bash
tail -f ~/atlas/logs/pdf-redaction-watcher.log
```

**Manually sanitize a single PDF:**
```bash
cd ~/atlas/tools/mcp/legal_analysis
python3 sanitize_to_text.py \
  ~/Dropbox/"MCP Analysis"/originals/case.pdf \
  ~/Dropbox/"MCP Analysis"/sanitized/case.txt
```

**Restart the watcher:**
```bash
launchctl unload ~/Library/LaunchAgents/com.atlas.pdf-redaction-watcher.plist
launchctl load ~/Library/LaunchAgents/com.atlas.pdf-redaction-watcher.plist
```

---

## Security Guarantees

1. **MCP Server Isolation**: Server ONLY has access to `sanitized/` folder
   - Cannot read `originals/` (where PDFs are dropped)
   - Cannot read `.sanitization_maps/` (PII mappings)
   - Literally impossible for Claude to see original PDFs

2. **Pre-Sanitization**: All files are sanitized BEFORE being accessible to MCP
   - Text extraction happens outside of MCP server
   - PII removal happens outside of MCP server
   - MCP server only sees already-sanitized .txt files

3. **Defense in Depth**: Server does second sanitization pass on .txt files
   - If watcher misses something, server catches it
   - Double-layer protection against PII leakage

4. **Manual Verification Gate**: You always review before analysis
   - Open .txt file to verify sanitization
   - Catch any missed PII
   - Edit manually if needed
   - Final control over what Claude sees

5. **Mapping Security**: PII mappings stored in `.sanitization_maps/` (gitignored)
   - Never synced to version control
   - Never accessible to MCP server
   - Only for your reference
   - Format: `{"AFF": "Alexander Field Fredrickson"}`

---

## Pattern-Based Sanitization

The system uses regex patterns to catch:

**Names:**
```python
# Structured fields: "Defendant: John Smith"
r'(Defendant|Attorney|Officer|Prosecutor):\s+([A-Z][a-z]+...)'

# Case captions: "State v. John Smith"
r'State v\.?\s+([A-Z][a-z]+...)'

# Names with titles: "Deputy John Smith"
r'(Deputy|Officer|Trooper|Sgt\.)\s+([A-Z][a-z]+...)'
```

**Other PII:**
- SSN: `\d{3}-\d{2}-\d{4}`
- Phone: `\(?d{3}\)?[-.]\d{3}[-.]\d{4}`
- License plates: `[A-Z]{2,3}[-\s]?\d{3,4}`
- Driver's licenses: `[A-Z]{1,}[0-9]{3,}[A-Z0-9]{3,}`
- Addresses: `\d+ [Street|Ave|Rd...]`

If a pattern is missed, manually edit the .txt file or report it for improvement.

---

## Tips

- **Batch processing**: Drop multiple PDFs/transcripts in `originals/` - watcher processes all
- **File naming**: Keep descriptive names ("Smith DUI Discovery.pdf") - .txt output will have same name
- **Review time**: Budget 1-2 minutes per .txt file for verification (faster than reviewing PDFs)
- **False positives**: "Prosecuting Attorney" might get redacted as a name - that's fine, it's not PII
- **Keep originals**: The `originals/` folder preserves your source PDFs forever
- **Searchable**: .txt files are fully searchable - easier to find specific content than in PDFs
- **Version control**: If you manually edit a .txt file, watcher won't overwrite it (uses state file)

---

## What's Next

After analysis, you can:
- Generate prosecutor email drafts (substance paragraphs only)
- Create case summaries
- Draft motion arguments
- Identify strongest suppression issues

All while maintaining PII security throughout the workflow.
