# OpenClaw Deep Dive: Additional Features for Atlas

**Analysis Date:** 2026-02-10
**Focus:** Memory, Browser, Autonomous Features, Tools

---

## 🎯 Executive Summary

After deep analysis of OpenClaw, here are the **highest-value features** we should adopt for Atlas:

| Feature | Value | Complexity | Priority |
|---------|-------|------------|----------|
| **Safari Browser Integration** | ⭐⭐⭐⭐⭐ | Medium | **HIGH** |
| **Memory Search (Semantic)** | ⭐⭐⭐⭐⭐ | Medium | **HIGH** |
| **Cron Tool (Agent-Managed)** | ⭐⭐⭐⭐ | Low | **HIGH** |
| **Sub-agent Architecture** | ⭐⭐⭐⭐ | High | Medium |
| **Session History Tool** | ⭐⭐⭐⭐ | Low | Medium |
| **Webhook Automation** | ⭐⭐⭐ | Low | Medium |
| **Node System (Multi-Device)** | ⭐⭐⭐ | Very High | Low |

---

## 🌐 Browser Implementation (Safari Support)

### **What OpenClaw Does**

OpenClaw's browser system is **architecture-focused**, not Chrome-specific:

**Key Architecture Patterns:**
1. **CDP (Chrome DevTools Protocol)** — Standard protocol for Chromium browsers
2. **Playwright Layer** — High-level actions on top of CDP
3. **Control Server** — HTTP API for browser management
4. **Profile System** — Multiple isolated browser instances
5. **Snapshot + Ref System** — Stable UI tree with refs for actions

**Multi-Browser Support:**
- Chrome (primary)
- Brave
- Edge
- Chromium
- **Any CDP-compatible browser**

### **Why Atlas Should Use Safari**

Safari **does support remote automation**, but via different protocols:

1. **Safari WebDriver** (built-in)
2. **Playwright for WebKit** (Safari's engine)

### **Implementation Path for Atlas**

**Option 1: Playwright for WebKit (RECOMMENDED)**
```python
# agents/safari_browser.py
from playwright.sync_api import sync_playwright

class SafariBrowser:
    """Safari browser control via Playwright WebKit"""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """Launch Safari via WebKit"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.webkit.launch(
            headless=False,
            # Safari respects system settings
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def snapshot(self, format="ai"):
        """Get page snapshot with refs"""
        if format == "ai":
            # AI snapshot with numeric refs
            return self.page.evaluate("""
                () => {
                    // Extract accessible tree
                    return document.body.outerHTML;
                }
            """)
        else:
            # ARIA snapshot
            return self.page.accessibility.snapshot()

    def click(self, ref):
        """Click element by ref"""
        # Resolve ref to selector
        selector = self._resolve_ref(ref)
        self.page.click(selector)

    def type(self, ref, text):
        """Type into element"""
        selector = self._resolve_ref(ref)
        self.page.fill(selector, text)

    def navigate(self, url):
        """Navigate to URL"""
        self.page.goto(url)

    def screenshot(self, full_page=False):
        """Take screenshot"""
        return self.page.screenshot(full_page=full_page)
```

**Integration with Atlas:**
```python
# tools/browser/safari_server.py
from flask import Flask, request, jsonify
from agents.safari_browser import SafariBrowser

app = Flask(__name__)
browser = SafariBrowser()

@app.route('/start', methods=['POST'])
def start():
    browser.start()
    return jsonify({"status": "started"})

@app.route('/snapshot', methods=['GET'])
def snapshot():
    format = request.args.get('format', 'ai')
    snapshot = browser.snapshot(format=format)
    return jsonify({"snapshot": snapshot})

@app.route('/act', methods=['POST'])
def act():
    action = request.json
    if action['kind'] == 'click':
        browser.click(action['ref'])
    elif action['kind'] == 'type':
        browser.type(action['ref'], action['text'])
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(port=18791, host='127.0.0.1')
```

**Benefits of Safari:**
- Native macOS integration
- Better privacy (Apple's stance)
- Lower resource usage
- System-wide password autofill
- Handoff support (iOS ↔ macOS)

**Why This Matters for Atlas:**
- Your entire system runs on macOS
- Safari is already running (no extra browser)
- Native feel, not "agent browser"

---

## 🧠 Memory Search (Semantic)

### **What OpenClaw Does**

**Two-Tool Pattern:**
1. **`memory_search`** — Semantic search across MEMORY.md + memory/*.md
2. **`memory_get`** — Fetch specific lines from files

**Key Features:**
- **Mandatory recall step** — Description forces agent to search before answering
- **Semantic search** — Not just keyword matching
- **Citation mode** — Can include source citations (path + line numbers)
- **Character budget** — Limits injected context size
- **Session transcript search** — Can search past conversations

**Config:**
```json
{
  "memory": {
    "backend": "qmd",  // or "voyageai", "openai"
    "citations": "auto",  // "on", "off", "auto"
    "qmd": {
      "limits": {
        "maxInjectedChars": 8000
      }
    }
  }
}
```

### **Atlas Implementation**

**Phase 1: Enhance Existing Memory Search**
```python
# tools/memory/semantic_search.py (enhance existing)
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

class SemanticMemorySearch:
    """Enhanced semantic search with citations"""

    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = None
        self.documents = []

    def index_memory_files(self):
        """Index MEMORY.md and memory/*.md"""
        files = [
            Path("memory/MEMORY.md"),
            *Path("memory/logs").glob("*.md"),
            *Path("data").glob("*.db")  # SQLite full-text search
        ]

        for file in files:
            content = file.read_text()
            # Split into chunks with overlaps
            chunks = self._chunk_text(content, chunk_size=500, overlap=50)

            for i, chunk in enumerate(chunks):
                self.documents.append({
                    "path": str(file),
                    "chunk_id": i,
                    "text": chunk,
                    "start_line": self._get_start_line(chunk, content),
                    "end_line": self._get_end_line(chunk, content)
                })

        # Create embeddings
        texts = [doc["text"] for doc in self.documents]
        embeddings = self.model.encode(texts)

        # Build FAISS index
        self.index = faiss.IndexFlatL2(embeddings.shape[1])
        self.index.add(embeddings.astype('float32'))

    def search(self, query: str, max_results: int = 5, min_score: float = 0.5):
        """Semantic search with citations"""
        # Encode query
        query_embedding = self.model.encode([query])

        # Search
        distances, indices = self.index.search(
            query_embedding.astype('float32'),
            k=max_results * 2  # Get more, filter by score
        )

        # Format results with citations
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            score = 1 / (1 + dist)  # Convert distance to similarity score
            if score < min_score:
                continue

            doc = self.documents[idx]
            citation = f"{doc['path']}#L{doc['start_line']}-L{doc['end_line']}"

            results.append({
                "snippet": doc["text"],
                "path": doc["path"],
                "startLine": doc["start_line"],
                "endLine": doc["end_line"],
                "citation": citation,
                "score": score
            })

            if len(results) >= max_results:
                break

        return results
```

**Phase 2: Add Citation Support**
```python
# tools/memory/memory_get.py
def memory_get(path: str, from_line: int = None, lines: int = None):
    """
    Fetch specific lines from memory file.

    Args:
        path: Relative path (e.g., "MEMORY.md", "logs/2026-02-10.md")
        from_line: Starting line number
        lines: Number of lines to read

    Returns:
        {"path": str, "text": str, "totalLines": int}
    """
    full_path = Path("memory") / path

    if not full_path.exists():
        return {"path": path, "text": "", "error": "File not found"}

    content = full_path.read_text().splitlines()

    if from_line and lines:
        # Slice specific range
        start = from_line - 1  # 1-indexed to 0-indexed
        end = start + lines
        selected = content[start:end]
    else:
        selected = content

    return {
        "path": path,
        "text": "\n".join(selected),
        "totalLines": len(content),
        "returnedLines": len(selected)
    }
```

**Phase 3: Integrate with Telegram Bot**
```python
# In tools/telegram/tool_definitions.py
{
    "name": "memory_search",
    "description": "Mandatory recall step: semantically search MEMORY.md + memory/*.md before answering questions about prior work, decisions, dates, people, preferences, or todos. Returns top snippets with citations.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "maxResults": {"type": "integer", "default": 5},
            "minScore": {"type": "number", "default": 0.5}
        },
        "required": ["query"]
    }
},
{
    "name": "memory_get",
    "description": "Read specific lines from memory files. Use after memory_search to pull only needed lines and keep context small.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path"},
            "from": {"type": "integer", "description": "Starting line"},
            "lines": {"type": "integer", "description": "Number of lines"}
        },
        "required": ["path"]
    }
}
```

**Benefits:**
- Better recall across sessions
- Citation tracking (know where info came from)
- Character budget prevents context overflow
- Semantic matching (not just keywords)

---

## ⏰ Cron Tool (Agent-Managed Scheduling)

### **What OpenClaw Does**

OpenClaw has a **`cron` tool** that lets the agent manage its own scheduled tasks:

```typescript
// Agent can call:
cron({
  action: "add",
  schedule: "0 9 * * MON",
  task: "Send weekly summary to user",
  sessionKey: "agent:main"
})
```

**Features:**
- Agent can view/add/remove/modify cron jobs
- Jobs trigger agent sessions (not just shell scripts)
- Persistent across restarts
- Validation of cron syntax

**Benefits:**
- **Autonomous scheduling** — Agent schedules its own follow-ups
- **Self-healing** — Agent can fix broken cron jobs
- **Dynamic workflows** — Schedule tasks based on context

### **Atlas Implementation**

```python
# tools/system/cron_tool.py
import json
from pathlib import Path
from crontab import CronTab

class AgentCronManager:
    """Agent-managed cron jobs"""

    def __init__(self):
        self.state_file = Path("data/agent_cron_state.json")
        self.cron = CronTab(user=True)

    def list_jobs(self):
        """List all agent-managed cron jobs"""
        state = self._load_state()
        return [
            {
                "id": job_id,
                "schedule": job["schedule"],
                "task": job["task"],
                "enabled": job["enabled"],
                "last_run": job.get("last_run"),
                "next_run": job.get("next_run")
            }
            for job_id, job in state["jobs"].items()
        ]

    def add_job(self, schedule: str, task: str, agent: str = "main"):
        """
        Add new cron job.

        Args:
            schedule: Cron expression (e.g., "0 9 * * *")
            task: Task description
            agent: Which agent to trigger

        Returns:
            job_id
        """
        # Validate cron syntax
        try:
            test_job = self.cron.new(command="echo test")
            test_job.setall(schedule)
            test_job.remove()
        except:
            raise ValueError(f"Invalid cron expression: {schedule}")

        # Generate job ID
        job_id = hashlib.sha256(f"{schedule}_{task}".encode()).hexdigest()[:12]

        # Create cron job that triggers agent
        command = f"/opt/homebrew/bin/python3 /Users/printer/atlas/tools/system/cron_trigger.py --job-id {job_id}"
        job = self.cron.new(command=command, comment=f"atlas_agent_{job_id}")
        job.setall(schedule)
        self.cron.write()

        # Save state
        state = self._load_state()
        state["jobs"][job_id] = {
            "schedule": schedule,
            "task": task,
            "agent": agent,
            "enabled": True,
            "created_at": datetime.now().isoformat()
        }
        self._save_state(state)

        return job_id

    def remove_job(self, job_id: str):
        """Remove cron job"""
        # Remove from crontab
        for job in self.cron.find_comment(f"atlas_agent_{job_id}"):
            self.cron.remove(job)
        self.cron.write()

        # Remove from state
        state = self._load_state()
        if job_id in state["jobs"]:
            del state["jobs"][job_id]
            self._save_state(state)

    def _load_state(self):
        """Load cron state"""
        if not self.state_file.exists():
            return {"jobs": {}}
        return json.loads(self.state_file.read_text())

    def _save_state(self, state):
        """Save cron state"""
        self.state_file.write_text(json.dumps(state, indent=2))
```

```python
# tools/system/cron_trigger.py
"""
Triggered by cron to execute agent task
"""
import argparse
from agents.workflows import WorkflowEngine

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    # Load job details
    manager = AgentCronManager()
    state = manager._load_state()
    job = state["jobs"].get(args.job_id)

    if not job:
        print(f"Job {args.job_id} not found")
        return

    # Trigger workflow
    engine = WorkflowEngine()
    engine.trigger(job["agent"], "cron_trigger", {
        "job_id": args.job_id,
        "task": job["task"],
        "schedule": job["schedule"]
    })

    # Update last run time
    job["last_run"] = datetime.now().isoformat()
    manager._save_state(state)

if __name__ == "__main__":
    main()
```

**Telegram Bot Integration:**
```python
# tools/telegram/tool_definitions.py
{
    "name": "cron",
    "description": "Manage scheduled tasks. Add, list, or remove cron jobs to schedule recurring agent actions.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "add", "remove", "enable", "disable"]
            },
            "schedule": {"type": "string", "description": "Cron expression (e.g., '0 9 * * MON')"},
            "task": {"type": "string", "description": "Task description"},
            "job_id": {"type": "string", "description": "Job ID for remove/enable/disable"}
        },
        "required": ["action"]
    }
}
```

**Use Cases:**
- **"Remind me every Monday at 9 AM to review tasks"** → Agent creates cron job
- **"Check for new case law opinions daily at 6 AM"** → Autonomous scheduling
- **"Send weekly summary every Friday"** → Self-managing reports

---

## 🔄 Sub-Agents (Background Tasks)

### **What OpenClaw Does**

**`sessions_spawn` tool** creates **isolated background agents**:

```typescript
sessions_spawn({
  task: "Research latest Node.js release notes",
  label: "node research",
  model: "minimax/MiniMax-M2.5",  // Latest model
  runTimeoutSeconds: 300,
  cleanup: "delete"  // or "keep"
})
```

**Features:**
- **Non-blocking** — Main agent continues immediately
- **Isolated session** — Own context, token usage
- **Announce-back** — Results posted to main chat when done
- **Auto-archive** — Sessions cleaned up after 60 min
- **Queue system** — Dedicated "subagent" lane prevents blocking

**Benefits:**
- Parallel work (research while answering questions)
- Long-running tasks don't block user
- Specialized agents for subtasks

### **Atlas Implementation**

We already have **workflow engine** — extend it for background execution:

```python
# agents/subagents.py
import subprocess
import json
from pathlib import Path
from datetime import datetime

class SubAgentManager:
    """Spawn background agents via Claude CLI"""

    def __init__(self):
        self.state_file = Path("data/subagent_runs.json")

    def spawn(self, task: str, label: str = None, model: str = "haiku",
              timeout_seconds: int = 300, agent: str = "main"):
        """
        Spawn background agent.

        Args:
            task: What the subagent should do
            label: Short identifier
            model: Claude model (sonnet, opus, haiku)
            timeout_seconds: Max execution time
            agent: Which agent context to use

        Returns:
            run_id
        """
        run_id = hashlib.sha256(f"{task}_{datetime.now()}".encode()).hexdigest()[:12]

        # Create background task
        cmd = [
            "/Users/printer/.local/bin/claude",
            "-p",
            "--permission-mode", "dontAsk",
            "--model", model,
            f"--max-budget-usd {timeout_seconds * 0.001}",  # Rough estimate
            task
        ]

        # Save state
        state = self._load_state()
        state["runs"][run_id] = {
            "task": task,
            "label": label or task[:50],
            "agent": agent,
            "model": model,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "timeout_seconds": timeout_seconds
        }
        self._save_state(state)

        # Start process (non-blocking)
        subprocess.Popen(
            cmd,
            stdout=open(f"data/subagent_{run_id}.log", "w"),
            stderr=subprocess.STDOUT
        )

        return run_id

    def list_runs(self):
        """List all subagent runs"""
        state = self._load_state()
        return [
            {
                "run_id": run_id,
                "label": run["label"],
                "status": run["status"],
                "runtime": self._calc_runtime(run),
                "agent": run["agent"]
            }
            for run_id, run in state["runs"].items()
        ]

    def get_status(self, run_id: str):
        """Check if subagent is still running"""
        log_file = Path(f"data/subagent_{run_id}.log")

        if not log_file.exists():
            return "unknown"

        # Check if process completed
        # (Simple heuristic: check if log has final output)
        content = log_file.read_text()
        if "✅" in content or "DONE" in content:
            return "completed"
        elif "ERROR" in content or "FAILED" in content:
            return "failed"
        else:
            return "running"

    def announce_result(self, run_id: str, chat_id: str):
        """Announce subagent result to Telegram"""
        log_file = Path(f"data/subagent_{run_id}.log")
        result = log_file.read_text()

        # Send to Telegram
        from tools.common.credentials import get_telegram_token
        import urllib.request
        import urllib.parse

        token = get_telegram_token()
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        message = f"✅ **Background Task Complete**\n\n{result}"

        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }).encode()

        urllib.request.urlopen(url, payload)
```

**Integration:**
```python
# In tools/telegram/tool_definitions.py
{
    "name": "spawn_subagent",
    "description": "Spawn background agent for long-running tasks. Main conversation continues immediately; results announced when done.",
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "What the subagent should do"},
            "label": {"type": "string", "description": "Short identifier"},
            "model": {"type": "string", "enum": ["sonnet", "opus", "haiku"], "default": "haiku"}
        },
        "required": ["task"]
    }
}
```

**Use Cases:**
- **User:** "Research latest Python security advisories"
  **Agent:** "I'll spawn a background agent to research that. I'll let you know when done."
  *(5 minutes later)* "Research complete: [summary]"

- **Multi-task:** User asks 3 questions → Spawn 3 subagents → All return within 2 minutes

---

## 📊 Additional High-Value Features

### **1. Session History Tool**

**What it does:** Agents can query transcripts from past sessions

```python
{
    "name": "sessions_history",
    "description": "View transcript from another agent session. Use to recall past conversations or coordinate with other agents.",
    "parameters": {
        "sessionKey": str,  # e.g., "agent:main:telegram:user:123"
        "limit": int,       # Last N messages
        "includeTool": bool # Include tool calls
    }
}
```

**Atlas use:** Telegram bot can recall previous conversations, briefings can reference past summaries

### **2. Webhook Automation**

**What it does:** External services can trigger agent workflows

```bash
# Receive webhook
curl -X POST http://127.0.0.1:18789/webhook/github \
  -H "Content-Type: application/json" \
  -d '{"event": "push", "repo": "atlas", "commit": "abc123"}'

# Triggers agent workflow
```

**Atlas use:**
- GitHub push → Run code review
- Calendar event reminder → Prep briefing
- Email received → Triage and create task

### **3. Think Mode (Extended Reasoning)**

**What it does:** Agent explicitly shows reasoning steps

```json
{
  "thinking": "high"  // off, low, medium, high
}
```

**Output:** Agent outputs `<thinking>...</thinking>` blocks showing internal reasoning

**Atlas use:** Complex legal analysis, debugging workflows, explaining decisions

---

## 🎯 Implementation Priority

### **Phase 1: High-Value, Low-Complexity (Do First)**

1. **Semantic Memory Search** (2-3 days)
   - Enhance existing search with embeddings
   - Add citation support
   - Integrate with Telegram bot

2. **Cron Tool** (1-2 days)
   - Build agent-managed cron system
   - Add to Telegram tool definitions
   - Test autonomous scheduling

3. **Safari Browser** (3-4 days)
   - Playwright WebKit integration
   - HTTP control server
   - Snapshot + ref system
   - Integration with existing browser tool

### **Phase 2: Medium-Value, Medium-Complexity**

4. **Session History Tool** (1 day)
   - Query past transcripts
   - Add to Telegram tools

5. **Webhook System** (2 days)
   - Webhook receiver endpoint
   - Workflow triggers
   - GitHub/email integration

### **Phase 3: High-Value, High-Complexity**

6. **Sub-Agent System** (4-5 days)
   - Background execution via Claude CLI
   - Announce-back mechanism
   - State management
   - Integration with workflows

---

## 📝 OpenClaw Patterns We Already Adopted

✅ **Inter-agent messaging** (sessions_send equivalent)
✅ **Health monitoring** (not in OpenClaw, but we have it)
✅ **Shared memory** (not in OpenClaw, but we have it)
✅ **Workflow engine** (sessions_spawn approach, but simpler)
✅ **Result caching** (not in OpenClaw core)

---

## 🚀 Quick Wins

**This Weekend:**
1. Add `memory_search` and `memory_get` tools to Telegram bot
2. Implement `cron` tool for agent-managed scheduling
3. Test: "Remind me every Monday at 9 AM to review tasks"

**Next Week:**
1. Safari browser integration (Playwright WebKit)
2. Session history tool
3. Webhook receiver

**Next Sprint:**
1. Full sub-agent system with announce-back
2. Multi-device support (if needed)

---

## 📚 Key Takeaways

**OpenClaw's Strengths:**
- **Modularity** — Clean separation of concerns
- **Multi-channel** — Works across many platforms
- **Tool-first** — Everything is a tool the agent can use
- **Autonomous** — Agent manages its own infrastructure

**What Atlas Should Adopt:**
1. **Safari browser** (better macOS integration)
2. **Semantic memory search** (better recall)
3. **Agent-managed cron** (autonomous scheduling)
4. **Session history** (cross-session coordination)
5. **Webhook automation** (external triggers)

**What Atlas Already Does Better:**
1. **GOTCHA framework** (clearer architecture)
2. **Health monitoring** (proactive failure detection)
3. **Shared memory with locking** (race condition prevention)
4. **Domain-specific agents** (specialized orchestrators)
5. **Result caching** (performance optimization)

---

## ✅ Action Items

**High Priority:**
- [ ] Implement semantic memory search with citations
- [ ] Add agent-managed cron tool
- [ ] Integrate Safari via Playwright WebKit
- [ ] Test end-to-end with Telegram bot

**Medium Priority:**
- [ ] Add session history tool
- [ ] Build webhook receiver
- [ ] Enhance thinking mode (show reasoning)

**Low Priority (Future):**
- [ ] Multi-device node system
- [ ] Full sub-agent with announce-back
- [ ] Canvas/visual workspace

**The path forward is clear: Focus on memory, automation, and browser integration first.**
