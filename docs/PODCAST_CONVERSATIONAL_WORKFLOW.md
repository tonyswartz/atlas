# Podcast Conversational Workflow

## Overview

The podcast system now supports **smart conversational interactions** via Telegram. You can manage entire podcast episodes through natural conversation.

## Supported Interactions

### 1. **Episode Creation** (Reply to Weekly Prompt)

**Prompt arrives automatically** (Mon/Wed/Fri 5 PM):
```
🎙️ Solo Law Club Episode Ideas
What would you like to talk about in the next episode?
```

**You reply with idea**:
```
Setting up WIP limits via Kanban...
```

**Bot automatically**:
- Creates episode with unique ID (e.g., `sololaw-030`)
- Generates script using GPT
- Sends script preview to Telegram
- Tracks message ID for follow-up

---

### 2. **Script Approval** (Reply to Script Preview)

**Bot sends preview**:
```
📄 Script ready for sololaw-030
[Script excerpt...]
```

**You can reply with**:

✅ **Simple approval**:
```
Approved
```
or `looks good`, `lgtm`, `go ahead`, `yes`, `proceed`

✅ **Approval with pronunciation fixes**:
```
Approved, fix: WIP=double-U-I-P, Kanban=Kahn-bahn
```

**Bot automatically**:
- Copies draft → approved
- Stores one-off pronunciation fixes
- Triggers TTS synthesis
- Mixes with background music
- Normalizes loudness to -16 LUFS
- Sends final MP3 to Telegram

---

### 3. **Regeneration** (Reply to Any Podcast Message)

**After manually editing the script in Obsidian**, reply to:
- The original prompt
- The script preview
- The final audio message

**You can say**:
```
Regenerate
```
or `redo`, `create new version`, `make new`, `i edited the script`, `new version`

✅ **Regenerate with pronunciation fixes**:
```
Regenerate, fix: attorney=uh-TUR-nee
```

**Bot automatically**:
- Reads your edited `script_approved.md` from Obsidian
- Applies pronunciation fixes
- Re-runs TTS synthesis
- Re-mixes audio
- Sends updated MP3

---

## Pronunciation System

### Three Approaches:

#### 1. **Permanent Dictionary** (Shared Across All Podcasts)
**File**: `Obsidian/Podcasts/Pronunciation Dictionary.md`

```markdown
## Dictionary

- WIP → whip
- Kanban → Kahn-bahn
- API → A-P-I
- voir dire → vwahr-DEER
```

**When to use**: Words you always want pronounced the same way.

---

#### 2. **Hardprompt Guidance** (Per-Podcast)
**File**: `hardprompts/podcast_script_sololaw.md`

Add natural language hints like:
```
Pronunciation notes:
- Say "W-I-P" as individual letters, not "whip"
- Pronounce "Kanban" as "Kahn-bahn"
```

**When to use**: Default guidance for script generation.

---

#### 3. **One-Off Fixes** (Per-Episode)
**Via Telegram approval/regeneration**:
```
Approved, fix: attorney=uh-TUR-nee, voir dire=vwahr-DEER
```

**When to use**: Weird words that appear once, no need to clutter dictionary.

---

## Message ID Tracking

The system tracks message IDs for intelligent reply detection:

```json
{
  "prompts": {
    "12345": {
      "podcast": "sololaw",
      "sent_at": "2026-02-12T17:00:00",
      "chat_id": "8241581699"
    }
  },
  "script_previews": {
    "12346": {
      "episode_id": "sololaw-030",
      "sent_at": "2026-02-12T17:15:00",
      "chat_id": "8241581699"
    }
  },
  "final_audio": {
    "12347": {
      "episode_id": "sololaw-030",
      "sent_at": "2026-02-12T17:30:00",
      "chat_id": "8241581699"
    }
  }
}
```

**Stored in**: `data/podcast_prompts.json`

---

## Example Complete Workflow

### Monday 5 PM:
**Bot**: 🎙️ Solo Law Club Episode Ideas...

**You**: Setting up WIP limits via Kanban boards...

**Bot**: ✅ Creating sololaw episode... Script generation in progress.

---

### 10 minutes later:
**Bot**: 📄 Script ready for sololaw-030 [preview]

**You**: Approved, fix: WIP=whip, Kanban=Kahn-bahn

**Bot**: 🎙️ sololaw-030 approved! Generating voice and mixing audio...

---

### 5 minutes later:
**Bot**: ✅ Solo Law Club - Episode Ready to Publish!
**Episode**: The Kanban Case Limit That Saved My Practice
**Duration**: 5:24
[MP3 attached with correct metadata]

---

### Later, after editing script in Obsidian:
**You** (replying to any previous message): Regenerate

**Bot**: 🔄 Regenerating sololaw-030... Reading your edited script and creating new audio.

---

### 5 minutes later:
**Bot**: ✅ Solo Law Club - Episode Ready to Publish!
[Updated MP3 with your edits]

---

## Tools Available to Telegram Bot

### `podcast_create_episode`
**Called**: When user replies to weekly prompt
**Parameters**:
- `podcast`: "explore" | "sololaw" | "832weekends"
- `idea`: Episode topic/outline

---

### `podcast_approve_script`
**Called**: When user approves script preview
**Parameters**:
- `episode_id`: e.g., "sololaw-030"
- `pronunciation_fixes` (optional): {"word": "pronunciation"}

---

### `podcast_regenerate_voice`
**Called**: When user requests regeneration after editing
**Parameters**:
- `episode_id`: e.g., "sololaw-030"
- `pronunciation_fixes` (optional): {"word": "pronunciation"}

---

## Detection Keywords

### Approval:
`approved`, `approve`, `looks good`, `lgtm`, `go ahead`, `yes`, `proceed`

### Regeneration:
`regenerate`, `redo`, `create new`, `make new`, `i edited`, `edited the script`, `new version`, `re-generate`, `re-synthesize`, `resynthesize`

---

## Technical Implementation

### Files Modified:

1. **tool_definitions.py**: Added `podcast_regenerate_voice` tool
2. **tool_runner.py**: Implemented `_podcast_regenerate_voice()`
3. **bot.py**: Enhanced `_handle_podcast_reply()` with smart detection
4. **audio_mixer.py**:
   - Updated `send_telegram()` to return message_id
   - Store final_audio message IDs in podcast_prompts.json
5. **pronunciation.py**: Core pronunciation processing logic
6. **tts_synthesizer.py**: Integrated pronunciation system

---

## Future Enhancements

Potential conversational commands:

- **Change title**: "Change title to 'Better Title'"
- **Use different music**: "Use upbeat music instead"
- **Adjust length**: "Make it shorter, target 3 minutes"
- **Change voice settings**: "Use slower speed, more stability"

The architecture is now extensible for adding more natural language commands.

---

## Troubleshooting

### "No approved script found"
- You tried to regenerate but haven't approved/edited the script yet
- **Fix**: Make sure `script_approved.md` exists in Obsidian episode folder

### "episode_id is required"
- Bot couldn't find episode context from your reply
- **Fix**: Reply directly to a podcast-related message (prompt, preview, or audio)

### Pronunciation fixes not applied
- **Check**: `data/podcast_prompts.json` → ensure your message was tracked
- **Check**: Pronunciation Dictionary.md syntax: `- Original → Phonetic`
- **Check**: One-off fix format: `fix: word=pronunciation, word2=pronunciation2`

---

*Last updated: 2026-02-12*
