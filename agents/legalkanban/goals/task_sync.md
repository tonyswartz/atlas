# Goal: LegalKanban Task Synchronization

## Objective
Bidirectional sync between LegalKanban case management system and Tony Tasks.md in Obsidian.

## Agent Focus
The **LegalKanban Agent** specializes in:
- Task synchronization (pull incomplete, push completions)
- Case information queries
- Deadline tracking
- Task creation with case context

## Key Tools
- `tools/legalkanban/sync.py` — Master orchestrator
- `tools/legalkanban/sync_tasks.py` — Pull tasks from LegalKanban
- `tools/legalkanban/sync_bidirectional.py` — Push completions and due date changes
- `tools/legalkanban/case_search.py` — Search open cases by name
- `tools/legalkanban/task_create.py` — Create tasks in LegalKanban or local

## Process

### 1. Hourly Sync (Master Orchestrator)
**Runs hourly via launchd**

```xml
~/Library/LaunchAgents/com.atlas.legalkanban-sync.plist
```

**Sync flow:**
1. Push local changes TO LegalKanban (completions, due date edits)
2. Pull updated tasks FROM LegalKanban
3. Log results to `logs/legalkanban-sync.log`

### 2. Pull Tasks (LegalKanban → Tony Tasks)
**sync_tasks.py**

**Query:**
```sql
SELECT id, title, due_date, priority, case_id, case_number
FROM tasks
WHERE assigned_to = 1
  AND completed = false
ORDER BY due_date ASC
```

**Format in Tony Tasks.md:**
```markdown
- [ ] Title 🔴 (Case Name) 📅 YYYY-MM-DD [LK-123]
- [ ] Title 🟡 (Case Name) 📅 YYYY-MM-DD [LK-456]
```

**Priority indicators:**
- 🔴 High
- 🟡 Medium
- (no emoji) Low

**Case display:**
- Always show case NAME, never raw case ID
- Format: `(Nelson)` not `(Case #123)`

### 3. Push Changes (Tony Tasks → LegalKanban)
**sync_bidirectional.py**

**Detects:**
1. **Completions:** `- [x]` marks task complete in LegalKanban
2. **Due date changes:** `📅 2026-02-15` updates due_date in DB
3. **Deletions:** Removed lines (user manually deleted) → no action

**Update queries:**
```sql
-- Mark complete
UPDATE tasks
SET completed = true, completed_at = NOW()
WHERE id = 123;

-- Update due date
UPDATE tasks
SET due_date = '2026-02-15'
WHERE id = 456;
```

**Cleanup:**
- Completed tasks removed from Tony Tasks.md after sync
- Keeps local file clean

### 4. Case Search
**case_search.py**

**Usage:**
```bash
python tools/legalkanban/case_search.py --query "Nelson"
```

**Returns:**
```json
{
  "cases": [
    {
      "id": 42,
      "case_number": "23-1-00123-45",
      "client_name": "John Nelson",
      "case_type": "DUI",
      "status": "active"
    }
  ]
}
```

**Matching:**
- Case insensitive
- Matches last name, first name, or full name
- Returns only open/active cases

### 5. Task Creation
**task_create.py**

**Two modes:**

**A. LegalKanban task (case-related):**
```bash
python tools/legalkanban/task_create.py \
  --system legalkanban \
  --title "File motion to suppress" \
  --case-id 42 \
  --priority high \
  --due-date 2026-02-15 \
  --description "Oral argument scheduled"
```

**B. Local task (non-case):**
```bash
python tools/legalkanban/task_create.py \
  --system local \
  --title "Buy milk" \
  --due-date tomorrow
```

## Edge Cases

### Duplicate Tasks
- Tracked by `[LK-123]` tag in Tony Tasks.md
- Sync ignores tasks without LK tag (local-only)
- Never creates duplicates (ID-based matching)

### Concurrent Edits
- LegalKanban is source of truth for case tasks
- Local completions pushed on next sync
- Due date edits overwrite LegalKanban (local wins)

### Case Name Display
- Always use case name in Tony Tasks, not ID
- Example: `(Nelson)` not `(Case #123)`
- Lookup via case_id → name mapping

### Deleted Tasks
- User deletes line from Tony Tasks → no sync action
- Task remains in LegalKanban (not deleted remotely)
- Will re-appear on next pull if still incomplete

### Network Failures
- Sync logs error but doesn't crash
- Retries on next hourly run
- No data loss (local changes preserved)

## Database Access

**Connection:**
```python
import os
import psycopg2

# Database URL from envchain or .env (key: LEGALKANBAN)
db_url = os.environ.get("LEGALKANBAN")
conn = psycopg2.connect(db_url)
```

**Tables:**
- `tasks` — Task records
- `cases` — Case information
- `users` — User assignments (user_id=1 is Tony)

## Success Criteria
- Tasks sync within 5 minutes of hourly trigger
- Zero duplicate tasks
- Completions propagate to LegalKanban
- Due date changes reflected in DB
- Case names displayed (not IDs)

## Known Issues
- Sync requires network access to LegalKanban DB
- No offline mode (sync fails silently if DB unreachable)
- Manual task deletions don't propagate to LegalKanban

## Future Enhancements
- Real-time sync (webhook-based)
- Conflict resolution for concurrent edits
- Offline queue for changes (sync when reconnected)
- Task comments sync
- Attachment tracking

## References
- `docs/LEGALKANBAN_SYNC.md` — Detailed sync documentation
- Database schema: LegalKanban PostgreSQL
- Launchd plist: `~/Library/LaunchAgents/com.atlas.legalkanban-sync.plist`
- Logs: `logs/legalkanban-sync.log` and `logs/legalkanban-sync.error.log`
