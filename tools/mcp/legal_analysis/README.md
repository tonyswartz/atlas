# Legal Case Analysis MCP Server

**Privacy-first legal case analysis** - Sanitizes client data locally before sending to ChatGPT for analysis.

## What This Does

1. **Reads case files** from your Dropbox (local files only)
2. **Sanitizes PII** - removes client names, case numbers, addresses, etc.
3. **Provides sanitized text** to ChatGPT for legal analysis
4. **Stores mapping locally** - you can reference what was redacted, but ChatGPT never sees it

**Key Privacy Features:**
- All file I/O happens locally
- Sanitization happens before anything reaches ChatGPT's servers
- Original identities stored in local JSON files (never sent to API)
- Works with ChatGPT desktop app (conversations saved in ChatGPT for reference)

## Installation

### 1. Install Dependencies

```bash
cd /Users/printer/atlas/tools/mcp/legal_analysis

# Install Python packages
pip install -r requirements.txt

# Download spaCy language model for entity recognition
python -m spacy download en_core_web_sm
```

### 2. Configure Case Files Directory

By default, the server looks for case files in:
```
~/Library/CloudStorage/Dropbox/Legal Cases
```

To change this, edit `server.py` line 47:
```python
CASE_FILES_DIR = Path.home() / "Library/CloudStorage/Dropbox/Legal Cases"
```

### 3. Configure ChatGPT Desktop

Add this to ChatGPT's MCP configuration file:

**macOS:** `~/Library/Application Support/ChatGPT/config.json`

```json
{
  "mcpServers": {
    "legal-analysis": {
      "command": "python3",
      "args": ["/Users/printer/atlas/tools/mcp/legal_analysis/server.py"],
      "env": {}
    }
  }
}
```

### 4. Restart ChatGPT Desktop

Quit and reopen ChatGPT. You should see "legal-analysis" in the MCP servers list (⚡ icon).

## Usage

### In ChatGPT Desktop

**List available case files:**
```
Show me what case files are available
```

**Analyze a specific file:**
```
Analyze "State v Smith DUI.pdf" for suppression issues
```

**Read and sanitize without analysis:**
```
Read "Johnson Arrest Report.pdf" and show me the sanitized version
```

**Breath test analysis:**
```
Analyze "DUI Breath Test.pdf" for breath test compliance issues
```

**Probable cause analysis:**
```
Analyze "Smith Arrest.pdf" for probable cause
```

### Tools Available

| Tool | Purpose |
|------|---------|
| `list_case_files` | List PDFs in your case files directory |
| `read_case_sanitized` | Read and sanitize any case file |
| `analyze_suppression_issues` | 4th Amendment / suppression analysis |
| `analyze_breath_test` | Breath/blood test compliance |
| `analyze_probable_cause` | Probable cause analysis |

## What Gets Sanitized

**Personal Information:**
- Client names → `[PERSON_1]`, `[PERSON_2]`
- Locations → `[LOCATION_1]`, `[LOCATION_2]`
- Organizations → `[ORG_1]`, `[ORG_2]`

**Case-Specific:**
- Case numbers (CR-2024-12345) → `[CASE_NUM_001]`
- License plates → `[PLATE_001]`
- Phone numbers → `[PHONE_REDACTED]`
- SSN → `[SSN_REDACTED]`
- Dates of birth → `[REDACTED]`
- Street addresses → `[ADDRESS_001]`

**What's NOT Sanitized:**
- Legal terminology
- Statutory citations
- Case law citations
- Procedural dates (arrest time, test time)
- BAC values
- Test results
- Facts relevant to legal analysis

## Where Data Lives

**Local (Never Leaves Your Machine):**
- Original PDF files: `~/Library/CloudStorage/Dropbox/Legal Cases`
- Sanitization mappings: `~/atlas/data/legal_sanitization_maps/`
  - These JSON files let you reference what was redacted
  - Format: `{file_hash}_{timestamp}.json`

**ChatGPT (Sanitized Only):**
- Sanitized text with placeholders
- ChatGPT's analysis
- Conversation history (you can search past analyses)

## Example Workflow

1. **Save case file** to `~/Library/CloudStorage/Dropbox/Legal Cases/State v Smith.pdf`

2. **In ChatGPT:**
   ```
   Analyze "State v Smith.pdf" for suppression issues
   ```

3. **MCP server does:**
   - Reads PDF from local Dropbox
   - Extracts text
   - Sanitizes: "John Smith" → "[PERSON_1]"
   - Saves mapping to `data/legal_sanitization_maps/abc12345_20260219_143022.json`
   - Returns sanitized text to ChatGPT

4. **ChatGPT analyzes:**
   - Reviews sanitized text
   - Identifies issues (reasonable suspicion, probable cause, etc.)
   - Provides analysis referencing placeholders

5. **You review:**
   - Analysis in ChatGPT (saved in conversation history)
   - If needed, check sanitization map to see what `[PERSON_1]` refers to

## Troubleshooting

**"No files found"**
- Check that `CASE_FILES_DIR` in `server.py` points to your case files
- Verify files are PDF format
- Try: `list_case_files` to see what's visible

**"spaCy model not found" or spaCy compatibility issues**

If you're on Python 3.14+, spaCy may not be compatible yet. **This is fine!** The server will automatically fall back to regex-only sanitization, which is robust and catches:
- Case numbers, SSN, phone numbers, DOB
- License plates, addresses
- Case captions ("State v. Smith")
- Organizations in standard patterns

If you want AI-based entity recognition (optional):
- Wait for spaCy to support Python 3.14, or
- Use Python 3.13 or earlier

**To check if spaCy loaded:**
Look for "INFO: spaCy loaded successfully" when the server starts.
If you see "WARNING: using regex-only sanitization" - **that's okay**, regex is very effective.

**ChatGPT doesn't see the server**
- Check `config.json` path is correct
- Verify JSON syntax is valid
- Restart ChatGPT completely
- Check ChatGPT's MCP settings (⚡ icon)

**Over-sanitization**
- If too much is redacted, edit regex patterns in `server.py`
- The `_is_legal_citation()` method prevents redacting case citations
- You can adjust what gets sanitized vs. what passes through

## Security Notes

✅ **This approach is safe for client confidentiality:**
- Sanitization happens before any network call
- OpenAI never receives client names, case numbers, or PII
- Mapping files stay on your machine
- You control what directory is monitored

⚠️ **Remember:**
- ChatGPT stores conversation history on OpenAI's servers
- While sanitized, fact patterns might still be sensitive
- Use your professional judgment about what to analyze
- Don't put the sanitization mapping files in cloud storage

## Customization

**Add more sanitization rules:**
Edit the `sanitize_text()` method in `server.py` to add regex patterns.

**Change analysis prompts:**
Edit the tool implementations (e.g., `analyze_suppression_issues`) to customize what ChatGPT is asked to analyze.

**Add new analysis types:**
Copy one of the `analyze_*` tools and modify the prompt for your specific needs (e.g., sentencing analysis, discovery review, etc.).

## Future Enhancements

Potential additions:
- [ ] Batch analysis (multiple files at once)
- [ ] Export analysis to Obsidian vault
- [ ] Integration with LegalKanban (link analysis to cases)
- [ ] Local LLM option (100% offline analysis)
- [ ] OCR support for scanned documents
- [ ] Configurable sanitization levels (minimal/moderate/maximum)

## Support

Issues or questions:
1. Check [docs/MCP_SERVERS.md](../../../docs/MCP_SERVERS.md) for general MCP troubleshooting
2. Review ChatGPT's MCP documentation
3. Check server logs (ChatGPT shows errors in the MCP panel)
