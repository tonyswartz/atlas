# Quick Setup Guide

**IMPORTANT: This MCP server is designed for Claude Desktop, not ChatGPT Desktop.**

ChatGPT Desktop requires HTTPS endpoints with OAuth (not local servers), while Claude Desktop supports local stdio-based MCP servers like this one.

## 1. Install Dependencies

```bash
cd /Users/printer/atlas/tools/mcp/legal_analysis

# Install Tesseract OCR (for scanned PDFs)
brew install tesseract

# Install Python packages
pip3 install --break-system-packages -r requirements.txt
```

**Note:** OCR support is now included! The server automatically handles:
- ✅ Digital PDFs (fast, ~1 second)
- ✅ Scanned PDFs (automatic OCR, ~10-30 seconds)

## 2. Drop Folder Created

The MCP server monitors:
```
~/Library/CloudStorage/Dropbox/MCP Analysis
```

**This folder was just created for you.**

Drop PDF files here when you want to analyze them. After ChatGPT completes the analysis, you can delete the files from this folder (they're temporary).

## 3. Configure Claude Desktop

Edit or create this file:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Add this content (or merge with existing config):
```json
{
  "mcpServers": {
    "legal-analysis": {
      "command": "python3",
      "args": ["/Users/printer/atlas/tools/mcp/legal_analysis/server.py"]
    }
  }
}
```

## 4. Restart Claude Desktop

Fully quit Claude Desktop app (not just close window) and reopen.

Look for the 🔌 icon at the bottom of the chat - you should see "legal-analysis" listed when you click it.

## 5. Test It

1. **Drop a test PDF** in `~/Library/CloudStorage/Dropbox/MCP Analysis/`

2. **In Claude Desktop, say:**
   ```
   List case files
   ```

   You should see your file listed.

3. **Analyze it:**
   ```
   Analyze "your-file.pdf" for suppression issues
   ```

   Claude will:
   - Call the MCP server
   - Server reads the PDF locally
   - Server sanitizes all PII
   - Server returns sanitized text
   - Claude analyzes and responds

4. **Check sanitization map:**
   ```bash
   ls ~/atlas/data/legal_sanitization_maps/
   cat ~/atlas/data/legal_sanitization_maps/<latest-file>.json
   ```

   This shows what was redacted (stays on your machine, never sent to OpenAI).

## Usage Examples

**List files:**
```
Show me what case files are available
```

**Quick read:**
```
Read "Smith DUI.pdf" and show me the sanitized version
```

**Suppression analysis:**
```
Analyze "Johnson Arrest.pdf" for 4th Amendment issues
```

**Breath test analysis:**
```
Analyze "Smith Breath Test.pdf" for compliance issues
```

**Probable cause analysis:**
```
Analyze "Arrest Report.pdf" for probable cause
```

## What Gets Sanitized

✅ **Removed (replaced with placeholders):**
- Client names → `[PERSON_1]`
- Officer names → `[PERSON_2]`
- Locations → `[LOCATION_1]`
- Organizations → `[ORG_1]`
- Case numbers → `[CASE_NUM_001]`
- License plates → `[PLATE_001]`
- Phone numbers → `[PHONE_REDACTED]`
- SSN → `[SSN_REDACTED]`
- Dates of birth → `[REDACTED]`
- Street addresses → `[ADDRESS_001]`

✅ **Preserved (needed for analysis):**
- BAC results
- Test times/dates
- Legal citations
- Case law references
- Factual observations
- Statutory references

## Troubleshooting

**"No MCP servers found"**
- Check config.json path: `~/Library/Application Support/ChatGPT/config.json`
- Verify JSON syntax (use a validator)
- Restart ChatGPT completely

**"No files found"**
- Make sure files are in `~/Library/CloudStorage/Dropbox/MCP Analysis/`
- Files must be PDF format
- Check permissions on the folder

**"spaCy warnings" or compatibility issues**

If you see spaCy warnings (common on Python 3.14+), **don't worry!** The server automatically falls back to regex-only sanitization, which is very effective for legal documents.

**Regex sanitization catches:**
- ✅ Names in case captions ("State v. Smith")
- ✅ Case numbers (CR-2024-12345)
- ✅ SSN, phone numbers, DOB
- ✅ License plates, addresses
- ✅ Standard organization patterns

This is sufficient for most legal analysis needs.

**Want to change the drop folder?**
Edit line 49 in `server.py`:
```python
CASE_FILES_DIR = Path("/your/custom/path")
```

## Workflow

1. **Drop file** → `~/Library/CloudStorage/Dropbox/MCP Analysis/case.pdf`
2. **Analyze in ChatGPT** → "Analyze case.pdf for suppression issues"
3. **Review analysis** → ChatGPT provides detailed breakdown
4. **Reference sanitization** → Check `~/atlas/data/legal_sanitization_maps/` if needed
5. **Delete file** → Remove from MCP Analysis folder after you're done

## Privacy Notes

✅ **Safe:**
- All sanitization happens locally
- OpenAI never receives client names or case numbers
- Mapping files never leave your machine
- You control the drop folder

⚠️ **Consider:**
- ChatGPT conversation history is stored on OpenAI servers (sanitized)
- Fact patterns might still be identifiable even when sanitized
- Use professional judgment about what to analyze
- Check your jurisdiction's ethics rules

## Next Steps

See [docs/LEGAL_ANALYSIS_MCP.md](../../../docs/LEGAL_ANALYSIS_MCP.md) for:
- Advanced customization
- Adding new analysis types
- Adjusting sanitization rules
- Integration with LegalKanban/Obsidian
