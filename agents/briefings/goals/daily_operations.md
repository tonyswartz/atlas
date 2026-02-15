# Goal: Daily Briefings & Monitoring

## Objective
Generate daily briefings (morning, afternoon, weekly) with weather, news, health metrics, and reminders.

## Agent Focus
The **Briefings Agent** specializes in:
- Daily brief generation (6 AM)
- Research brief (3 PM tech news)
- Weekly review (Friday 5 PM)
- Health monitoring (proactive alerts)
- Reminder management

## Key Tools
- `tools/briefings/daily_brief.py` — 6 AM briefing
- `tools/briefings/research_brief.py` — 3 PM tech news
- `tools/briefings/weekly_review.py` — Friday 5 PM review
- `tools/briefings/health_monitor.py` — Daily health checks
- `tools/briefings/wellness_coach.py` — 7:30 AM fitness advice
- `tools/briefings/reminder_add.py` — Add/update reminders

## Process

### 1. Morning Brief (6 AM)
**Runs daily via launchd**

```xml
~/Library/LaunchAgents/com.atlas.daily-brief.plist
```

**Components:**
1. **Weather:**
   - Current conditions (temp, description)
   - Today's forecast (high/low, precipitation)
   - Timeout: 20s primary, 10s fallback

2. **Reminders:**
   - Read from Tony Reminders.md
   - Auto-rolls recurring reminders (weekly, daily)
   - Sections: Today, Later This Week, Shopping

3. **Calendar:**
   - Today's events via gog (Google OAuth)
   - Lists: time, title, location

4. **Case Law (Legal Briefings):**
   - WA appellate opinions from previous day
   - PDF holdings extracted
   - Saved to: Research/Briefs/ and Case Law/

5. **Quote of the Day:**
   - Random inspirational quote
   - Saved to daily digest

**Output:**
- Sent to Telegram (chat ID: 8241581699)
- Saved to Obsidian: Digest/YYYY-MM-DD.md
- Legal briefs → Research/Briefs/ and Case Law/

### 2. Research Brief (3 PM)
**Runs daily via launchd**

```xml
~/Library/LaunchAgents/com.atlas.research-brief.plist
```

**Components:**
1. **Tech News:**
   - Google RSS feed search: "AI", "LLM", "machine learning"
   - Last 24 hours

2. **Kraken News:**
   - Seattle Kraken updates
   - Game results, roster news

**Output:**
- Sent to Telegram
- Brief summary with links

### 3. Weekly Review (Friday 5 PM)
**Runs weekly via launchd**

```xml
~/Library/LaunchAgents/com.atlas.weekly-review.plist
```

**Components:**
1. **Journal Stats:**
   - Entries this week
   - Mood trend analysis
   - Top keywords

2. **Fitness Summary:**
   - Workouts completed
   - HRV average
   - Sleep quality

3. **Kanban Health:**
   - Tasks completed vs created
   - Overdue items
   - Progress assessment

4. **AI Recap:**
   - MiniMax-generated summary of week's journal entries
   - Highlights and themes

5. **Nudges:**
   - Gated on `this["days"] > 0` logic
   - Suggests areas needing attention

**Output:**
- Sent to Telegram
- Backs up week's journals to CSV
- Saved to Obsidian: Reviews/YYYY-WW.md

### 4. Health Monitor (Daily)
**Proactive health alerts**

**Runs:** Daily (schedule TBD via launchd)

**Checks:**
1. **Oura Ring Data:**
   - HRV anomalies (sudden drops)
   - RHR spikes (resting heart rate)
   - Sleep quality degradation
   - Readiness score <70

2. **Workout Gaps:**
   - No workouts in 3+ days
   - Suggests recovery vs laziness

3. **Pattern Detection:**
   - Consecutive poor sleep nights
   - Declining HRV trend (7-day window)

**Output:**
- Telegram alerts (only when anomalies detected)
- Logged to health history

### 5. Wellness Coach (7:30 AM)
**Recovery-aware fitness recommendations**

**Runs:** Daily at 7:30 AM via launchd

**Components:**
1. **Today's Recommendation:**
   - Based on Oura readiness score
   - Suggests workout intensity or rest day

2. **PR Celebrations:**
   - Detects personal records (steps, HRV, workouts)
   - Sends congratulatory message

3. **Long-term Trends:**
   - Weekly step average
   - Workout consistency
   - Goal tracking

**Output:**
- Telegram message with actionable advice

## Edge Cases

### Weather Timeout
- Primary API: 20s timeout
- Fallback API: 10s timeout
- If both fail: Skip weather section, continue brief

### Calendar OAuth Failure
- gog calendar requires Keychain access
- Launchd jobs run in user session (Keychain accessible)
- Cron jobs CANNOT access Keychain (use launchd only)

### MindsetLog Database Access
- Journal sync via direct PostgreSQL connection
- URL from envchain: `MINDSETLOG_DB_URL`
- Fallback: OAuth API (slower, less reliable)

### Health Data Unavailable
- Oura API requires valid access token
- Graceful degradation: skip health section
- Log error but don't crash brief

## Launchd vs Cron

**Use launchd for:**
- Briefings (need Keychain for gog calendar)
- Health monitoring (Oura OAuth tokens)
- Any script requiring envchain credentials

**Use cron for:**
- Simple file watchers (no Keychain needed)
- Scripts with .env credentials only

**Key lesson:**
- Launchd runs in user session → Keychain access ✅
- Cron runs in system context → Keychain blocked ❌
- Always wrap launchd commands with `envchain atlas` for token access

## Success Criteria
- Daily brief delivered by 6:05 AM
- Research brief delivered by 3:05 PM
- Weekly review delivered Friday 5:00-5:10 PM
- Health alerts within 15 min of anomaly detection
- Zero crashes due to missing data

## Known Issues
- Weather API occasionally times out (increased to 20s/10s)
- MindsetLog OAuth sessions expire (use direct DB instead)
- Oura API rate limits (cache data for 1 hour)

## Future Enhancements
- Voice briefing via text-to-speech
- Custom brief templates per day (weekday vs weekend)
- Integration with Apple Health for additional metrics
- Smart reminder suggestions based on calendar

## References
- `docs/CRON.md` — Launchd vs cron guidance
- `docs/ENVCHAIN.md` — Credential management
- Launchd plists: `~/Library/LaunchAgents/com.atlas.*.plist`
- Logs: `logs/daily-brief.log`, `logs/weekly-review.log`
