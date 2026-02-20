#!/usr/bin/env python3
"""
Helper for processing raw body camera STT transcripts.
Adds speaker labels and structure to unformatted transcripts.
"""

import re
from pathlib import Path


def structure_raw_transcript(raw_text: str, use_ai: bool = False) -> str:
    """
    Convert raw STT transcript to structured format with speaker labels.

    Args:
        raw_text: Unformatted transcript text
        use_ai: If True, use AI for speaker diarization. If False, use heuristics.

    Returns:
        Structured transcript with [OFFICER] and [DEFENDANT] labels
    """

    if use_ai:
        return _ai_speaker_diarization(raw_text)
    else:
        return _heuristic_speaker_diarization(raw_text)


def _heuristic_speaker_diarization(raw_text: str) -> str:
    """
    Use heuristics to identify speakers in body cam transcript.

    Common patterns:
    - Officer phrases: "Deputy", "Officer", "Sheriff", "I'm placing you under arrest",
      "step out", "perform", "follow", "field sobriety"
    - Defendant phrases: Usually shorter responses, personal statements
    - Questions typically from officer
    """

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', raw_text)

    structured = []
    current_speaker = None
    officer_patterns = [
        r'\b(deputy|officer|trooper|sergeant|sgt|detective)\b',
        r'\bsheriff\b',
        r'\bplacing you under arrest\b',
        r'\bstep out\b',
        r'\bfield sobriety\b',
        r'\bprobable cause\b',
        r'\bmirandize\b',
        r'\bright to remain silent\b',
        r'\bperform.*test\b',
        r'\bfollow.*pen\b',
        r'\blive in\s+\w+\s+county\b',
        r'\bdriver\'?s license\b',
        r'\bregistration and insurance\b',
        r'\bwhere.*coming from\b',
        r'\bhow much.*drink\b',
    ]

    for sentence in sentences:
        if not sentence.strip():
            continue

        # Check if sentence matches officer patterns
        is_officer = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in officer_patterns)

        # Questions are usually from officer
        if '?' in sentence and not is_officer:
            # Could be clarification from defendant, but likely officer
            is_officer = True

        # Very short responses (<5 words) likely defendant
        word_count = len(sentence.split())
        if word_count < 5 and not is_officer:
            speaker = 'DEFENDANT'
        else:
            speaker = 'OFFICER' if is_officer else 'DEFENDANT'

        # Add speaker label if changed
        if speaker != current_speaker:
            structured.append(f"\n[{speaker}]:")
            current_speaker = speaker

        structured.append(sentence)

    return '\n'.join(structured)


def _ai_speaker_diarization(raw_text: str) -> str:
    """
    Use AI to identify speakers in transcript.
    This would call Claude/GPT to segment and label speakers.

    Prompt: "This is a body camera transcript from a traffic stop.
             Add speaker labels ([OFFICER] and [DEFENDANT]) to each statement.
             Officers typically ask questions, give instructions, and cite legal authority.
             Defendants typically give shorter responses and personal statements."
    """
    # TODO: Implement AI-based diarization if needed
    # For now, fall back to heuristics
    return _heuristic_speaker_diarization(raw_text)


def format_for_analysis(structured_transcript: str, case_context: str = "") -> str:
    """
    Format structured transcript for legal analysis.

    Args:
        structured_transcript: Transcript with speaker labels
        case_context: Optional context (e.g., "DUI traffic stop")

    Returns:
        Formatted transcript ready for MCP analysis
    """

    header = f"""BODY CAMERA TRANSCRIPT
{'='*50}
Context: {case_context if case_context else 'Traffic Stop / Field Investigation'}
Format: Structured from raw STT output
Note: Speaker labels added via analysis (not from original transcript)

TRANSCRIPT:
{'='*50}
"""

    return header + structured_transcript


def extract_key_moments(structured_transcript: str) -> dict:
    """
    Extract key legal moments from structured transcript.

    Returns dict with:
    - miranda_warning: Text of Miranda warnings if present
    - initial_contact: First exchange
    - field_tests: Field sobriety test instructions
    - statements: Defendant statements
    - arrest: Arrest language
    """

    key_moments = {
        'miranda_warning': None,
        'initial_contact': None,
        'field_tests': [],
        'statements': [],
        'arrest': None
    }

    # Find Miranda warning
    miranda_pattern = r'\[OFFICER\]:.*?(right to remain silent.*?attorney)'
    miranda_match = re.search(miranda_pattern, structured_transcript, re.IGNORECASE | re.DOTALL)
    if miranda_match:
        key_moments['miranda_warning'] = miranda_match.group(0)

    # Find initial contact (first 200 chars)
    key_moments['initial_contact'] = structured_transcript[:200]

    # Find field test instructions
    field_test_pattern = r'\[OFFICER\]:.*?(follow.*?pen|walk.*?line|stand.*?foot|alphabet|count)'
    for match in re.finditer(field_test_pattern, structured_transcript, re.IGNORECASE):
        key_moments['field_tests'].append(match.group(0))

    # Find defendant statements (for voluntary analysis)
    defendant_pattern = r'\[DEFENDANT\]:.*?(?=\[OFFICER\]|\Z)'
    for match in re.finditer(defendant_pattern, structured_transcript, re.DOTALL):
        statement = match.group(0).strip()
        if len(statement) > 20:  # Skip very short responses
            key_moments['statements'].append(statement)

    # Find arrest language
    arrest_pattern = r'\[OFFICER\]:.*?(plac.*?under arrest|arrest.*?for)'
    arrest_match = re.search(arrest_pattern, structured_transcript, re.IGNORECASE)
    if arrest_match:
        key_moments['arrest'] = arrest_match.group(0)

    return key_moments


if __name__ == '__main__':
    # Test with sample raw transcript
    sample = """
    Good evening I'm Deputy Garcia with Kittitas County Sheriff's Office. Hi. Do you know why I stopped you? No I don't. I observed you weaving within your lane. Oh I was trying to avoid a pothole. Have you consumed any alcohol tonight? I had two beers about an hour ago. I'm going to need you to step out of the vehicle. Can you perform some field sobriety tests for me? Sure. I'm going to have you follow this pen with just your eyes don't move your head. Okay. I'm placing you under arrest for DUI. You have the right to remain silent anything you say can and will be used against you in a court of law.
    """

    print("RAW TRANSCRIPT:")
    print(sample)
    print("\n" + "="*50 + "\n")

    structured = structure_raw_transcript(sample)
    print("STRUCTURED:")
    print(structured)
    print("\n" + "="*50 + "\n")

    formatted = format_for_analysis(structured, "DUI Traffic Stop")
    print("FORMATTED FOR ANALYSIS:")
    print(formatted)
    print("\n" + "="*50 + "\n")

    key_moments = extract_key_moments(structured)
    print("KEY MOMENTS:")
    for moment_type, content in key_moments.items():
        if content:
            print(f"\n{moment_type.upper()}:")
            if isinstance(content, list):
                for item in content:
                    print(f"  - {item[:100]}...")
            else:
                print(f"  {content[:200]}...")
