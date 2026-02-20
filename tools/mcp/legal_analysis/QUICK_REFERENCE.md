# Legal Analysis MCP - Quick Reference

## ChatGPT Commands

### DUI Criminal Defense Analysis
Comprehensive Washington DUI analysis - reasonable suspicion, probable cause, breath/blood tests, 4th/5th Amendment, warrants, suppression opportunities.

**Single file:**
```
Analyze DUI for "Smith Arrest Report.pdf"
```

**All files in folder (batch):**
```
Analyze DUI for this case
```
or
```
Analyze all files for DUI criminal issues
```

---

### DUI DOL Hearing Analysis
Implied consent/license suspension hearing defenses under RCW 46.20.308.

**Single file:**
```
Analyze DOL hearing for "Smith DOL File.pdf"
```

**All files (batch):**
```
Analyze DOL hearing for this case
```

---

### General Criminal Case Analysis
Non-DUI criminal defense - reasonable suspicion, PC, search/seizure, Miranda, charging, evidence issues.

**Single file:**
```
Analyze criminal case for "Assault Report.pdf"
```

**All files (batch):**
```
Analyze this criminal case
```

---

## What Gets Analyzed

### DUI Criminal Analysis Covers:
1. **Initial Stop** - Reasonable suspicion (State v. Prado weaving analysis)
2. **Arrest & PC** - Probable cause timing and basis
3. **Breath/Blood Tests** - WAC 448-14 compliance, operator cert, machine cert, observation period
4. **Search & Seizure** - Vehicle searches, inventory, warrants
5. **Miranda** - Custody, interrogation, invocation
6. **Procedural Issues** - Chain of custody, discovery, speedy trial
7. **WA Defenses** - Rising BAC, mouth alcohol, medical conditions

**Output:** Prioritized issues, motion strategy (CrR 3.5/3.6), trial themes, plea leverage, case assessment

### DOL Hearing Analysis Covers:
The **Four DOL Issues** (RCW 46.20.308(9)):
1. **Lawful Arrest** - Officer presence, RS for stop, PC for arrest
2. **Reasonable Grounds** - Articulable basis for DUI belief
3. **Implied Consent Warnings** - RCW 46.20.308(2) compliance (most common defense)
4. **Refusal or Test Result** - Refusal vs inability, test within 2 hours, procedure compliance

**Plus:** IID eligibility, discovery requests, hearing strategy, stipulation strategy

**Output:** Win likelihood, strongest issue, weakest DOL evidence, IID recommendation

### Criminal Case Analysis Covers:
1. **Stop/Seizure** - Terry stop, traffic stop, pretext analysis
2. **PC for Arrest** - Timing, warrantless arrest exceptions
3. **Search & Seizure** - SITA, consent, vehicle, warrant, plain view, digital searches
4. **Miranda** - Custody, interrogation, invocation, voluntariness
5. **ID Procedures** - Lineups, show-ups, suggestiveness
6. **Charging/Procedure** - Brady, Giglio, speedy trial, jurisdiction
7. **Evidence** - Hearsay, expert testimony (Frye), ER 403/404(b)
8. **WA Defenses** - Necessity, duress, self-defense, entrapment

**Output:** Top 3 issues, suppression motions, dismissal potential, plea leverage, trial strategy, verdict prediction

---

## Workflow Examples

### Example 1: DUI Case with Discovery Packet
**Files:**
- State v Smith - Arrest Report.pdf
- State v Smith - Breath Test Results.pdf
- State v Smith - Dashcam Transcript.pdf
- State v Smith - BAC DataMaster Report.pdf

**In ChatGPT:**
```
Analyze DUI for this case
```

**Result:**
- Comprehensive analysis across all 4 files
- Prioritized suppression issues
- Motion recommendations
- Plea negotiation strategy

---

### Example 2: DOL Hearing
**Files:**
- Smith DOL Administrative File.pdf
- Smith Implied Consent Form.pdf

**In ChatGPT:**
```
Analyze DOL hearing for this case
```

**Result:**
- Four-issue DOL analysis
- Implied consent warnings compliance
- Hearing strategy
- IID vs. fight recommendation

---

### Example 3: Non-DUI Criminal Case
**Files:**
- Assault Investigation Report.pdf
- Witness Statements.pdf

**In ChatGPT:**
```
Analyze this criminal case
```

**Result:**
- 4th/5th Amendment issues
- Charging issues
- Evidence admissibility
- Defense strategy

---

## Privacy Guarantees

**What Gets Sanitized (Never Sent to ChatGPT):**
- Client names → `[PERSON_1]`
- Officer names → `[PERSON_2]`
- Case numbers → `[CASE_NUM_001]`
- Addresses → `[ADDRESS_001]`
- License plates → `[PLATE_001]`
- SSN → `[SSN_REDACTED]`
- DOB → `[REDACTED]`
- Phone numbers → `[PHONE_REDACTED]`

**What's Preserved:**
- BAC results
- Test times
- Legal citations
- Factual observations
- Washington case law

**Where Data Lives:**
- Original PDFs: `~/Library/CloudStorage/Dropbox/MCP Analysis/` (local)
- Sanitization maps: `~/atlas/data/legal_sanitization_maps/` (local)
- ChatGPT: Sanitized analysis only (conversation history)

---

## Tips

**Naming Convention:**
Organize files by case for easier batch processing:
- `Smith DUI - Arrest.pdf`
- `Smith DUI - Test.pdf`
- `Smith DUI - Discovery.pdf`

**Drop Multiple Cases:**
The server analyzes ALL PDFs in the folder. For multiple cases:
1. Analyze Case 1 → save analysis
2. Delete Case 1 files from folder
3. Drop Case 2 files
4. Analyze Case 2

**OCR Support:**
- Digital PDFs: Fast (~1 second/file)
- Scanned PDFs: Automatic OCR (~10-30 seconds/file)
- Works with both seamlessly

**Sanitization Maps:**
If you need to reference what `[PERSON_1]` refers to:
```bash
cat ~/atlas/data/legal_sanitization_maps/<uuid>.json
```

---

## Common Questions

**Q: Can I analyze just one file from a batch?**
A: Yes! Use the filename:
```
Analyze DUI for "Arrest Report.pdf"
```

**Q: Does it cite Washington case law?**
A: Yes! The prompts reference key WA cases (Prado, O'Neill, Ladson, etc.) and RCWs.

**Q: Can I save the analysis?**
A: Yes! Copy from ChatGPT or use ChatGPT's conversation history (searchable).

**Q: What if files have different naming?**
A: No problem - batch mode analyzes ALL PDFs regardless of naming.

**Q: Can I use this for both criminal and DOL on same case?**
A: Yes! Run both analyses:
```
Analyze DUI for this case
[Review criminal analysis]

Analyze DOL hearing for this case
[Review DOL hearing analysis]
```

---

## Troubleshooting

**"No files found"**
- Check: `~/Library/CloudStorage/Dropbox/MCP Analysis/`
- Verify files are PDFs
- Dropbox sync complete?

**"Failed to process"**
- Check PDF isn't password-protected
- Try opening PDF manually first
- OCR might take 30+ seconds for large scanned files

**Claude doesn't see tools**
- Restart Claude Desktop completely
- Check 🔌 icon shows "legal-analysis"
- Verify config: `~/Library/Application Support/Claude/claude_desktop_config.json`

---

**Documentation:** See [README.md](README.md) for full details
