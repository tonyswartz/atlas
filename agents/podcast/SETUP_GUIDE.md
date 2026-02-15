# Podcast Agent - Setup Guide

## Prerequisites

- ElevenLabs account with voice clone (or Deepgram)
- MiniMax API key (for AI script generation)
- Telegram bot token
- Music bed files (background music for each podcast)
- ffmpeg installed (`brew install ffmpeg`)

## Phase 0: Voice Clone Setup

### Option 1: ElevenLabs (Recommended)

1. Sign up at [elevenlabs.io](https://elevenlabs.io)
2. Navigate to **Voice Lab**
3. Click **Add Voice** → **Instant Voice Cloning**
4. Upload 5-10 minutes of clear voice samples:
   - Different emotions (happy, serious, reflective)
   - Different contexts (storytelling, explaining, conversing)
   - High quality audio (no background noise)
5. Name your voice (e.g., "Tony Voice Clone")
6. Generate clone (takes ~10 minutes)
7. Copy the **Voice ID** from Voice Library
8. Add API key to envchain:
   ```bash
   envchain atlas --set ELEVENLABS_API_KEY
   ```

### Option 2: Deepgram

1. Sign up at [deepgram.com](https://deepgram.com)
2. Follow their voice cloning setup
3. Copy voice ID
4. Add API key to envchain:
   ```bash
   envchain atlas --set DEEPGRAM_API_KEY
   ```

## Phase 1: Configuration

### 1. Update podcast.yaml

Edit `agents/podcast/args/podcast.yaml` and replace all `VOICE_ID_PLACEHOLDER` values with your actual voice IDs:

```yaml
podcasts:
  explore:
    voice_id: "YOUR_ELEVENLABS_VOICE_ID_HERE"
  sololaw:
    voice_id: "YOUR_ELEVENLABS_VOICE_ID_HERE"
  832weekends:
    voice_id: "YOUR_ELEVENLABS_VOICE_ID_HERE"
```

### 2. Add MiniMax API Key

```bash
envchain atlas --set MINIMAX
```

### 3. Add Music Beds

Place your music bed files in `audio/music_beds/`:

```bash
# Example structure
audio/music_beds/
├── explore_upbeat.mp3
├── sololaw_professional.mp3
└── 832weekends_warm.mp3
```

Update the paths in `podcast.yaml` if you use different filenames.

**Music bed requirements:**
- Royalty-free or licensed for podcast use
- Instrumental (no lyrics)
- At least as long as your episodes (or loopable)
- MP3 format

### 4. Episode Ideas (Obsidian)

Episode idea lists live in the Obsidian vault only (no copy in the repo), one per podcast subfolder:

- `Podcasts/explore/Ideas.md`
- `Podcasts/sololaw/Ideas.md`
- `Podcasts/832weekends/Ideas.md`

Edit these in Obsidian to add or refine episode ideas.

### 5. Episode History (Obsidian)

Each show has an episode history doc in the vault: **episode number, title, show notes**, plus published date and duration. Two ways to keep it accurate:

**1. Sync from RSS (source of truth for published feed)**  
Add each podcast’s `rss_url` in `agents/podcast/args/podcast.yaml` (from Spotify for Creators / Anchor or your host). Then run:

```bash
python tools/podcast/sync_history_from_rss.py
```

This fetches the live feed and overwrites the history file with all episodes from the feed. Run whenever you want to refresh from the host (e.g. after manual edits or to backfill).

**2. Update when you publish a new episode**  
When you upload a new episode via the pipeline, run (or let the upload script call):

```bash
python tools/podcast/update_history.py --episode-id explore-001
```

That adds or updates that one episode in the same Obsidian history file from local state. The next `sync_history_from_rss` run will then include it from the feed too.

Files (in vault):

- `Podcasts/Explore with Tony - Episode History.md`
- `Podcasts/Solo Law Club - Episode History.md`
- `Podcasts/832 Weekends - Episode History.md`

### 6. Populate Example Scripts (Optional but Recommended)

Add 2-3 example scripts from past episodes to each context file:
- `agents/podcast/context/explore_examples.md`
- `agents/podcast/context/sololaw_examples.md`
- `agents/podcast/context/832weekends_examples.md`

This helps MiniMax generate scripts that match your existing style.

## Phase 2: Testing

### Test Script Generation

```bash
python tools/podcast/script_generator.py \
  --test \
  --podcast explore \
  --idea "My recent trip to Iceland - the hot springs, the food, and getting lost in Reykjavik"
```

Expected output: Generated script (~600-800 words) matching travel podcast style.

### Test TTS

```bash
python tools/podcast/tts_synthesizer.py \
  --test \
  --text "Testing voice synthesis with a short sample script."
```

Expected output: `data/voice_test.mp3` created with your voice clone.

### Test Audio Mixing

```bash
python tools/podcast/audio_mixer.py \
  --test \
  --voice data/voice_test.mp3 \
  --music audio/music_beds/explore_upbeat.mp3
```

Expected output: `data/mixed_test.mp3` with music bed under voice.

Play test files:
```bash
afplay data/voice_test.mp3
afplay data/mixed_test.mp3
```

## Phase 3: End-to-End Test

Create your first test episode:

```bash
# Step 1: Create episode
python tools/podcast/idea_processor.py \
  --podcast explore \
  --idea "Test episode - my favorite coffee shop in Seattle"

# Note the episode ID from output (e.g., 20260210-170000-explore)

# Step 2: Review generated script
cat data/podcast_episodes/20260210-170000-explore/script_draft.md

# Step 3: Approve script
touch data/podcast_episodes/20260210-170000-explore/.approved

# Step 4: Run approval poller manually
python tools/podcast/script_approver.py

# This will trigger TTS → audio mixing automatically
# Check logs for progress

# Step 5: Listen to final audio
afplay data/podcast_episodes/20260210-170000-explore/mixed_final.mp3

# Step 6: Mark as published
python tools/podcast/episode_manager.py \
  --episode-id 20260210-170000-explore \
  --mark-published
```

## Phase 4: Automation Setup

### Install Launchd Jobs

```bash
# Copy plists to LaunchAgents
cp launchd/com.atlas.podcast-*.plist ~/Library/LaunchAgents/

# Load jobs
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-prompt-explore.plist
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-prompt-sololaw.plist
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-prompt-832weekends.plist
launchctl load ~/Library/LaunchAgents/com.atlas.podcast-script-poller.plist

# Verify jobs loaded
launchctl list | grep podcast
```

**Expected output:**
```
com.atlas.podcast-prompt-explore
com.atlas.podcast-prompt-sololaw
com.atlas.podcast-prompt-832weekends
com.atlas.podcast-script-poller
```

### Weekly Schedule

- **Monday 5 PM**: Explore with Tony prompt
- **Wednesday 5 PM**: Solo Law Club prompt
- **Friday 5 PM**: 832 Weekends prompt
- **Every 30 min**: Script approval poller

## Phase 5: Production Workflow

### Weekly Routine

1. **Receive Telegram prompt** (Mon/Wed/Fri 5 PM)
2. **Reply with idea** via Telegram
3. **Review generated script** (preview sent via Telegram)
4. **Approve script**:
   - Reply `[approved]` in Telegram, OR
   - Run: `touch data/podcast_episodes/{episode_id}/.approved`
5. **Wait ~5-10 min** for TTS + mixing (automatic)
6. **Receive final audio** via Telegram
7. **Upload to Spotify Creators** (Anchor.fm)
8. **Mark published**: `python tools/podcast/episode_manager.py --episode-id {id} --mark-published`

### Manual Episode Creation

```bash
python tools/podcast/idea_processor.py \
  --podcast {podcast_name} \
  --idea "Your episode idea here"
```

### Retry Failed Stage

```bash
python tools/podcast/episode_manager.py \
  --episode-id {episode_id} \
  --retry script  # or tts, mix
```

### Check Status

```bash
# List all episodes
python tools/podcast/episode_manager.py --action list

# Filter by podcast
python tools/podcast/episode_manager.py --action list --podcast explore

# Filter by status
python tools/podcast/episode_manager.py --action list --status script_draft

# Show episode details
python tools/podcast/episode_manager.py --episode-id {episode_id}
```

## Troubleshooting

### Script generation fails

**Check API key:**
```bash
envchain atlas env | grep MINIMAX
```

**Test MiniMax API:**
```bash
python tools/podcast/script_generator.py --test --podcast explore --idea "test"
```

### TTS fails

**Check API key:**
```bash
envchain atlas env | grep ELEVENLABS_API_KEY
```

**Verify voice ID:**
```bash
grep voice_id agents/podcast/args/podcast.yaml
```

**Test TTS:**
```bash
python tools/podcast/tts_synthesizer.py --test --text "testing"
```

### Audio mixing fails

**Check ffmpeg:**
```bash
which ffmpeg
ffmpeg -version
```

**Check music bed:**
```bash
ls -lh audio/music_beds/
```

**Test mixing:**
```bash
python tools/podcast/audio_mixer.py \
  --test \
  --voice data/voice_test.mp3 \
  --music audio/music_beds/explore_upbeat.mp3
```

### Approval not detected

**Check marker file:**
```bash
ls -la data/podcast_episodes/{episode_id}/.approved
```

**Manually run poller:**
```bash
python tools/podcast/script_approver.py
```

**Check poller logs:**
```bash
tail -f logs/podcast_script_poller.log
```

## Cost Monitoring

### Per Episode
- MiniMax script generation: ~$0.15
- ElevenLabs TTS (750 words): ~$1.50
- **Total**: ~$1.65 per episode

### Monthly (10 episodes total)
- 2× Explore with Tony: $3.30
- 4× Solo Law Club: $6.60
- 4× 832 Weekends: $6.60
- **Total**: ~$16.50/month

**Savings vs. Veed.io**: ~$7.50/month + eliminate manual editing

### Track Costs

```bash
# Count episodes this month
python tools/podcast/episode_manager.py --action list | grep "2026-02" | wc -l

# Estimated cost = count × $1.65
```

## Next Steps

1. ✅ Complete Phase 0 (voice clone)
2. ✅ Update podcast.yaml with voice IDs
3. ✅ Add music beds
4. ✅ Test all components
5. ✅ Run end-to-end test episode
6. ✅ Install launchd jobs
7. ✅ Monitor first week of automation
8. ✅ Populate example scripts for better AI generation
9. ✅ Migrate fully from Veed.io

---

**Support**: See [agents/podcast/goals/overview.md](goals/overview.md) for detailed workflow documentation.
