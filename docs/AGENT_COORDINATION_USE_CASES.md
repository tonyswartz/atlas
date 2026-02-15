# Agent Coordination Use Cases

**Complete guide to implementing OpenClaw-inspired coordination features in Atlas**

## Overview

Atlas now has 5 powerful coordination features:
1. **Inter-Agent Messaging** — Agents communicate cross-domain
2. **Health Monitoring** — Track performance, catch failures early
3. **Shared Memory** — Coordinate without tight coupling
4. **Workflow Engine** — Declarative multi-agent workflows
5. **Result Caching** — Fast responses, fewer API calls

**Tests Status:** ✅ All comprehensive tests passed (see `tests/test_agent_features.py`)

---

## 🎯 Real-World Use Cases for Atlas

### **Use Case 1: Print Completion → Low Stock Alert → Auto-Reminder**

**Problem:** When filament runs low after print, manually creating reminder is tedious.

**Solution:** Multi-agent workflow

**Implementation:**

**1. Bambu Agent detects low stock after logging print:**
```python
# In tools/bambu/bambu_reply_handler.py
from agents.workflows import WorkflowEngine
from agents.shared_memory import SharedMemory

# After logging to JeevesUI
if remaining_grams < 100:
    engine = WorkflowEngine()
    engine.trigger("bambu", "print_complete_low_stock", {
        "filename": filename,
        "spool_id": spool_id,
        "remaining_grams": remaining_grams,
        "filament_type": filament_type,
        "filament_color": filament_color
    })
```

**2. Workflow orchestrates multiple agents:**
```yaml
# workflows/print_low_stock.yaml (already created)
name: "Print completion with low stock alert"
trigger:
  agent: bambu
  event: print_complete_low_stock
steps:
  - agent: telegram
    action: send_notification
    template: |
      🖨️ {{filename}} done
      Spool #{{spool_id}}: {{remaining_grams}}g left
      ⚠️ Low stock!

  - agent: system
    action: run_script
    script: "tools/briefings/reminder_add.py"
    args:
      - "--task"
      - "Order {{filament_type}} filament ({{filament_color}})"
      - "--schedule"
      - "this week"
```

**Result:** Fully automated - print done, alert sent, reminder created, no manual intervention.

---

### **Use Case 2: Health Anomaly → Reschedule Court Appearance**

**Problem:** HRV drops significantly before important court date. Should probably reschedule.

**Solution:** Inter-agent messaging + workflow

**Implementation:**

**1. Briefings Agent detects HRV anomaly:**
```python
# In tools/briefings/health_monitor.py
from agents.messaging import send_message
from agents.health import AgentHealthMonitor

# Check for HRV drop
if hrv_drop_percent > 20:
    # Track health event
    monitor = AgentHealthMonitor()
    monitor.record_execution("briefings", "health_check", duration, success=True, context={
        "hrv_drop": hrv_drop_percent,
        "alert": "significant_drop"
    })

    # Message LegalKanban agent
    send_message("briefings", "legalkanban", {
        "event": "health_alert",
        "severity": "high",
        "recommendation": "consider_rescheduling",
        "hrv_drop_percent": hrv_drop_percent,
        "next_7_days": next_week_cases
    }, priority="high")
```

**2. LegalKanban Agent receives message and suggests rescheduling:**
```python
# In tools/legalkanban/health_integration.py (new file)
from agents.messaging import receive_messages, send_message

messages = receive_messages("legalkanban")
for msg in messages:
    if msg["message"].get("event") == "health_alert":
        # Find upcoming court dates
        cases = query_upcoming_cases(days=7)

        if cases:
            # Send Telegram notification with options
            send_message("legalkanban", "telegram", {
                "action": "ask_user",
                "message": f"⚠️ HRV dropped {msg['message']['hrv_drop_percent']}%\n\nUpcoming cases:\n{format_cases(cases)}\n\nShould we reschedule any?"
            })
```

**Result:** Proactive health-based scheduling recommendations.

---

### **Use Case 3: Concurrent Task Sync (Race Condition Prevention)**

**Problem:** Two processes trying to modify `Tony Tasks.md` simultaneously causes corruption.

**Solution:** Shared memory locking

**Implementation:**

**1. LegalKanban sync acquires lock:**
```python
# In tools/legalkanban/sync.py
from agents.shared_memory import SharedMemory

memory = SharedMemory()

# Acquire lock before modifying file
with memory.lock("tony_tasks_md", timeout=30):
    # Safe to read and modify
    tasks = read_tony_tasks()
    sync_to_legalkanban(tasks)
    write_tony_tasks(updated_tasks)
```

**2. Manual edits also acquire lock:**
```python
# In tools/legalkanban/task_create.py
from agents.shared_memory import SharedMemory

memory = SharedMemory()

with memory.lock("tony_tasks_md", timeout=30):
    # Safe to append new task
    append_task_to_file(task)
```

**Result:** No more file corruption from concurrent access.

---

### **Use Case 4: Expensive Case Lookups (Caching)**

**Problem:** LegalKanban case queries are slow (database round-trip). Same cases queried repeatedly.

**Solution:** Result caching

**Implementation:**

**1. Cache case queries for 1 hour:**
```python
# In tools/legalkanban/case_search.py
from agents.cache import cache_result

@cache_result(ttl=3600, key_fn=lambda case_id: f"case_{case_id}")
def get_case_details(case_id: int) -> dict:
    """Query LegalKanban database (cached for 1 hour)"""
    conn = get_database_connection()
    # ... expensive query ...
    return case_data
```

**2. Invalidate cache on updates:**
```python
# In tools/legalkanban/sync_bidirectional.py
from agents.cache import invalidate_cache

@invalidate_cache(keys=["case_{{case_id}}", "tasks_{{case_id}}"])
def update_case(case_id: int, updates: dict):
    """Update case (invalidates cache)"""
    conn = get_database_connection()
    # ... update database ...
```

**Result:**
- First query: 500ms (database)
- Subsequent queries: 5ms (cache)
- **100x faster**

---

### **Use Case 5: Proactive System Health Alerts**

**Problem:** Services fail silently. Don't know until manually checking logs.

**Solution:** Health monitoring + Telegram alerts

**Implementation:**

**1. Integrate health tracking into all scripts:**
```python
# In tools/briefings/daily_brief.py
from agents.health import AgentHealthMonitor

monitor = AgentHealthMonitor()

with monitor.track("briefings", "daily_brief"):
    # Generate brief
    brief = generate_daily_brief()
    send_telegram(brief)
```

**2. Run health check via cron/launchd:**
```bash
# Every 30 minutes
*/30 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/agents/health.py --dashboard

# Alert if degraded
*/15 * * * * /opt/homebrew/bin/python3 /Users/printer/atlas/scripts/check_agent_health.py
```

**3. Alert script:**
```python
# scripts/check_agent_health.py
from agents.health import AgentHealthMonitor
from agents.messaging import send_message

monitor = AgentHealthMonitor()

for agent in ["telegram", "bambu", "legalkanban", "briefings", "system"]:
    health = monitor.get_health(agent, window_hours=1)

    if health["status"] in ["degraded", "down"]:
        send_message("system", "telegram", {
            "action": "alert",
            "message": f"⚠️ {agent} agent: {health['status']}\nSuccess rate: {health['success_rate']:.0%}"
        }, priority="urgent")
```

**Result:** Immediate notification when services degrade.

---

### **Use Case 6: Multi-Step Research → Case Task Creation**

**Problem:** User asks Telegram bot to research case law, summarize, and create task.

**Solution:** Workflow with multiple agents

**Implementation:**

**1. Create workflow:**
```yaml
# workflows/research_to_task.yaml
name: "Research case law and create task"
trigger:
  agent: telegram
  event: research_request
steps:
  - agent: briefings
    action: run_script
    script: "tools/legal/wa_opinions_to_obsidian.py"
    args:
      - "--topic"
      - "{{topic}}"
      - "--days"
      - "7"

  - agent: telegram
    action: send_notification
    template: "✅ Research complete: {{topic}}"

  - agent: legalkanban
    action: create_task
    title: "Review case law: {{topic}}"
    case_id: "{{case_id}}"
    priority: "medium"
    due_date: "{{due_date}}"
```

**2. Trigger from Telegram bot:**
```python
# In tools/telegram/conversation.py
from agents.workflows import WorkflowEngine

if user_intent == "research_and_task":
    engine = WorkflowEngine()
    engine.trigger("telegram", "research_request", {
        "topic": extracted_topic,
        "case_id": extracted_case_id,
        "due_date": extracted_due_date or "next week"
    })
```

**Result:** Single command orchestrates research, notification, and task creation.

---

### **Use Case 7: Coordinated Morning Routine**

**Problem:** Multiple briefings run independently. Want coordinated sequence with shared state.

**Solution:** Workflow + shared memory

**Implementation:**

**1. Morning routine workflow:**
```yaml
# workflows/morning_routine.yaml
name: "Coordinated morning routine"
trigger:
  agent: system
  event: morning_start
steps:
  # Step 1: Run daily brief
  - agent: briefings
    action: run_script
    script: "tools/briefings/daily_brief.py"

  # Step 2: Check health data
  - agent: briefings
    action: run_script
    script: "tools/briefings/wellness_coach.py"

  # Step 3: Sync LegalKanban tasks
  - agent: legalkanban
    action: run_script
    script: "tools/legalkanban/sync.py"

  # Step 4: Consolidated morning message
  - agent: telegram
    action: send_notification
    template: |
      🌅 Good morning!

      ✅ Daily brief sent
      ✅ Health check complete
      ✅ Tasks synced

      {{agenda_summary}}
```

**2. Trigger from launchd at 6 AM:**
```bash
# Instead of separate cron jobs, single workflow
/opt/homebrew/bin/python3 -c "
from agents.workflows import WorkflowEngine
from agents.shared_memory import SharedMemory
import datetime

memory = SharedMemory()
memory.set('morning_routine_started', datetime.datetime.now().isoformat())

engine = WorkflowEngine()
engine.trigger('system', 'morning_start', {})
"
```

**Result:** Coordinated sequence, single consolidated notification.

---

## 💡 Additional Use Case Ideas

### **Legal Domain**
1. **Case Assignment Notification**
   - LegalKanban → new case assigned → Telegram alert → create research tasks
2. **Deadline Tracking**
   - LegalKanban → task due in 3 days → Telegram reminder → check calendar conflicts
3. **Discovery Request Tracking**
   - Email → new discovery request → LegalKanban task → calendar block for review

### **3D Printing Domain**
4. **Print Queue Management**
   - Shared memory tracks current print → prevents concurrent prints
   - Queue system: Telegram → "add to print queue" → Bambu agent starts when idle
5. **Filament Inventory Management**
   - Low stock → check Amazon prices → create shopping list task
   - New filament ordered → update JeevesUI inventory → clear low stock flag
6. **Print Failure Detection**
   - BambuBuddy → print stopped early → Telegram alert with camera snapshot → create debug task

### **Health & Wellness Domain**
7. **Workout Scheduling**
   - Oura readiness <70 → reschedule workout → update calendar → Telegram notification
8. **Sleep Quality Alerts**
   - 3 consecutive poor sleep nights → suggest schedule adjustment → create task to review evening routine
9. **Nutrition Tracking Integration**
   - Journal entry mentions food → extract macros → send to health dashboard

### **Productivity Domain**
10. **Smart Task Prioritization**
    - Combine: calendar (available time), LegalKanban (deadlines), health (readiness) → suggest daily priorities
11. **Context Switching Minimization**
    - Shared memory tracks "current focus area" → batch notifications → deliver at context switch times
12. **Time Blocking Automation**
    - LegalKanban tasks → estimate duration → auto-create calendar blocks → Telegram confirmation

### **System Monitoring Domain**
13. **Cascading Failure Detection**
    - One agent fails → check dependent agents → send comprehensive alert → attempt auto-recovery
14. **Performance Trend Analysis**
    - Weekly health report → average response times → identify degrading agents → proactive optimization
15. **Resource Usage Monitoring**
    - Track cache size, database connections, API rate limits → alert before hitting limits

---

## 🛠️ Implementation Checklist

When implementing a new coordinated feature:

### **1. Design Phase**
- [ ] Identify which agents are involved
- [ ] Determine if workflow, messaging, or both needed
- [ ] Check for race conditions (use shared memory locks)
- [ ] Consider caching expensive operations
- [ ] Plan health monitoring integration

### **2. Implementation Phase**
- [ ] Create workflow YAML (if multi-step)
- [ ] Add messaging calls (if cross-domain)
- [ ] Integrate health tracking (context manager)
- [ ] Add caching (if expensive operations)
- [ ] Use shared memory for coordination

### **3. Testing Phase**
- [ ] Test happy path
- [ ] Test failure scenarios
- [ ] Verify health metrics recorded
- [ ] Check cache hit/miss rates
- [ ] Validate workflow execution

### **4. Production Phase**
- [ ] Add to monitoring dashboard
- [ ] Document in agent goals
- [ ] Set up alerts for failures
- [ ] Monitor performance metrics

---

## 📊 Monitoring Commands

**Check Agent Health:**
```bash
python3 agents/health.py --dashboard
```

**View Messages:**
```bash
python3 agents/messaging.py --status
```

**Check Shared Memory:**
```bash
python3 agents/shared_memory.py --stats
```

**List Workflows:**
```bash
python3 agents/workflows.py --list
```

**Cache Statistics:**
```bash
python3 agents/cache.py --stats
```

---

## 🚀 Quick Start: First Coordinated Feature

**Goal:** Add "print done → send notification → create reminder if low stock"

**Steps:**

1. **Create workflow** (already done: `workflows/print_low_stock.yaml`)

2. **Integrate into Bambu agent:**
```python
# In tools/bambu/bambu_reply_handler.py
from agents.workflows import WorkflowEngine

# After logging to JeevesUI
if remaining_grams < 100:
    WorkflowEngine().trigger("bambu", "print_complete_low_stock", {
        "filename": filename,
        "spool_id": spool_id,
        "remaining_grams": remaining_grams,
        "filament_type": filament_type,
        "filament_color": filament_color
    })
```

3. **Test:**
```bash
# Manually trigger workflow
python3 agents/workflows.py --trigger bambu print_complete_low_stock \
  --data '{"filename":"test.gcode","spool_id":5,"remaining_grams":85,"filament_type":"PLA","filament_color":"Red"}'
```

4. **Monitor:**
```bash
# Check if workflow executed
python3 agents/health.py --status bambu
```

---

## 🎯 Success Metrics

Track these to measure coordination effectiveness:

1. **Automation Rate** — % of manual tasks now automated
2. **Response Time** — Time from event to action completion
3. **Failure Rate** — % of workflows that fail
4. **Cache Hit Rate** — % of cached vs fresh queries
5. **Agent Health** — Success rate per agent
6. **Message Volume** — Inter-agent messages per day

**Goal:**
- Automation Rate: >80%
- Response Time: <5 seconds
- Failure Rate: <5%
- Cache Hit Rate: >60%
- Agent Health: >95% success rate

---

## 🔮 Future Enhancements

Ideas for expanding coordination:

1. **Visual Workflow Builder** — Web UI for creating workflows
2. **Agent Analytics Dashboard** — Real-time metrics and logs
3. **Smart Retry Logic** — Auto-retry failed steps with backoff
4. **Workflow Versioning** — Track changes to workflow definitions
5. **A/B Testing** — Test different workflow approaches
6. **Cost Tracking** — Monitor API call costs per workflow
7. **Audit Logging** — Track all agent interactions for compliance

---

## 📚 Reference

**Documentation:**
- `agents/README.md` — Subagent architecture
- `agents/QUICKSTART.md` — Agent usage guide
- `docs/SUBAGENT_ARCHITECTURE.md` — Implementation details
- This document — Use cases and examples

**Test Suite:**
- `tests/test_agent_features.py` — Comprehensive tests (all passing ✅)

**Example Workflows:**
- `workflows/print_low_stock.yaml` — Print completion workflow

**CLI Tools:**
- `agents/messaging.py` — Message management
- `agents/health.py` — Health monitoring
- `agents/shared_memory.py` — Shared state
- `agents/workflows.py` — Workflow execution
- `agents/cache.py` — Cache management

---

## ✅ Summary

Atlas now has powerful coordination features inspired by OpenClaw:

1. **Messaging** — Agents communicate cross-domain
2. **Health** — Track performance, catch failures early
3. **Memory** — Shared state, resource locking
4. **Workflows** — Declarative multi-agent workflows
5. **Caching** — Fast responses, fewer API calls

**Status:** ✅ All features implemented and tested

**Next:** Choose a use case, implement it, and watch multiple agents coordinate seamlessly.

**The system is now ready for sophisticated multi-agent workflows.**
