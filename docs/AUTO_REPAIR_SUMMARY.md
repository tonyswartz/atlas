# Autonomous Code Repair - Quick Reference

## What It Does

When a Telegram bot tool fails **3+ times in 6 hours**, the system automatically:
1. Calls MiniMax to diagnose the bug
2. Generates a fix
3. Creates backup of original code
4. Applies and validates the fix
5. **Commits to git** with detailed message
6. Sends Telegram alert with commit hash

## Files

| File | Purpose |
|------|---------|
| `tools/telegram/auto_fixer.py` | MiniMax-powered code repair engine |
| `tools/telegram/bot_health_monitor.py` | Tracks failures, triggers repairs |
| `data/bot_failure_tracking.json` | Failure history per tool |
| `data/backups/` | Timestamped code backups |
| `args/telegram.yaml` → `bot.auto_fix` | Configuration |

## Configuration

```yaml
bot:
  auto_fix:
    enabled: true
    failures_threshold: 3
    time_window_hours: 6
```

## Rollback

```bash
# Option 1: Git revert
git revert <commit_hash>

# Option 2: Restore backup
cp data/backups/tool_name_backup_TIMESTAMP.py tools/telegram/tool_name.py
git add tools/telegram/tool_name.py
git commit -m "Rollback auto-fix"
```

## Safety Features

✅ **Backup before change** - Original code saved to `data/backups/`
✅ **Syntax validation** - Rollback if fix has syntax errors
✅ **Git commit** - Full history with `git log --grep="Auto-fix:"`
✅ **Detailed alerts** - Know exactly what changed and why
✅ **Conservative trigger** - Only fixes recurring issues (3+ failures)

## Cost

~$0.01 per auto-fix (MiniMax API call)

## Example Alert

```
🔧 Bot Health Monitor

🤖 Autonomous Code Repairs:

• ✓ Auto-fixed rotary_tool: Auto-fixed rotary_tool after 3 failures.
  Backup: rotary_tool_backup_20260216_110016.py (commit: a1b2c3d)
```

## Full Documentation

See `docs/AUTO_REPAIR_SYSTEM.md` for complete details.

---

**Built:** 2026-02-16
**Model:** MiniMax M2.5
**Philosophy:** Fix symptoms AND root causes autonomously
