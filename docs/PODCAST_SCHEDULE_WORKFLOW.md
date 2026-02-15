# Podcast Schedule Workflow

## Overview

Each podcast has a **Schedule.md** file in its main folder that contains pre-planned episode topics for the next 12 weeks. This streamlines episode creation by providing a queue of ready-to-go episode ideas.

## Schedule Files

Located in each podcast's main folder:
- **Solo Law Club**: `/Podcasts/Solo Law Club/Schedule.md`
- **832 Weekends**: `/Podcasts/832 Weekends/Schedule.md`
- **Explore with Tony**: `/Podcasts/Explore with Tony/Schedule.md`

## Weekly Workflow

### 1. Check for Scheduled Episode

When it's time to create a new episode, first check if there's a scheduled topic:

```bash
python tools/podcast/schedule_manager.py sololaw
python tools/podcast/schedule_manager.py 832weekends
python tools/podcast/schedule_manager.py explore
```

**If a scheduled episode exists:**
- The tool displays the title, theme, key discussion points, and show notes
- Use this as the episode idea for script generation
- Proceed with normal episode creation workflow

**If no scheduled episode:**
- Use the normal weekly prompt to ask the user for an episode idea
- Continue with the usual creative process

### 2. Generate Script

Use the scheduled episode content as the episode idea:

```bash
# For Solo Law Club
python tools/podcast/script_generator.py sololaw "<formatted_episode_idea>"

# The formatted idea comes from schedule_manager.py output
```

The script generator uses the conversational hardprompt to create a natural-sounding script based on the scheduled topic.

### 3. User Review & Edits

- Send the generated script to user for review
- If user wants changes to the topic/approach, edit the script or regenerate
- User can choose to skip the scheduled topic and do something else
- Approval process remains the same

### 4. Remove from Schedule (After Publishing)

Once an episode is approved and published, remove it from the schedule:

```bash
python tools/podcast/schedule_manager.py sololaw --remove 2026-02-20
```

This keeps the Schedule.md file clean and focused on upcoming episodes.

## Schedule File Format

Each podcast uses a consistent markdown format:

### Solo Law Club Format
```markdown
## Friday, February 20, 2026

### Episode Title

#### Key Discussion Points
- Point 1
- Point 2
- Point 3

#### Show Notes
Description paragraph here.

------------------------------------------------------------------------
```

### 832 Weekends Format
```markdown
## February 14, 2026 — Episode Title
**Theme:** Theme Name
**Key Discussion Points:**
- Point 1
- Point 2
- Point 3
**Show Notes:**
Description paragraph here.
```

### Explore with Tony Format
```markdown
### Friday, February 20, 2026
## Episode: Episode Title

### Key Discussion Points
- Point 1
- Point 2
- Point 3

### Show Notes
Description paragraph here.
```

## Benefits

1. **Streamlined Creation**: No need to brainstorm topics every week
2. **Strategic Planning**: Plan themed content runs (e.g., 4-week series on one topic)
3. **Flexibility**: Can still override scheduled topics when inspiration strikes
4. **Batch Planning**: Create 12 weeks of topics in one planning session
5. **Reduced Decision Fatigue**: Less cognitive load on production days

## Editing the Schedule

### Adding New Episodes

Simply edit the Schedule.md file directly in Obsidian:

```markdown
## Friday, March 13, 2026

### Your New Episode Title

#### Key Discussion Points
- Your point 1
- Your point 2
- Your point 3

#### Show Notes
Your show notes here.

------------------------------------------------------------------------
```

### Reordering Episodes

Cut and paste sections in the Schedule.md to change the order.

### Removing Episodes

Delete the entire section (date through separator line).

## Integration with Existing Workflow

The schedule system **enhances** the current workflow, it doesn't replace it:

```
1. Weekly prompt time arrives
2. ✨ NEW: Check Schedule.md first
3a. IF scheduled episode exists → Use that as the idea
3b. IF no scheduled episode → Send normal prompt to user
4. Generate script (same as before)
5. User reviews/approves (same as before)
6. Generate audio (same as before)
7. Publish (same as before)
8. ✨ NEW: Remove published episode from Schedule.md
```

## Automation Opportunities

Future enhancements:
- Auto-check schedule in `weekly_prompt.py`
- Auto-remove from schedule in publish workflow
- Send preview of next 3 scheduled episodes each month
- Alert when schedule has < 4 weeks remaining

## CLI Usage Examples

### Check for scheduled episode
```bash
python tools/podcast/schedule_manager.py sololaw
```

### Remove published episode
```bash
# After publishing the February 20th episode:
python tools/podcast/schedule_manager.py sololaw --remove 2026-02-20
```

### Quick check all podcasts
```bash
for podcast in sololaw 832weekends explore; do
    echo "=== $podcast ==="
    python tools/podcast/schedule_manager.py $podcast
    echo
done
```

## Notes

- Schedule dates are matched with ±3 day tolerance (so you don't have to be exact)
- The tool automatically finds the next Friday (or configured publish day)
- If user declines a scheduled topic, it stays in the schedule until manually removed
- Schedule entries can be edited at any time - changes take effect immediately
