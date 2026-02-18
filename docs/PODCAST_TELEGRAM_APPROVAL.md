# Podcast Paragraph-by-Paragraph Telegram Approval

## Overview

Instead of generating the entire episode audio at once, you can now approve each paragraph individually via Telegram. This saves credits on re-runs and prevents the whack-a-mole problem where fixing one section breaks another.

## Workflow

### 1. Start Telegram Approval Mode

After your script is approved, start the paragraph-by-paragraph workflow:

```bash
python tools/podcast/tts_synthesizer.py --telegram-approval --episode-id sololaw-030
```

This will:
- Split the script into paragraphs
- Generate paragraph 1
- Send it to Telegram with audio preview
- Wait for your approval

### 2. Review on Telegram

You'll receive:
- **Text message**: Paragraph number, word count, duration, preview text
- **Audio file**: The generated paragraph

Listen to the audio and reply to the message:

**Approval Commands:**
- `good` / `✓` / `ok` → Approve and move to next paragraph
- `redo` / `regenerate` → Regenerate this paragraph with different audio
- `stop` / `pause` → Pause workflow (resume later)

### 3. Auto-Progression

When you approve a paragraph:
- ✅ Marked as approved
- 🔄 Next paragraph is automatically generated
- 📱 Sent to Telegram for review

This continues until all paragraphs are reviewed.

### 4. Final Mix

When the last paragraph is approved:
- 🔗 All paragraphs are concatenated
- 🎵 Music bed is mixed in
- 📱 Final episode sent to Telegram
- 🎉 Ready to publish!

## Commands

### Check Status

```bash
python tools/podcast/paragraph_orchestrator.py --status sololaw-030
```

Shows:
- Total paragraphs
- How many approved
- Current paragraph being reviewed
- Duration of approved segments

### Resume Paused Workflow

```bash
python tools/podcast/paragraph_orchestrator.py --resume sololaw-030
```

If you paused or the workflow was interrupted, this picks up where it left off.

### Manually Finalize

```bash
python tools/podcast/paragraph_orchestrator.py --finalize sololaw-030
```

If all paragraphs are approved but the mix hasn't triggered, run this manually.

## Benefits

✅ **Cost Efficient**: Only regenerate the paragraphs that need fixing
✅ **Better Quality**: Catch issues immediately before generating more
✅ **No Compound Errors**: Fixing paragraph 3 won't affect paragraph 10
✅ **Review on Phone**: Listen and approve from anywhere
✅ **Resumable**: Can pause and come back later
✅ **State Tracked**: System remembers what's been approved

## State Management

State is stored in `data/podcast_paragraph_state.json`:

```json
{
  "sololaw-030": {
    "status": "awaiting_approval",
    "total_paragraphs": 15,
    "current_paragraph": 3,
    "paragraphs": {
      "0": {"status": "approved", "message_id": 12340, "duration": 12.5},
      "1": {"status": "approved", "message_id": 12341, "duration": 15.2},
      "2": {"status": "approved", "message_id": 12342, "duration": 18.1},
      "3": {"status": "pending", "message_id": 12343}
    }
  }
}
```

### Clear State

If you want to abandon a workflow and start over:

```bash
python tools/podcast/paragraph_approval_state.py clear sololaw-030
```

## Traditional Workflow (Still Available)

The old "generate entire episode at once" workflow still works:

```bash
python tools/podcast/tts_synthesizer.py --episode-id sololaw-030
```

This generates all paragraphs in one go, concatenates, and triggers mixing automatically. Use this when you're confident the script is perfect and just want the audio fast.

## When to Use Each Workflow

**Use Telegram Approval When:**
- First time generating audio for a new voice
- Script has complex pronunciations or technical terms
- You want to catch issues early
- Quality > speed

**Use Traditional Workflow When:**
- Script is polished and tested
- You've used this voice before and trust it
- Speed > iterative review
- You're regenerating an episode where you already fixed issues

## Cost Comparison

**Traditional Workflow:**
- First generation: ~$3-5
- Pronunciation error in paragraph 8: Regenerate entire episode ~$3-5
- Total: **$6-10**

**Telegram Approval:**
- Paragraphs 1-7: ~$2.50
- Paragraph 8 sounds wrong: Regenerate paragraph 8 only ~$0.50
- Paragraphs 9-15: ~$2.50
- Total: **$5.50**

Plus you catch issues earlier and have finer control.

## Integration with Telegram Bot

The paragraph approval workflow is fully integrated with the Telegram bot's podcast commands. The bot automatically detects replies to paragraph audio and handles approvals.

No need to run commands manually - just reply to the messages!

## Troubleshooting

### "No approval state found"

You haven't started the Telegram approval workflow yet. Run:
```bash
python tools/podcast/tts_synthesizer.py --telegram-approval --episode-id <episode_id>
```

### "Waiting for approval"

A paragraph is pending your reply in Telegram. Check your messages and reply with `good` or `redo`.

### "Paragraph generation failed"

Check the error message. Common issues:
- ElevenLabs API quota exceeded
- Network timeout
- Invalid episode ID

### Workflow Stuck

1. Check status: `python tools/podcast/paragraph_orchestrator.py --status <episode_id>`
2. If needed, clear and restart: `python tools/podcast/paragraph_approval_state.py clear <episode_id>`
3. Resume from paragraph 0

## Technical Details

**Scripts:**
- `tts_synthesizer.py` - Generates individual paragraphs (--telegram-approval mode)
- `paragraph_approval_state.py` - State manager (tracks approved/pending)
- `paragraph_orchestrator.py` - Handles final concatenation and mixing
- `bot.py` - Telegram reply handler for approvals/regenerations

**State File:** `data/podcast_paragraph_state.json`
**Paragraph Audio:** `data/podcast_episodes/<episode_id>/paragraphs/paragraph_NNN.mp3`
**Metadata:** `data/podcast_episodes/<episode_id>/paragraphs/paragraph_metadata.json`

After final mix, the state is cleaned up automatically.
