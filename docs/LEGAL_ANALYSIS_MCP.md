# Legal Case Analysis with ChatGPT + Local MCP Server

## Overview

This system lets you analyze legal case files using ChatGPT while **keeping all client data local**.

**The Problem:**
- ChatGPT is excellent for legal analysis (finding suppression issues, probable cause problems, etc.)
- But you can't send files with client names, case numbers, PII to ChatGPT's servers
- Manual sanitization is time-consuming and error-prone

**The Solution:**
- **Local MCP server** reads files from your Dropbox
- **Sanitizes PII** before sending to ChatGPT (client names → placeholders)
- **Stores mapping locally** so you can reference what was redacted
- **ChatGPT analyzes** sanitized text and saves analysis in its conversation history

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Your Machine (Local)                                   │
│                                                         │
│  Case Files (Dropbox)                                  │
│       ↓                                                 │
│  MCP Server (atlas/tools/mcp/legal_analysis/)         │
│    - Reads PDF                                         │
│    - Extracts text                                     │
│    - Sanitizes PII (names, case #s, addresses)        │
│    - Saves mapping to data/legal_sanitization_maps/   │
│       ↓                                                 │
│  Sanitized text sent to ↓                              │
└─────────────────────────┼───────────────────────────────┘
                          ↓
                    ChatGPT API
                          ↓
┌─────────────────────────┼───────────────────────────────┐
│  ChatGPT Desktop App                                    │
│                                                         │
│  - Receives sanitized text only                        │
│  - Performs legal analysis                             │
│  - Saves analysis in conversation history              │
│  - You can search/reference past analyses              │
└─────────────────────────────────────────────────────────┘
```

**Key Privacy Protection:**
- Original PDFs never leave your machine
- Sanitization happens locally before any API call
- OpenAI only sees placeholders like `[PERSON_1]`, `[CASE_NUM_001]`
- Mapping of placeholders to real names stays on your machine

## Installation

See [tools/mcp/legal_analysis/README.md](../tools/mcp/legal_analysis/README.md) for full setup.

**Quick Start:**
```bash
# 1. Install dependencies
cd /Users/printer/atlas/tools/mcp/legal_analysis
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 2. Configure ChatGPT
# Add to: ~/Library/Application Support/ChatGPT/config.json
{
  "mcpServers": {
    "legal-analysis": {
      "command": "python3",
      "args": ["/Users/printer/atlas/tools/mcp/legal_analysis/server.py"]
    }
  }
}

# 3. Restart ChatGPT Desktop
```

## Usage Examples

### Example 1: Suppression Analysis

**You:** "Analyze 'State v Johnson DUI.pdf' for suppression issues"

**MCP Server does:**
1. Reads `/Users/printer/Library/CloudStorage/Dropbox/Legal Cases/State v Johnson DUI.pdf`
2. Extracts text from PDF
3. Sanitizes:
   - "Michael Johnson" → `[PERSON_1]`
   - "Officer Williams" → `[PERSON_2]`
   - "CR-2024-12345" → `[CASE_NUM_001]`
   - "123 Oak Street" → `[ADDRESS_001]`
4. Saves mapping to `data/legal_sanitization_maps/{hash}_{timestamp}.json`
5. Sends sanitized text + analysis prompt to ChatGPT

**ChatGPT responds:**
```
SUPPRESSION ANALYSIS

1. Reasonable Suspicion for Stop
   ✗ ISSUE FOUND

   Facts: Officer [PERSON_2] observed [PERSON_1]'s vehicle "weaving
   within lane" but never crossing lane markers. No traffic violations
   observed.

   Legal Basis: Mere weaving within a lane, without more, does not
   establish reasonable suspicion. State v. Prado, 174 Wn.2d 258 (2012).

   Likelihood of Success: HIGH - Prado directly on point.

2. Probable Cause for Arrest
   ? MARGINAL

   Facts: [PERSON_1] admitted to "two beers," odor of alcohol,
   bloodshot eyes. Refused field sobriety tests. No PBT.

   Legal Basis: Odor + admission + refusal to perform tests may be
   sufficient, but case law is split...
```

### Example 2: Breath Test Analysis

**You:** "Analyze 'Smith Breath Test.pdf' for compliance issues"

**ChatGPT responds:**
```
BREATH TEST COMPLIANCE ANALYSIS

1. Observation Period ✓ COMPLIANT
   Facts: Officer [PERSON_3] observed [PERSON_1] continuously from
   21:15 to 21:30 (15 minutes). No eating, drinking, smoking, or
   regurgitation observed.

2. Operator Certification ✗ ISSUE FOUND
   Facts: Certificate shows expiration date of [DATE]. Test conducted
   on [LATER_DATE].

   Suppression Potential: HIGH - Expired certification violates
   WAC 448-14-020...
```

### Example 3: Just Read and Sanitize

**You:** "Read 'Arrest Report - Jones.pdf' and show me the sanitized version"

**ChatGPT shows:**
```
SANITIZED CASE FILE: Arrest Report - Jones.pdf
(Original identities stored locally with UUID: a1b2c3d4_20260219_143022)

On [DATE_REDACTED], at approximately 22:45 hours, I, Officer [PERSON_1],
observed a vehicle bearing license plate [PLATE_001] traveling northbound
on [LOCATION_1] Highway...

[PERSON_2] stated that [PERSON_2] had consumed "a couple drinks" at
[ORG_1] bar located at [ADDRESS_001]...

---
Note: All client names, case numbers, and PII have been redacted.
```

You can then ask follow-up questions about the sanitized text.

## What Gets Sanitized

| Type | Example | Placeholder |
|------|---------|-------------|
| Person names | "John Smith" | `[PERSON_1]` |
| Locations | "Seattle" | `[LOCATION_1]` |
| Organizations | "King County Sheriff" | `[ORG_1]` |
| Case numbers | "CR-2024-12345" | `[CASE_NUM_001]` |
| License plates | "ABC1234" | `[PLATE_001]` |
| Phone numbers | "(555) 123-4567" | `[PHONE_REDACTED]` |
| SSN | "123-45-6789" | `[SSN_REDACTED]` |
| DOB | "DOB 1/1/1980" | `DOB [REDACTED]` |
| Addresses | "123 Main Street" | `[ADDRESS_001]` |

**What's preserved:**
- BAC results ("0.15")
- Test times ("21:30 hours")
- Legal citations ("RCW 46.61.502")
- Case law ("State v. Prado")
- Factual observations (weaving, odor, speech)

## Benefits of This Approach

✅ **Privacy-First**
- Client confidentiality maintained
- Professional responsibility obligations met
- No raw PII sent to third parties

✅ **Efficient**
- Faster than manual sanitization
- Consistent redaction (no human error)
- Reusable for multiple analyses

✅ **Powerful**
- ChatGPT's legal reasoning on sanitized facts
- Can search past analyses in ChatGPT history
- Can ask follow-up questions

✅ **Auditable**
- Sanitization mappings stored locally
- You can verify what was redacted
- Reproducible process

## Integration with Existing Workflows

### With LegalKanban (Future)
- Link analysis to case records
- Auto-file analysis in case folder
- Track which cases have been analyzed

### With Obsidian (Future)
- Export ChatGPT analysis to case note
- Link to original file
- Include in case research

### With Telegram Bot (Future)
- "Analyze the Smith file" → bot calls MCP → returns link to ChatGPT conversation
- Get notifications when analysis is complete

## Troubleshooting

**ChatGPT doesn't show the MCP server**
1. Check config file path: `~/Library/Application Support/ChatGPT/config.json`
2. Verify JSON syntax is valid
3. Restart ChatGPT completely (quit, not just close window)
4. Look for ⚡ icon in ChatGPT to see MCP status

**"No files found"**
1. Check `CASE_FILES_DIR` in `server.py` points to your Dropbox case files folder
2. Verify files are `.pdf` format
3. Try: "List case files" to see what's visible

**Over-sanitization (too much redacted)**
1. Edit `sanitize_text()` in `server.py`
2. Adjust regex patterns for your jurisdiction
3. The `_is_legal_citation()` function prevents redacting case cites

**Under-sanitization (PII leaking)**
1. Check sanitization map to see what was caught
2. Add regex patterns for jurisdiction-specific formats
3. Consider running test cases to verify

## Advanced: Customization

### Add New Analysis Type

Copy an existing analysis tool and modify the prompt:

```python
@app.call_tool()
async def call_tool(name: str, arguments: Any):
    # ... existing tools ...

    elif name == "analyze_sentencing":
        filename = arguments["filename"]
        result = await call_tool("read_case_sanitized", {"filename": filename})
        sanitized_text = result[0].text

        prompt = (
            f"{sanitized_text}\n\n"
            f"**ANALYSIS REQUEST: Sentencing Issues**\n\n"
            f"Please analyze for sentencing mitigation:\n"
            f"1. Criminal history issues\n"
            f"2. Mitigating circumstances\n"
            f"3. Alternative sentencing options\n"
            # ... etc ...
        )

        return [TextContent(type="text", text=prompt)]
```

Then add the tool to `list_tools()`.

### Adjust Sanitization Aggressiveness

Edit `CaseSanitizer.sanitize_text()`:

```python
# For MINIMAL sanitization (just names/case numbers):
# Comment out address, phone, DOB patterns

# For MAXIMUM sanitization (all dates, all locations):
# Add more aggressive patterns
```

### Change Case Files Directory

Edit line 47 in `server.py`:

```python
CASE_FILES_DIR = Path("/path/to/your/case/files")
```

## Security Considerations

**Safe for client confidentiality:**
- ✅ Sanitization happens before network call
- ✅ Mapping never leaves your machine
- ✅ ChatGPT only sees placeholders

**Consider:**
- ⚠️ ChatGPT stores conversation history on OpenAI servers
- ⚠️ Fact patterns might still be identifiable even when sanitized
- ⚠️ Use professional judgment about what to analyze
- ⚠️ Check your jurisdiction's ethics rules about AI tools

**Best practices:**
- Don't put sanitization maps in cloud storage
- Review sanitized text before complex analyses
- Delete ChatGPT conversations after case concludes
- Document AI tool use in case file
- Consider ChatGPT Teams for better data control

## Future Enhancements

Possible additions:
- [ ] Batch processing (analyze multiple files)
- [ ] Local LLM option (Ollama) for 100% offline analysis
- [ ] OCR for scanned documents
- [ ] Export to Obsidian/LegalKanban
- [ ] Configurable sanitization levels
- [ ] Client intake form sanitization
- [ ] Discovery document sanitization
- [ ] Automated case research integration

## Related Documentation

- [MCP Server Setup](MCP_SERVERS.md)
- [LegalKanban Integration](LEGALKANBAN.md)
- [Privacy & Security](PRIVACY_SECURITY.md)
