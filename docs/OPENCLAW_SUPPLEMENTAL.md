# OpenClaw Supplemental Analysis: Skills & Deployment

**Analysis Date:** 2026-02-10
**Focus:** Plugin/Skill System, Deployment Patterns, Tool Modularity
**Builds on:** [OPENCLAW_DEEP_DIVE.md](./OPENCLAW_DEEP_DIVE.md)

---

## 🎯 Executive Summary

Beyond the core features analyzed in the deep dive, OpenClaw has two architectural patterns worth considering:

| Pattern | Value for Atlas | Complexity | Priority |
|---------|----------------|------------|----------|
| **Skills System (Modular Tools)** | ⭐⭐⭐⭐ | Medium | Medium |
| **ClawHub (Tool Registry)** | ⭐⭐⭐ | High | Low |
| **Raspberry Pi Deployment** | ⭐⭐⭐⭐⭐ | Low | **HIGH** |
| **Gateway Mode Architecture** | ⭐⭐⭐⭐ | Medium | Medium |

---

## 📦 Skills System: Modular Tool Bundles

### **What OpenClaw Does**

OpenClaw uses a **skills system** where each skill is a self-contained bundle:

```
skills/
  calendar-integration/
    SKILL.md           # Primary description + usage
    config.yaml        # Skill metadata
    scripts/           # Supporting files
      sync.py
      parse.py
```

**Key Features:**
- **SKILL.md** is the instruction manual (loaded into agent context)
- **Versioned bundles** with semver (1.2.3)
- **Public registry (ClawHub)** for discovery and sharing
- **CLI tools** for install/update/publish
- **Automatic loading** when session starts
- **Workspace-scoped** (skills only available in specific projects)

**Example SKILL.md:**
```markdown
---
summary: "Google Calendar integration with 2-way sync"
read_when:
  - User mentions calendar, appointments, or scheduling
  - Need to check availability or create events
---

# Calendar Integration

This skill provides 2-way sync with Google Calendar.

## Tools Available
- `calendar_list_events` - List upcoming events
- `calendar_create_event` - Create new event
- `calendar_check_availability` - Find free slots

## Usage
When user asks about calendar:
1. Use `calendar_list_events` to see current schedule
2. Suggest free slots with `calendar_check_availability`
3. Create events with `calendar_create_event`

## Setup Required
- OAuth credentials in envchain under "calendar"
- First run: will open browser for authorization
```

### **ClawHub Registry**

**Public skill marketplace:**
- Search: `clawhub search "calendar"`
- Install: `clawhub install google-calendar-sync`
- Update: `clawhub update --all`
- Publish: `clawhub publish ./my-skill --version 1.0.0`
- Sync: `clawhub sync --all` (backup all skills)

**Features:**
- **Vector search** (embeddings, not just keywords)
- **Versioning** with changelogs and tags
- **Stars and comments** for community feedback
- **Moderation** (report/hide/ban abusive skills)
- **Download counts** for popularity signals
- **Lock file** (.clawhub/lock.json) tracks installed versions

**Security:**
- GitHub account required (must be 1+ weeks old)
- 3+ reports auto-hide skills
- Moderators can ban users
- All skills are public (transparency)

---

## 🔄 How This Maps to Atlas

### **Current State**

Atlas has a **monolithic tools/** directory:
```
tools/
  bambu/
  briefings/
  legalkanban/
  telegram/
  browser/
```

**Problems:**
1. No versioning (hard to track changes)
2. No isolation (tools can conflict)
3. No sharing (can't easily export a tool bundle)
4. No discovery (must know tool exists to use it)

### **Skills-Based Approach**

Reorganize Atlas tools as **self-contained skills**:

```
skills/
  bambu-print-tracking/
    SKILL.md                    # "Track 3D print completions and log filament usage"
    goals/
      print_tracking.md
    tools/
      bambu_buddy_watcher.py
      bambu_prompt_poller.py
      bambu_reply_handler.py
    config.yaml                 # Metadata

  legalkanban-sync/
    SKILL.md                    # "Bidirectional task sync with LegalKanban"
    goals/
      task_sync.md
    tools/
      sync.py
      query.py
    config.yaml

  telegram-bot/
    SKILL.md                    # "Multi-model Telegram bot with tool support"
    goals/
      conversation_management.md
    tools/
      bot.py
      conversation.py
      tool_runner.py
    config.yaml
```

**Benefits:**
1. **Portable** — Copy skill folder to another Atlas instance
2. **Versioned** — Track skill changes independently
3. **Documented** — SKILL.md is always up-to-date
4. **Discoverable** — List all skills, see what's available
5. **Testable** — Each skill can have its own test suite

### **Implementation: Lightweight Version**

We don't need ClawHub's full registry — start with **local skills management**:

```python
# tools/system/skill_manager.py
from pathlib import Path
import yaml
import json

class SkillManager:
    """Manage Atlas skills"""

    def __init__(self, skills_dir: Path = None):
        self.skills_dir = skills_dir or Path("/Users/printer/atlas/skills")
        self.lock_file = self.skills_dir / ".skilllock.json"

    def list_skills(self):
        """List all installed skills"""
        skills = []
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            config = skill_dir / "config.yaml"

            if not skill_md.exists():
                continue

            metadata = {}
            if config.exists():
                metadata = yaml.safe_load(config.read_text())

            skills.append({
                "name": skill_dir.name,
                "path": str(skill_dir),
                "version": metadata.get("version", "0.0.0"),
                "summary": metadata.get("summary", "No summary"),
                "enabled": metadata.get("enabled", True)
            })

        return skills

    def get_skill(self, skill_name: str):
        """Get skill details"""
        skill_dir = self.skills_dir / skill_name

        if not skill_dir.exists():
            return None

        skill_md = skill_dir / "SKILL.md"
        config = skill_dir / "config.yaml"

        metadata = {}
        if config.exists():
            metadata = yaml.safe_load(config.read_text())

        return {
            "name": skill_name,
            "path": str(skill_dir),
            "description": skill_md.read_text() if skill_md.exists() else "",
            "version": metadata.get("version", "0.0.0"),
            "summary": metadata.get("summary", ""),
            "tools": list((skill_dir / "tools").glob("*.py")) if (skill_dir / "tools").exists() else [],
            "goals": list((skill_dir / "goals").glob("*.md")) if (skill_dir / "goals").exists() else [],
            "enabled": metadata.get("enabled", True)
        }

    def enable_skill(self, skill_name: str):
        """Enable a skill"""
        config_path = self.skills_dir / skill_name / "config.yaml"
        if config_path.exists():
            config = yaml.safe_load(config_path.read_text())
            config["enabled"] = True
            config_path.write_text(yaml.dump(config))

    def disable_skill(self, skill_name: str):
        """Disable a skill"""
        config_path = self.skills_dir / skill_name / "config.yaml"
        if config_path.exists():
            config = yaml.safe_load(config_path.read_text())
            config["enabled"] = False
            config_path.write_text(yaml.dump(config))
```

**CLI:**
```bash
# List skills
python tools/system/skill_manager.py list

# Show skill details
python tools/system/skill_manager.py info bambu-print-tracking

# Enable/disable skill
python tools/system/skill_manager.py enable telegram-bot
python tools/system/skill_manager.py disable browser-automation
```

---

## 🍓 Raspberry Pi Deployment: Always-On Personal AI

### **What OpenClaw Does**

OpenClaw has a **gateway architecture** that separates:
- **Gateway** (server that runs 24/7)
- **Nodes** (clients that connect to gateway)

This means you can run the gateway on a **Raspberry Pi** ($35-80 one-time cost) instead of always-on Mac.

### **Architecture**

```
┌─────────────────────┐
│   Raspberry Pi 4    │  ← Gateway (always on, $55)
│   (2GB RAM, headless)│
│                     │
│   - OpenClaw daemon │
│   - Telegram bot    │
│   - Scheduled tasks │
│   - Tool execution  │
└──────────┬──────────┘
           │
           ├──→ Telegram (users send messages)
           ├──→ WhatsApp (multi-channel)
           ├──→ Mac (for heavy tasks via SSH)
           └──→ Claude API (models in cloud)
```

**Benefits:**
1. **Always-on** — Pi runs 24/7 without keeping Mac awake
2. **Low power** — ~5W vs Mac's ~50W ($40/year savings)
3. **Cheap** — $55 Pi 4 (4GB) vs $600+ Mac Mini
4. **Dedicated** — No interference with main work machine
5. **Reliable** — Fewer moving parts, solid-state storage

**Cost Comparison:**
| Setup | One-Time | Monthly | Yearly Total |
|-------|----------|---------|--------------|
| Pi 4 (4GB) | $55 | $0 | $55 (year 1), $5/yr power |
| Pi 5 (8GB) | $80 | $0 | $80 (year 1), $5/yr power |
| DigitalOcean | $0 | $6 | $72/year |
| Mac Mini Always-On | $600 | $4 power | $648/year |

**Break-even:** Pi pays for itself vs cloud VPS in ~8-10 months.

### **Atlas on Raspberry Pi**

**Current Problem:**
- Atlas runs on your Mac
- Mac must be awake 24/7 for scheduled tasks
- High power consumption (~50W)
- Can't close laptop and go mobile

**Pi Solution:**
- **Move Atlas to Pi** — Runs 24/7 on cheap hardware
- **Keep Mac for heavy tasks** — SSH tunnel for development
- **Low power** — $5/year electricity
- **Portable** — Small, silent, can run anywhere

### **Implementation Guide**

#### **1. Hardware**

**Recommended:**
- Raspberry Pi 4 or 5 (4GB RAM minimum)
- 32GB+ microSD card OR USB SSD (better performance)
- Official Pi power supply
- Ethernet cable (more reliable than WiFi)

**Cost:** ~$55-80 total

#### **2. Software Setup**

```bash
# Flash Raspberry Pi OS Lite (64-bit)
# Use Raspberry Pi Imager: https://www.raspberrypi.com/software/

# SSH into Pi
ssh pi@raspberrypi.local

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y git curl build-essential python3 python3-pip

# Set timezone
sudo timedatectl set-timezone America/Chicago

# Add swap (important for 2-4GB RAM)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Reduce swappiness (optimize for low RAM)
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Clone Atlas
cd ~
git clone https://github.com/yourusername/atlas.git  # Or rsync from Mac
cd atlas

# Install Python dependencies
pip3 install -r requirements.txt  # Create this if missing

# Copy credentials
# Use scp to copy envchain data OR setup .env file
scp ~/.env pi@raspberrypi.local:~/atlas/.env
```

#### **3. Setup Systemd Service**

```bash
# Create systemd service for Atlas
sudo tee /etc/systemd/system/atlas.service > /dev/null <<EOF
[Unit]
Description=Atlas Agentic System
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/atlas
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/python3 /home/pi/atlas/tools/system/daemon.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable atlas
sudo systemctl start atlas

# Check status
sudo systemctl status atlas

# View logs
journalctl -u atlas -f
```

#### **4. Migrate Scheduled Tasks**

All your cron jobs can run on the Pi:

```bash
# Copy crontab from Mac
# On Mac:
crontab -l > /tmp/atlas_cron.txt
scp /tmp/atlas_cron.txt pi@raspberrypi.local:/tmp/

# On Pi:
crontab /tmp/atlas_cron.txt
crontab -l  # Verify
```

All your launchd jobs (daily_brief, watchdog, etc.) can run on Pi via cron since Pi doesn't need macOS Keychain.

#### **5. Remote Access**

**Option A: SSH Tunnel (Simple)**
```bash
# From Mac, tunnel to Pi
ssh -L 18789:localhost:18789 pi@raspberrypi.local

# Access Pi's services from Mac
curl http://localhost:18789/health
```

**Option B: Tailscale (Best)**
```bash
# On Pi
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# On Mac
# Install Tailscale app
# Connect to same network

# Access Pi from anywhere
curl http://raspberrypi.tailnet.ts.net:18789/health
```

#### **6. Database Migration**

Move SQLite databases to Pi:

```bash
# From Mac
rsync -av ~/atlas/data/ pi@raspberrypi.local:~/atlas/data/

# Or for continuous sync
# Setup bidirectional sync with Syncthing or rsync cron
```

**For PostgreSQL databases** (LegalKanban, etc.), no migration needed — Pi connects to remote DB.

### **What Runs on Pi vs Mac**

**Pi (24/7):**
- Daily brief (6 AM)
- Watchdog (monitoring)
- Telegram bot
- Bambu print tracking
- LegalKanban sync
- All scheduled briefings/reports
- Health monitoring
- Backup tasks

**Mac (when needed):**
- Heavy browser automation (if needed)
- Video processing (if added later)
- Development/testing
- Large file operations

**Both:**
- Can SSH from Pi to Mac for heavy tasks
- Pi delegates, Mac executes, Pi reports results

### **Performance Expectations**

**Raspberry Pi 4 (4GB) Benchmarks:**
- Python script startup: ~0.5s
- SQLite query: <10ms
- API call: Same as Mac (network-bound)
- Telegram bot response: ~1-2s
- Daily brief generation: ~5-10s

**Good enough for:**
✅ Scheduled briefings
✅ Telegram bot
✅ Database queries
✅ API orchestration
✅ File operations
✅ Most Atlas workflows

**Too slow for:**
❌ Heavy browser automation (100+ tabs)
❌ Video transcoding
❌ Large ML model inference

---

## 🎯 Implementation Roadmap

### **Phase 1: Skills System (Weekend Project)**

**Goal:** Make Atlas tools more modular and portable

**Steps:**
1. Create `skills/` directory structure
2. Migrate one tool bundle (start with Bambu)
3. Write SKILL.md for that bundle
4. Test loading skill at runtime
5. Build `skill_manager.py` CLI
6. Document migration guide

**Result:** Skills are self-contained, versioned, and portable

---

### **Phase 2: Raspberry Pi Deployment (1 Week)**

**Goal:** Move Atlas to always-on Pi hardware

**Steps:**
1. **Order hardware** (Pi 4 4GB + USB SSD)
2. **Flash and setup** (OS, swap, dependencies)
3. **Migrate Atlas** (clone repo, copy data, setup .env)
4. **Setup systemd service** (auto-start on boot)
5. **Migrate cron jobs** (all scheduled tasks)
6. **Setup Tailscale** (remote access)
7. **Test 48 hours** (verify all workflows work)
8. **Full cutover** (Pi becomes primary)

**Result:** Atlas runs 24/7 on $55 hardware, Mac is free

**Cost Savings:**
- Power: ~$40/year (Mac awake 24/7 vs Pi)
- Hardware: Break-even in 1 year vs cloud VPS
- Peace of mind: No more "did I leave my Mac on?"

---

### **Phase 3: ClawHub-Style Registry (Future)**

**Goal:** Share Atlas skills publicly (optional)

**Steps:**
1. Add versioning to skills (semver)
2. Create skill publish/install CLI
3. Setup GitHub releases as "registry"
4. Document skill format standard
5. Create example skills for others

**Result:** Atlas skills can be shared and reused by others

---

## 📊 Skills System: Practical Examples

### **Example 1: Bambu Print Tracking Skill**

```yaml
# skills/bambu-print-tracking/config.yaml
name: bambu-print-tracking
version: 1.2.0
summary: "Track 3D print completions and log filament usage"
author: Tony
dependencies:
  - python: ">=3.9"
  - pip:
    - sqlite3
enabled: true
cron_jobs:
  - schedule: "*/5 * * * *"
    script: "tools/bambu_buddy_watcher.py"
    description: "Watch BambuBuddy database for new prints"
environment:
  - TELEGRAM_BOT_TOKEN  # Required from envchain
```

```markdown
# skills/bambu-print-tracking/SKILL.md
---
summary: "Track 3D print completions and log filament usage"
read_when:
  - User mentions 3D printing, Bambu, or filament
  - Print completion notifications
  - Filament inventory questions
---

# Bambu Print Tracking

Tracks 3D print completions from BambuBuddy database and logs filament usage to JeevesUI.

## How It Works

1. **Watcher** — `bambu_buddy_watcher.py` polls BambuBuddy SQLite DB every 5 min
2. **Prompt Generation** — Creates prompt with filament auto-detection
3. **Telegram Prompt** — Sends to user for confirmation
4. **Reply Handler** — Parses reply and logs to JeevesUI
5. **Confirmation** — Sends success message

## Supported Reply Formats

- Single color: `6, 39g, Tony`
- Multi-color: `5, 42g + 8, 18g, Tony`
- Prefilled: `Tony` (uses auto-detected values)

## Data Flow

```
BambuBuddy DB → Pending Prompts → Telegram → Reply → JeevesUI
```

## Maintenance

- State file: `data/bambu_buddy_last_id.txt`
- Pending prompts: `memory/bambu-pending-prompts.md`
- Last reply cache: `memory/bambu-last-reply.txt`
```

**Benefits:**
- **Self-documenting** — SKILL.md explains everything
- **Portable** — Copy folder to another system
- **Versioned** — Track changes over time
- **Configurable** — config.yaml for settings

---

### **Example 2: LegalKanban Sync Skill**

```yaml
# skills/legalkanban-sync/config.yaml
name: legalkanban-sync
version: 2.1.0
summary: "Bidirectional task sync with LegalKanban case management"
author: Tony
dependencies:
  - python: ">=3.9"
  - pip:
    - psycopg2
    - python-dateutil
enabled: true
environment:
  - LEGALKANBAN  # PostgreSQL connection string
```

```markdown
# skills/legalkanban-sync/SKILL.md
---
summary: "Bidirectional task sync with LegalKanban case management"
read_when:
  - User asks about case tasks, deadlines, or assignments
  - Questions about LegalKanban integration
  - Task completion or due date changes
---

# LegalKanban Sync

Syncs tasks between LegalKanban PostgreSQL database and Tony Tasks.md in Obsidian.

## Features

- **FROM LegalKanban:** Pull incomplete tasks for user 1
- **TO LegalKanban:** Push completions and due date changes
- **Format:** `- [ ] Title 🔴/🟡 (Case #123) 📅 YYYY-MM-DD [LK-456]`
- **Frequency:** Hourly via launchd

## Task Lifecycle

1. **New task in LegalKanban** → Appears in Tony Tasks.md
2. **Check off in Tony Tasks** → Marked complete in LegalKanban
3. **Edit due date in Tony Tasks** → Updated in LegalKanban
4. **Completed tasks** → Auto-removed from Tony Tasks

## Database Schema

See `docs/LEGALKANBAN_SYNC.md` for full schema documentation.
```

---

## 🚀 Quick Wins

### **This Weekend: Skills Prototype**

1. **Create skills/ directory structure**
2. **Migrate Bambu tools to first skill**
3. **Write SKILL.md and config.yaml**
4. **Test loading and execution**
5. **Build basic CLI for list/info commands**

**Time estimate:** 3-4 hours

---

### **Next Week: Raspberry Pi Setup**

1. **Order Pi 4 (4GB) + USB SSD** (~$70 total)
2. **Flash OS, install dependencies**
3. **Clone Atlas, copy credentials**
4. **Setup systemd service**
5. **Migrate cron jobs**
6. **Test for 48 hours**
7. **Full cutover to Pi**

**Time estimate:** 1 evening + 2 days testing

---

## 📚 Key Takeaways

**Skills System Benefits:**
- ✅ **Portable** — Move tools between systems
- ✅ **Versioned** — Track changes over time
- ✅ **Self-documenting** — SKILL.md always current
- ✅ **Shareable** — Can export/import easily
- ✅ **Testable** — Isolated test suites

**Raspberry Pi Benefits:**
- ✅ **Always-on** — No more "is Mac awake?"
- ✅ **Cheap** — $55-80 one-time, $5/year power
- ✅ **Reliable** — Fewer parts, solid-state
- ✅ **Dedicated** — No interference with work Mac
- ✅ **Portable** — Small, silent, can run anywhere

**Atlas Gets:**
1. **Modular architecture** (skills system)
2. **24/7 operation** (Raspberry Pi)
3. **Lower costs** (no cloud VPS needed)
4. **Better reliability** (dedicated hardware)
5. **Easier maintenance** (self-contained skills)

---

## ✅ Recommended Action Plan

**Priority 1: Raspberry Pi (HIGH VALUE, LOW COMPLEXITY)**

Biggest bang for buck — move Atlas to always-on Pi hardware.

**Steps:**
1. Order Pi 4 (4GB) + accessories ($70)
2. Setup this weekend (4-5 hours)
3. Migrate gradually (test 48 hours before full cutover)
4. Keep Mac as development machine

**Result:** Atlas runs 24/7 on $55 hardware, Mac is liberated.

---

**Priority 2: Skills System (MEDIUM VALUE, MEDIUM COMPLEXITY)**

Make Atlas tools more modular and portable.

**Steps:**
1. Create skills/ directory
2. Migrate one tool bundle (Bambu)
3. Write skill_manager.py CLI
4. Document standard format

**Result:** Skills are self-contained, versioned, and shareable.

---

**Priority 3: ClawHub-Style Registry (LOW VALUE, HIGH COMPLEXITY)**

Only if you want to share skills publicly — defer until later.

---

## 🎯 Final Recommendation

**Do this week:**
1. ✅ **Order Raspberry Pi 4 (4GB) + USB SSD** — $70 investment
2. ✅ **Setup Pi as Atlas host** — 1 evening work
3. ✅ **Test 48 hours** — Verify all workflows
4. ✅ **Full cutover** — Pi becomes primary

**Do next sprint:**
1. ✅ **Implement skills system** — Make tools modular
2. ✅ **Document skill format** — Enable sharing

**This gives you:**
- 24/7 always-on Atlas for $55 hardware
- Modular, portable tool architecture
- Foundation for future enhancements

**The path is clear: Deploy to Pi first, then modularize.**
