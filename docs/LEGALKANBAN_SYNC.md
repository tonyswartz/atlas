# LegalKanban Task Sync

**Bidirectional sync between LegalKanban case management and Tony Tasks.md**

## How It Works

The sync runs **every hour** automatically and keeps your LegalKanban tasks in sync with your local Tony Tasks.md file.

### What Gets Synced

**FROM LegalKanban → Tony Tasks.md:**
- Incomplete tasks assigned to you (user 1) **in open cases only** (tasks for closed cases are not synced)
- Task priorities (🔴 high, 🟡 medium)
- Case associations (by name when available)
- Due dates
- Task IDs for tracking

**FROM Tony Tasks.md → LegalKanban:**
- ✅ Task completions (check off a task → marked complete in LegalKanban)
- 📅 Due date changes (edit the date → updates in LegalKanban)

## Task Format

Tasks appear in your Tony Tasks.md like this:

```markdown
## LegalKanban Tasks
- [ ] Negotiation: ready for conversation w/prosecutor 🔴 (Nelson) 📅 2025-06-28 [LK-511]
- [ ] Client meeting conducted 🟡 (Smith) 📅 2025-08-07 [LK-623]
- [ ] DOL decision received 🟡 (Case #378) [LK-863]
```

### Elements:
- `- [ ]` / `- [x]` — Checkbox (checked = complete)
- `🔴` — High priority (medium = 🟡, low = no indicator)
- `(Case name)` or `(Case #123)` — Case (sync uses client name when available; fallback to ID)
- `📅 2025-12-31` — Due date (optional, editable)
- `[LK-456]` — LegalKanban task ID (don't edit this!)

## Usage

### To Complete a Task
Just check it off in Tony Tasks.md:
```markdown
- [x] Ready to negotiate with prosecutor 🟡 (Case #154) 📅 2025-06-05 [LK-426]
```

Next sync will:
1. Mark it complete in LegalKanban
2. Remove it from Tony Tasks.md

### To Change a Due Date
Just edit the date directly:
```markdown
- [ ] Client meeting 🟡 (Case #205) 📅 2025-12-15 [LK-623]  <!-- Changed from 08-07 to 12-15 -->
```

Next sync will update the due date in LegalKanban.

### To Add a New Task
Create tasks in LegalKanban as normal. They'll appear in Tony Tasks.md on the next sync.

## Schedule

- **Frequency:** Every hour
- **Automated via:** launchd (`com.atlas.legalkanban-sync`)
- **Logs:** `logs/legalkanban-sync.log`

## Manual Sync

To run sync manually:
```bash
cd /Users/printer/atlas
envchain atlas python3 tools/legalkanban/sync.py
```

## Tools

| Script | Purpose |
|--------|---------|
| `tools/legalkanban/sync.py` | Master orchestrator (run this) |
| `tools/legalkanban/sync_tasks.py` | Pull tasks from LegalKanban |
| `tools/legalkanban/sync_bidirectional.py` | Push changes to LegalKanban |

## Database Access

- **Database:** LegalKanban case management PostgreSQL database
- **Credentials:** Stored in envchain under `LEGALKANBAN` key
- **Access:** Full read/write for task sync, read-only for queries
- **Your user ID:** 1

### Required permissions for the DB user (e.g. `task_manager`)

- **`tasks`:** `SELECT`, `UPDATE` (full table).
- **`cases`:** `SELECT` on `id`, `title`, `closed`:

```sql
GRANT SELECT (id, title, closed) ON cases TO task_manager;
```

- **`title`** — Case display name; we use the first part before " - " (e.g. "Nelson - 5A0858464..." → "Nelson"). If your app stores a separate `client_name`, grant it and we can prefer it in a future change.
- **`closed`** — Open-case filter: sync pulls only tasks in open cases; case search returns only open cases.

## Notes

- Don't delete or modify the `[LK-123]` task IDs — they're used for tracking
- The sync is smart about avoiding duplicates and conflicts
- Completed tasks are automatically cleaned up from your local file
- Changes sync within an hour (or run manually for immediate sync)
