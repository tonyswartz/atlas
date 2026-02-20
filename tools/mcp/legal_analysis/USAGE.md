# Legal Analysis MCP - Usage Guide

## Quick Start

### 1. Add Files to Drop Folder

```bash
# Copy discovery files here:
~/Library/CloudStorage/Dropbox/MCP Analysis/
```

### 2. Analyze in Claude Desktop

**Important**: Use MCP tools, don't drag/drop PDF directly!

```
List case files
```

```
Analyze "filename.pdf" for DUI criminal issues
```

### 3. Save Analysis to Obsidian

Analysis is automatically formatted for saving to:
```
~/Obsidian/Tony's Vault/MCP Legal/YYYY-MM-DD [Initials].md
```

Example: `2026-01-28 AFF.md`

## What Gets Sanitized (Using Initials Now!)

### ✅ Names → Initials
- Client: Alexander Field Fredrickson → **AFF**
- Prosecutor: Gregory L. Zempel → **GLZ**
- Officer: Deputy Garcia → **G**
- Attorney: John Smith → **JS**

### ✅ Other PII
- DOB: `04/02/1990` → `[REDACTED]`
- Case #: `18274` → `[CASE_NUM_001]`
- Phone: `509-962-7520` → `[PHONE_REDACTED]`
- Address: `820 Milwaukee Dr` → `[ADDRESS_001]`
- License Plate: `CPK0543` → `[PLATE_001]`
- Serial #: `ABC123456` → `[SERIAL_001]`
- Badge #: `Badge #1234` → `[BADGE_001]`

## Analysis Types

### DUI Criminal Defense
```
Analyze "filename.pdf" for DUI criminal issues
```

**Covers:**
- Reasonable suspicion for stop (State v. Prado)
- Probable cause for arrest
- Breath/blood test compliance (WAC 448-14)
- Search & seizure (4th Amendment)
- Miranda warnings (5th Amendment)
- Suppression motion strategy (CrR 3.5, 3.6)

### DOL Hearing (License Suspension)
```
Analyze "filename.pdf" for DOL hearing defenses
```

**Covers (The Four DOL Issues):**
1. Lawful arrest
2. Reasonable grounds
3. Implied consent warnings (RCW 46.20.308)
4. Refusal or test result

### General Criminal Case
```
Analyze "filename.pdf" for criminal defense issues
```

**Covers:**
- Stop/seizure analysis
- Probable cause
- Search & seizure
- Miranda compliance
- Charging issues
- Evidence admissibility

## Sample Analysis Format

```markdown
# DUI Criminal Defense Analysis

**Client**: AFF
**Prosecutor**: GLZ
**Stop Date**: 2026-01-28
**Analysis Date**: 2026-02-19

---

## SUPPRESSION ISSUES

### 1. Initial Stop - Reasonable Suspicion ⚠️

Officer stated "weaving within lane" as basis for stop. Under *State v. Prado*,
weaving within a single lane does NOT establish reasonable suspicion unless:
- Pronounced/repeated
- Combined with other factors
- Unsafe driving

**Issue**: Report only documents single instance. Insufficient under *Prado*.

**Motion**: CrR 3.6 suppression - all evidence fruit of unlawful stop.

### 2. Probable Cause for Arrest ✅

Officer noted:
- Odor of alcohol
- Bloodshot eyes
- Failed HGN (4 of 6 clues)
- Admission: "two beers"

**Likely sufficient** for PC under totality of circumstances.

### 3. Breath Test Compliance (WAC 448-14) ⚠️

**Issues found:**
- Observation period: Only 14 minutes documented (requires 15)
- Mouth alcohol: No affirmative statement of check
- Operator cert: Expires [DATE] - verify current at test time

**Motion**: Suppress breath test results - WAC non-compliance.

---

## MOTION STRATEGY

**File:**
1. CrR 3.6 motion to suppress stop (weak RS)
2. CrR 3.5 motion to suppress breath test (WAC violations)

**Strength:**
- Stop suppression: STRONG (Prado violation)
- Breath test suppression: MODERATE (observation period)

**Outcome if successful:**
- No breath test = no DUI per se
- Forced to prove impairment = weaker case
- Better plea leverage

---

*Analysis based on sanitized discovery*
*Sanitization mapping: [UUID].json*
```

## Obsidian Integration

### Filename Format
- `YYYY-MM-DD [ClientInitials].md`
- Example: `2026-01-28 AFF.md`
- Date: Extracted from violation/stop date in document
- Initials: First person identified (defendant)

### Location
```
~/Obsidian/Tony's Vault/MCP Legal/
```

### Benefits
- ✅ Searchable in Obsidian
- ✅ Linked to other case notes
- ✅ Markdown format (portable)
- ✅ Date-organized
- ✅ Version control (multiple analyses)

## Body Cam Transcripts

For raw STT transcripts:

```
Analyze "bodycam_transcript.txt" for Miranda compliance
```

The helper script will:
1. Add speaker labels ([OFFICER], [DEFENDANT])
2. Sanitize names/case numbers
3. Extract key moments (Miranda, statements, FSTs)
4. Analyze for legal issues

## Privacy Notes

### What Stays Local
- ✅ Original PDFs (never uploaded)
- ✅ Sanitization maps (`~/atlas/data/legal_sanitization_maps/`)
- ✅ Full names → initials mapping

### What Goes to Claude
- ✅ Sanitized text only
- ✅ Initials instead of names
- ✅ Redacted PII
- ✅ Preserved: BAC, times, citations, observations

### Verify Sanitization
If you see real names in Claude's analysis:
1. ❌ You dragged PDF into chat (bypasses MCP)
2. ✅ Must use: `Analyze "filename.pdf"`

## Troubleshooting

**"No files found"**
- Check: `~/Library/CloudStorage/Dropbox/MCP Analysis/`
- Verify Dropbox sync complete

**"Real names still showing"**
- Did you use MCP tool or drag/drop PDF?
- Restart Claude Desktop
- Verify 🔌 icon shows "legal-analysis" connected

**"Analysis not saving to Obsidian"**
- Manually save for now
- Auto-save coming in future update

## Advanced: LegalKanban Integration

See [LEGALKANBAN_INTEGRATION.md](LEGALKANBAN_INTEGRATION.md) for:
- Analyzing case folders directly
- Saving to case-specific locations
- Multi-file batch analysis

## Next Features

- [ ] Auto-save analysis to Obsidian
- [ ] Body cam video analysis (visual + audio)
- [ ] Multi-file timeline generation
- [ ] LegalKanban case folder integration
- [ ] Witness statement analysis
