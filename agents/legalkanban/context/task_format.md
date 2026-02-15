# LegalKanban Task Format Specifications

## Tony Tasks.md Format

**Template:**
```markdown
- [ ] Task title 🔴/🟡 (Case Name) 📅 YYYY-MM-DD [LK-123]
```

**Components:**
1. `- [ ]` — Checkbox (unchecked = incomplete, `[x]` = complete)
2. `Task title` — Descriptive action item
3. `🔴/🟡` — Priority indicator (optional)
   - 🔴 High priority
   - 🟡 Medium priority
   - (none) Low priority
4. `(Case Name)` — Human-readable case identifier
   - Use client last name: `(Nelson)`
   - NOT case number: ~~`(Case #123)`~~
5. `📅 YYYY-MM-DD` — Due date in ISO format
6. `[LK-123]` — LegalKanban task ID for sync tracking

**Examples:**
```markdown
- [ ] File motion to suppress 🔴 (Nelson) 📅 2026-02-15 [LK-42]
- [ ] Send discovery response 🟡 (Smith) 📅 2026-02-20 [LK-89]
- [ ] Client intake call (Johnson) 📅 2026-02-12 [LK-103]
```

## LegalKanban Database Schema

**tasks table:**
```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    case_id INTEGER REFERENCES cases(id),
    assigned_to INTEGER REFERENCES users(id),
    due_date DATE,
    priority VARCHAR(20), -- 'high', 'medium', 'low'
    completed BOOLEAN DEFAULT false,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**cases table:**
```sql
CREATE TABLE cases (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(50),
    client_name VARCHAR(255),
    case_type VARCHAR(50),
    status VARCHAR(20), -- 'active', 'closed', 'pending'
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Case Name Mapping

**Lookup process:**
1. Task has `case_id = 42`
2. Query: `SELECT client_name FROM cases WHERE id = 42`
3. Result: `"John Nelson"`
4. Extract last name: `"Nelson"`
5. Display in Tony Tasks: `(Nelson)`

**Fallback for multiple clients with same last name:**
- Use first + last: `(John Nelson)`
- Or case number: `(Nelson #123)`

## Task State Transitions

**LegalKanban → Tony Tasks (Pull):**
```
DB: completed=false → Tony Tasks: - [ ] Title
```

**Tony Tasks → LegalKanban (Push):**
```
Tony Tasks: - [x] Title → DB: UPDATE completed=true
Tony Tasks: 📅 2026-02-20 → DB: UPDATE due_date='2026-02-20'
```

**Cleanup after completion:**
```
Tony Tasks: - [x] Title [LK-42] → (sync) → Remove from Tony Tasks
```

## Priority Mapping

| Tony Tasks | LegalKanban DB |
|------------|----------------|
| 🔴         | high           |
| 🟡         | medium         |
| (none)     | low            |

## Date Format

**Tony Tasks display:**
- `📅 2026-02-15` (ISO format, always 10 characters)

**LegalKanban DB:**
- `due_date DATE` column (PostgreSQL DATE type)

**Parsing:**
```python
from datetime import datetime

# Parse from Tony Tasks
date_str = "2026-02-15"
date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

# Format for Tony Tasks
date_str = date_obj.strftime("%Y-%m-%d")
```

## Sync ID Tracking

**[LK-123] tag:**
- Unique identifier linking Tony Tasks ↔ LegalKanban
- Always at end of line
- Format: `[LK-{task_id}]`
- Parsed via regex: `\[LK-(\d+)\]`

**When missing:**
- Task is local-only (not synced to LegalKanban)
- Sync process ignores it
- User can manually add LK tag if needed

## User ID Mapping

**LegalKanban:**
- User ID 1 = Tony (primary user)
- All synced tasks have `assigned_to = 1`

**Tony Tasks.md:**
- Single user (Tony)
- No user field needed
