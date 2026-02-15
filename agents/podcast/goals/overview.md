# Podcast Agent - Overview

## Purpose

The Podcast Agent automates end-to-end podcast production for three shows:
- **Explore with Tony** (Travel) - Monday prompts, Wednesday publish
- **Solo Law Club** (Solo Lawyers) - Wednesday prompts, Monday publish
- **832 Weekends** (Parenting) - Friday prompts, Friday publish

## Workflow

```
Weekly Prompt → Idea Collection → Script Generation → Approval →
TTS Synthesis → Audio Mixing → Ready to Publish
```

### Stage 1: Weekly Prompt
- **When**: Mon/Wed/Fri 5 PM (per podcast schedule)
- **Tool**: `tools/podcast/weekly_prompt.py`
- **Action**: Sends Telegram message asking for episode ideas
- **Scheduling**: Launchd (3 separate jobs)

### Stage 2: Idea Collection
- **When**: User replies to prompt
- **Tool**: `tools/podcast/idea_processor.py`
- **Action**: Creates episode directory, triggers script generation
- **Manual**: `python tools/podcast/idea_processor.py --podcast explore --idea "My idea"`

### Stage 3: Script Generation
- **When**: Triggered by idea_processor.py
- **Tool**: `tools/podcast/script_generator.py`
- **Action**:
  - Loads hardprompt for podcast
  - Calls MiniMax-M2.5
  - Validates script (word count)
  - Sends preview to Telegram
- **Output**: `script_draft.md`

### Stage 4: Script Approval
- **When**: User approves script
- **Tool**: `tools/podcast/script_approver.py`
- **Action**:
  - Polls every 30 min for approvals
  - Checks for `.approved` file marker or state.json flag
  - Copies draft → approved
  - Triggers TTS
- **Manual approval**: `touch data/podcast_episodes/{episode_id}/.approved`

### Stage 5: TTS Synthesis
- **When**: After script approval
- **Tool**: `tools/podcast/tts_synthesizer.py`
- **Action**:
  - Calls ElevenLabs API with user's voice clone
  - Saves `voice_raw.mp3`
  - Calculates duration
  - Triggers audio mixing
- **Output**: `voice_raw.mp3`

### Stage 6: Audio Mixing
- **When**: After TTS complete
- **Tool**: `tools/podcast/audio_mixer.py`
- **Action**:
  - Loads music bed from config
  - Uses ffmpeg to overlay music (10% volume, -20dB)
  - Adds fade in/out
  - Sends final audio to Telegram
- **Output**: `mixed_final.mp3`

### Stage 7: Manual Publishing
- **When**: User ready to publish
- **Action**: User uploads `mixed_final.mp3` to Spotify Creators (Anchor.fm)
- **Mark complete**: `python tools/podcast/episode_manager.py --episode-id {id} --mark-published`

## Configuration

**File**: `agents/podcast/args/podcast.yaml`

Key settings:
- `voice_id`: ElevenLabs voice clone ID (per podcast)
- `music_bed`: Path to background music file
- `prompt_day`: Weekday for weekly prompt (0=Mon, 6=Sun)
- `target_words_min/max`: Script length constraints

## Commands

### Create Episode Manually
```bash
python tools/podcast/idea_processor.py \
  --podcast explore \
  --idea "Hiking the Tour du Mont Blanc"
```

### Check Episode Status
```bash
python tools/podcast/episode_manager.py --action list
python tools/podcast/episode_manager.py --episode-id 20260210-170000-explore
```

### Approve Script
```bash
# Method 1: File marker
touch data/podcast_episodes/20260210-170000-explore/.approved

# Method 2: Manual trigger
python tools/podcast/script_approver.py --episode-id 20260210-170000-explore
```

### Retry Stage
```bash
python tools/podcast/episode_manager.py \
  --episode-id 20260210-170000-explore \
  --retry script  # or tts, mix
```

### Test Components
```bash
# Test script generation
python tools/podcast/script_generator.py \
  --test \
  --podcast explore \
  --idea "Testing script generation"

# Test TTS
python tools/podcast/tts_synthesizer.py \
  --test \
  --text "Testing voice synthesis"

# Test audio mixing
python tools/podcast/audio_mixer.py \
  --test \
  --voice voice.mp3 \
  --music audio/music_beds/explore_upbeat.mp3
```

## State Management

Each episode has:
- **Directory**: `data/podcast_episodes/{episode_id}/`
- **State file**: `state.json` (current status, timestamps)
- **Database**: `data/podcast_catalog.db` (SQLite catalog)

**Episode status flow**:
```
idea_captured → script_draft → script_approved → voice_generated → mixed → published
```

## Scheduling

**Launchd jobs**:
- `com.atlas.podcast-prompt-explore.plist` - Mon 5 PM
- `com.atlas.podcast-prompt-sololaw.plist` - Wed 5 PM
- `com.atlas.podcast-prompt-832weekends.plist` - Fri 5 PM
- `com.atlas.podcast-script-poller.plist` - Every 30 min

**Install**:
```bash
cp launchd/com.atlas.podcast-*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-prompt-explore.plist
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-prompt-sololaw.plist
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-prompt-832weekends.plist
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-script-poller.plist
```

**Verify**:
```bash
launchctl list | grep podcast
```

## File Structure

```
data/podcast_episodes/{episode_id}/
├── state.json              # Episode metadata and status
├── idea.txt                # Original user idea
├── script_draft.md         # Generated script
├── script_approved.md      # Approved script
├── voice_raw.mp3           # TTS output
├── mixed_final.mp3         # Final audio with music bed
└── .approved               # Approval marker (optional)
```

## Credentials

**Required**:
- `MINIMAX` - For Claude script generation
- `ELEVENLABS_API_KEY` - For TTS voice synthesis
- `TELEGRAM_BOT_TOKEN` - For Telegram notifications

**Storage**:
```bash
envchain atlas --set MINIMAX
envchain atlas --set ELEVENLABS_API_KEY
envchain atlas --set TELEGRAM_BOT_TOKEN
```

## Cost Estimates

Per episode (5 min, ~750 words):
- Claude script generation: ~$0.15
- ElevenLabs TTS: ~$1.50
- **Total**: ~$1.65 per episode

Monthly (10 episodes):
- Explore with Tony: 2 episodes = $3.30
- Solo Law Club: 4 episodes = $6.60
- 832 Weekends: 4 episodes = $6.60
- **Total**: ~$16.50/month

Compare to Veed.io ($24/month) = **save ~$7.50/month** + eliminate manual editing

## Troubleshooting

### Script generation fails
- Check `MINIMAX` in envchain
- Verify hardprompt exists: `hardprompts/podcast_script_{podcast_name}.md`
- Check API rate limits

### TTS fails
- Check `ELEVENLABS_API_KEY` in envchain
- Verify voice ID in `agents/podcast/args/podcast.yaml`
- Check ElevenLabs account quota

### Audio mixing fails
- Verify ffmpeg installed: `which ffmpeg`
- Check music bed file exists
- Verify file permissions

### Approval not detected
- Verify `.approved` file created: `ls data/podcast_episodes/{episode_id}/`
- Check script_approver.py logs: `logs/podcast_script_poller.log`
- Manually trigger: `python tools/podcast/script_approver.py --episode-id {id}`

## Next Steps

1. **Set up voice clone** with ElevenLabs (Phase 0)
2. **Add voice IDs** to podcast.yaml
3. **Add music beds** to `audio/music_beds/`
4. **Test workflow** with one episode per podcast
5. **Install launchd jobs** for automation
6. **Monitor logs** for first week
