# LegalKanban Integration Specification

## Goal

Analyze case files from LegalKanban case folders with full sanitization, storing results back in the case file structure.

## Architecture

```
Dropbox Case Folder Structure:
~/Dropbox/Cases/
  └── [Case Title]/
      ├── Discovery/
      │   ├── Police Report.pdf
      │   ├── Breath Test.pdf
      │   └── Body Cam Transcript.txt
      ├── Analysis/           # ← MCP stores sanitized analysis here
      │   ├── 2026-02-19_DUI_Criminal_Analysis.md
      │   └── 2026-02-20_DOL_Hearing_Analysis.md
      └── Pleadings/
```

## MCP Tool: `analyze_legalkanban_case`

### Input

```json
{
  "case_folder": "~/Dropbox/Cases/State v. Smith",
  "analysis_type": "dui_criminal",  // or "dui_dol", "general"
  "file_pattern": "Discovery/*.pdf"  // optional, defaults to all PDFs
}
```

### Process

1. **Find case files** matching pattern in case folder
2. **Extract and sanitize** all discovered files
   - PDFs → extract text → sanitize
   - Text files (body cam transcripts) → sanitize
   - DOCX → extract text → sanitize
3. **Combine** into unified case context
4. **Analyze** based on analysis_type (DUI criminal, DOL, etc.)
5. **Save sanitized analysis** to `Analysis/` subfolder
6. **Return** file path + summary

### Output

```markdown
# DUI Criminal Defense Analysis
**Case**: [CASE_NUM_001]
**Defendant**: [PERSON_1]
**Date**: 2026-02-19
**Files Analyzed**:
- Police Report.pdf
- Breath Test Results.pdf
- Body Cam Transcript.txt

---

## EXECUTIVE SUMMARY

[Sanitized analysis with placeholders...]

## SUPPRESSION ISSUES

### 1. Initial Stop - Reasonable Suspicion
[Analysis using [PERSON_1], [PERSON_2], etc.]

### 2. Probable Cause for Arrest
[...]

## MOTION STRATEGY
[...]

---

*Analysis generated via sanitized MCP server*
*Sanitization map: [UUID].json*
```

## Implementation

### 1. Add to MCP Server

```python
@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    # ... existing tools ...

    elif name == "analyze_legalkanban_case":
        case_folder = Path(arguments["case_folder"]).expanduser()
        analysis_type = arguments.get("analysis_type", "dui_criminal")
        file_pattern = arguments.get("file_pattern", "Discovery/*.pdf")

        # Find files
        files = sorted(case_folder.glob(file_pattern))
        if not files:
            return [TextContent(
                type="text",
                text=f"No files found matching {file_pattern} in {case_folder}"
            )]

        # Process each file
        all_text = []
        for file_path in files:
            if file_path.suffix == '.pdf':
                text = extract_pdf_text(file_path)
            elif file_path.suffix in ['.txt', '.md']:
                text = file_path.read_text()
            else:
                continue

            # Sanitize
            sanitizer = CaseSanitizer()
            sanitized, mapping = sanitizer.sanitize_text(text)
            all_text.append(f"=== {file_path.name} ===\n\n{sanitized}\n\n")

            # Save mapping
            save_sanitization_map(file_path, mapping)

        # Combine all sanitized text
        combined = "\n".join(all_text)

        # Get analysis prompt based on type
        if analysis_type == "dui_criminal":
            prompt = get_dui_criminal_prompt(combined)
        elif analysis_type == "dui_dol":
            prompt = get_dui_dol_prompt(combined)
        else:
            prompt = get_general_criminal_prompt(combined)

        # Save analysis to case folder
        analysis_dir = case_folder / "Analysis"
        analysis_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d")
        analysis_file = analysis_dir / f"{timestamp}_{analysis_type}_analysis.md"

        # Return prompt for Claude to complete
        return [TextContent(
            type="text",
            text=f"FILES ANALYZED (sanitized):\n\n{combined}\n\n{prompt}\n\n"
                 f"(Analysis will be saved to: {analysis_file})"
        )]
```

### 2. Tool Definition

```python
Tool(
    name="analyze_legalkanban_case",
    description="Analyze all case files from a LegalKanban case folder (Dropbox). Sanitizes all PII and generates comprehensive legal analysis stored in the case Analysis folder.",
    inputSchema={
        "type": "object",
        "properties": {
            "case_folder": {
                "type": "string",
                "description": "Path to case folder (e.g., '~/Dropbox/Cases/State v. Smith')"
            },
            "analysis_type": {
                "type": "string",
                "enum": ["dui_criminal", "dui_dol", "general_criminal"],
                "description": "Type of analysis to perform",
                "default": "dui_criminal"
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob pattern for files to analyze (default: 'Discovery/*.pdf')",
                "default": "Discovery/*.pdf"
            }
        },
        "required": ["case_folder"]
    }
)
```

## Usage Examples

### From Claude Desktop

```
Analyze the case at ~/Dropbox/Cases/State v. Smith for DUI criminal issues
```

```
Analyze all discovery files in ~/Dropbox/Cases/State v. Johnson for DOL hearing defenses
```

### From LegalKanban

If LegalKanban has UI integration:
1. Open case in LegalKanban
2. Click "Analyze Case Files" button
3. Select analysis type (DUI Criminal / DOL / General)
4. Launches Claude Desktop with pre-filled command
5. Analysis saved to case folder

## Benefits

1. **Privacy**: All sanitization happens locally
2. **Organization**: Analysis stored with case files
3. **Version Control**: Multiple analyses over time
4. **Accessibility**: Available in Dropbox, LegalKanban, Obsidian
5. **Portable**: Markdown format, readable anywhere

## Future Enhancements

### Phase 2: LegalKanban UI Integration

Add button to LegalKanban web UI:
```javascript
// LegalKanban frontend
<Button onClick={() => analyzeCase(case.id)}>
  Analyze Case Files
</Button>

function analyzeCase(caseId) {
  // Call local MCP HTTP server
  fetch('http://localhost:8000/analyze', {
    method: 'POST',
    body: JSON.stringify({
      case_id: caseId,
      analysis_type: 'dui_criminal'
    })
  })
  .then(res => res.json())
  .then(data => {
    // Display analysis in UI
    showAnalysis(data.sanitized_analysis);
  });
}
```

### Phase 3: Case Timeline Integration

Combine analysis with:
- Police report timeline
- Breath test times
- Body cam transcript timeline
- Court dates from LegalKanban

Generate unified timeline document.

## Security Notes

- All file processing happens locally
- Sanitization maps stored in `~/atlas/data/legal_sanitization_maps/`
- No case files uploaded to cloud AI services
- Analysis contains only sanitized placeholders
- Original files remain untouched in case folders

## Questions to Answer

1. **Where are your case folders stored?**
   - ~/Dropbox/Cases/[Case Title]/ ?
   - Different structure?

2. **Preferred analysis storage?**
   - Option 1: Dropbox case folder (recommended)
   - Option 2: New database table
   - Option 3: Obsidian vault

3. **Trigger mechanism?**
   - Manual: Claude Desktop command
   - Semi-auto: LegalKanban button → opens Claude
   - Auto: Watch folder, analyze on new files

4. **Analysis frequency?**
   - One-time per case?
   - Update when new discovery arrives?
   - On-demand when preparing motions?
