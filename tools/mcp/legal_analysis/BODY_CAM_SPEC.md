# Body Camera Integration Specification

## Overview

Integrate body camera video analysis into the Legal Analysis MCP server to provide comprehensive evidence review for DUI/criminal defense cases.

## Phase 1: Audio Transcription (MVP)

### Features

1. **Video File Detection**
   - Accept `.mp4`, `.mov`, `.avi` formats in drop folder
   - Detect video files alongside PDFs

2. **Audio Extraction**
   - Use `ffmpeg` to extract audio track
   - Convert to WAV for Whisper processing

3. **Transcription**
   - Use Whisper (OpenAI API or local model)
   - Preserve timestamps for timeline
   - Speaker diarization if possible (officer vs defendant)

4. **Sanitization**
   - Apply same regex patterns to transcript
   - Redact names, case numbers, addresses mentioned verbally
   - Preserve legal terminology and observations

5. **Legal Analysis**
   - Miranda compliance check
   - Voluntary statement analysis
   - Officer observation timeline
   - Field sobriety test instructions compliance

### Technical Stack

```python
# Dependencies to add to requirements.txt
openai-whisper>=20231117
ffmpeg-python>=0.2.0
pydub>=0.25.0  # audio manipulation
```

### MCP Tool Definition

```python
Tool(
    name="analyze_body_cam_audio",
    description="Transcribe and analyze body camera audio for legal issues - Miranda warnings, voluntary statements, field sobriety test instructions, officer observations",
    inputSchema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of video file (.mp4, .mov, .avi)"
            },
            "segments": {
                "type": "array",
                "description": "Optional: specific time segments to analyze (e.g., [{'start': '00:02:30', 'end': '00:05:00', 'label': 'Initial stop'}])",
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "label": {"type": "string"}
                    }
                }
            }
        },
        "required": ["filename"]
    }
)
```

### Output Format

```
BODY CAMERA AUDIO TRANSCRIPT
File: [CASE_NUM_001]_bodycam.mp4
Duration: 18:34
Transcription Quality: 94%

TIMELINE:

[00:00:15] OFFICER: [PERSON_2]
"[PERSON_1], I'm stopping you for weaving within your lane."

[00:00:32] DEFENDANT: [PERSON_1]
"I was just trying to avoid the pothole."

[00:02:15] OFFICER: [PERSON_2]
"I'm going to administer some field sobriety tests. Have you consumed any alcohol tonight?"

[00:02:22] DEFENDANT: [PERSON_1]
"I had two beers about an hour ago."

[00:05:40] OFFICER: [PERSON_2]
"I'm placing you under arrest for DUI. You have the right to remain silent..."

LEGAL ISSUES IDENTIFIED:

1. **Miranda Warnings** [00:05:40]
   ✅ Given at time of arrest
   ✅ Complete advisement captured
   ⚠️  No explicit acknowledgment by [PERSON_1]

2. **Voluntary Statements** [00:02:22]
   ⚠️  Statement about alcohol consumption made BEFORE Miranda
   → May be admissible as spontaneous statement
   → Check State v. statements case law

3. **Field Sobriety Test Instructions**
   [Detailed analysis of instructions given vs. NHTSA standards]

4. **Stop Justification** [00:00:15]
   Officer stated "weaving within lane"
   → Analyze under State v. Prado standard
```

## Phase 2: Visual Analysis (Future)

### Features

1. **Key Frame Extraction**
   - Extract frames at user-marked timestamps
   - OR automatic frame extraction (1 per 30 seconds)

2. **Vision Model Analysis**
   - GPT-4V or Claude with vision
   - Describe physical actions, demeanor, environmental conditions
   - Identify field sobriety test performance

3. **Privacy-Preserving Options**
   - Local vision models (no API calls)
   - OR frame descriptions without face recognition
   - Map person placeholders to blurred regions

### Visual Analysis Output

```
[00:02:45] VISUAL OBSERVATION:
Scene: Roadside, nighttime, well-lit by patrol car lights
Officer: [PERSON_2] standing 6 feet from vehicle
Defendant: [PERSON_1] standing next to driver's door
- Posture: Leaning slightly on vehicle
- Actions: Fumbling with wallet
- Environmental: Dry pavement, no visible hazards
- Equipment: PBT device visible in officer's hand

[00:03:30] FIELD SOBRIETY TEST - Horizontal Gaze Nystagmus
Compliance with NHTSA protocol:
✅ Officer positioned correctly
✅ Stimulus held at proper distance
⚠️  Stimulus moved slightly too fast (per training standards)
Observations: [Detailed HGN performance]
```

## Phase 3: Multi-Source Timeline (Advanced)

Combine:
- Body cam transcript
- Police report (PDF)
- Breath test results (PDF)
- Dashcam (if separate video)

Generate unified timeline of events with cross-references.

## Cost Estimates

### Whisper Transcription
- **API**: $0.006/minute
  - 1-hour video: $0.36
  - 10 videos/month: $3.60/month
- **Local Whisper**: Free (slower, uses Mac CPU/GPU)

### Vision Analysis (Phase 2)
- **GPT-4V**: ~$0.01/image
  - 1 frame/30 seconds = 120 frames/hour
  - 120 frames × $0.01 = $1.20/hour video
- **Local Vision Model**: Free (much slower)

## Storage

- Videos stay in Dropbox folder (local)
- Transcripts saved to `data/body_cam_transcripts/`
- Sanitization maps include timestamp → speaker mapping
- Never upload video to AI services (only audio or frame descriptions)

## Privacy Safeguards

1. **Audio Only (Phase 1)**
   - No faces sent to AI
   - Voice → text transcription
   - Text sanitization (same as PDFs)

2. **Visual (Phase 2)**
   - Option A: Local processing only
   - Option B: Describe scenes without face recognition
   - Option C: User confirms before sending any frames

3. **Mapping File**
   - Links sanitized placeholders to real names/times
   - Stays local, never transmitted
   - Format: `{timestamp: "00:02:30", speaker: "PERSON_1", original: "[REDACTED]"}`

## Implementation Checklist

### Phase 1 (Audio - 2-3 hours)
- [ ] Install ffmpeg, whisper dependencies
- [ ] Add video file detection to MCP server
- [ ] Implement audio extraction
- [ ] Implement Whisper transcription with timestamps
- [ ] Apply sanitization to transcript
- [ ] Create body cam analysis hardprompt
- [ ] Test with sample body cam video
- [ ] Update documentation

### Phase 2 (Visual - 4-6 hours)
- [ ] Implement key frame extraction
- [ ] Choose vision model (GPT-4V vs local)
- [ ] Implement frame analysis
- [ ] Combine audio + visual timeline
- [ ] Privacy review and safeguards
- [ ] Test with sample body cam video

### Phase 3 (Multi-source - 4-6 hours)
- [ ] Build unified timeline merger
- [ ] Cross-reference engine (match times across sources)
- [ ] Conflict detection (discrepancies between sources)
- [ ] Enhanced analysis prompts

## Sample Commands

```
# Phase 1 - Audio only
"Analyze the body cam audio for Miranda compliance"
"Transcribe officer-defendant conversation from bodycam.mp4"

# Phase 2 - Audio + Visual
"Analyze the field sobriety tests in the body cam video"
"Review the HGN test performance from bodycam.mp4 at 00:03:30"

# Phase 3 - Multi-source
"Generate a complete timeline from the body cam, police report, and breath test results"
```

## Washington-Specific Legal Analysis

Body cam analysis should check:

1. **Miranda (State v. Mitchell)**
   - When given (custody analysis)
   - Completeness of warnings
   - Invocation by defendant

2. **Field Sobriety Tests (State v. Baity)**
   - NHTSA protocol compliance
   - Officer training/certification
   - Environmental conditions

3. **Statements (State v. Braun)**
   - Voluntary vs. custodial
   - Before vs. after Miranda
   - Spontaneous vs. interrogation-induced

4. **Stop Justification (State v. Prado)**
   - Reasonable suspicion articulated
   - Observable facts vs. hunches
   - Duration and scope

## Next Steps

1. Decide: Local Whisper vs API?
2. Decide: Phase 1 only or include Phase 2?
3. Estimate monthly usage (# of videos)
4. Test with sample body cam video
5. Build Phase 1 implementation
