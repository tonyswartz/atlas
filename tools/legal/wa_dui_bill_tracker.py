#!/usr/bin/env python3
"""
WA DUI Bill Tracker - Tracks specific bills and monitors for updates.
Runs daily and sends Telegram alerts for bill activity.
Creates daily log entries when bills are updated.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Load .env so cron runs have TELEGRAM_BOT_TOKEN
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

# Configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "8241581699"
STATE_FILE = "/Users/printer/atlas/data/wa_dui_bill_tracker_state.json"
BILL_LOGS_DIR = "/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Case Law/Legislation/Bill Logs"

BASE_URL = "https://leg.wa.gov"


def load_state():
    """Load previously tracked bills from state file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"tracked_bills": {}, "last_check": None}


def save_state(state):
    """Save tracked bills to state file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_bill_status(bill_number):
    """Get the current status and history of a bill."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })
    
    # Try app.leg.wa.gov bill summary
    try:
        url = f"https://app.leg.wa.gov/billsummary?BillNumber={bill_number}&Year=2025"
        response = session.get(url, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract current status
            status_elem = soup.find(string=re.compile(r'Spassed|Passed|Failed|Referred'))
            status = status_elem.strip() if status_elem else "Unknown"
            
            # Extract bill description
            desc_elem = soup.find(string=re.compile(r'Concerning|impaired|DUI'))
            description = desc_elem.strip() if desc_elem else ""
            
            return {
                "bill_number": bill_number,
                "url": url,
                "accessible": True,
                "status": status,
                "description": description,
                "checked_at": datetime.now().isoformat()
            }
    except Exception as e:
        print(f"  Error checking {bill_number}: {e}")
    
    return {
        "bill_number": bill_number,
        "url": f"https://app.leg.wa.gov/billsummary?BillNumber={bill_number}&Year=2025",
        "accessible": False,
        "status": "Could not verify",
        "checked_at": datetime.now().isoformat()
    }


def create_daily_log(date_str, updates):
    """Create a daily log entry for bill updates."""
    os.makedirs(BILL_LOGS_DIR, exist_ok=True)
    
    filename = f"{BILL_LOGS_DIR}/{date_str} Bill Updates.md"
    
    content = f"""---
date: "{date_str}"
type: bill-log
---

# WA DUI Bill Tracker - {date_str}

"""
    
    if not updates:
        content += "No updates today.\n"
    else:
        for update in updates:
            content += f"""## {update['bill_number']}

- **Status:** {update.get('status', 'N/A')}
- **URL:** {update.get('url', 'N/A')}
- **Change:** {update.get('change_type', 'Checked')}

"""
    
    content += f"\n---\n*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
    
    with open(filename, 'w') as f:
        f.write(content)
    
    return filename


def create_individual_bill_log(bill_number, update_info):
    """Create or update an individual bill log file."""
    os.makedirs(BILL_LOGS_DIR, exist_ok=True)
    
    filename = f"{BILL_LOGS_DIR}/{bill_number} Log.md"
    
    # Read existing or create new
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            content = f.read()
    else:
        content = f"""---
billNumber: {bill_number}
type: bill-log
---

# {bill_number} - Bill Log

## Summary
[Add bill summary here]

## Status History

"""
    
    # Add new entry
    date_str = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H:%M')
    
    new_entry = f"""### {date_str} {time_str}
- **Status:** {update_info.get('status', 'N/A')}
- **Change:** {update_info.get('change_type', 'Status check')}
- **Notes:** {update_info.get('notes', 'No additional notes')}

"""
    
    # Insert after "## Status History" header
    marker = "## Status History\n"
    if marker in content:
        content = content.replace(marker, marker + new_entry)
    else:
        content += new_entry
    
    with open(filename, 'w') as f:
        f.write(content)
    
    return filename


def send_telegram_alert(new_bills, updated_bills):
    """Send Telegram alert for bill updates."""
    if not TELEGRAM_TOKEN:
        print("No Telegram token configured")
        return
    
    if not new_bills and not updated_bills:
        print("No updates to report")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    message = "📋 *WA DUI Bill Tracker Update*\n\n"
    
    if new_bills:
        message += f"🆕 *New Bills ({len(new_bills)}):*\n"
        for bill in new_bills:
            message += f"• {bill['bill_number']}: {bill.get('status', 'Unknown')}\n"
        message += "\n"
    
    if updated_bills:
        message += f"🔄 *Updates ({len(updated_bills)}):*\n"
        for bill in updated_bills:
            message += f"• {bill['bill_number']}: {bill.get('status', 'Unknown')}\n"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"Alert sent successfully")
        else:
            print(f"Failed to send alert: {response.text}")
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")


def main():
    """Main tracking function."""
    date_str = datetime.now().strftime('%Y-%m-%d')
    print(f"[{datetime.now()}] Starting WA DUI bill check...")
    
    state = load_state()
    
    if not state["tracked_bills"]:
        print("  No bills to track. Add bills using: python3 scripts/wa_dui_bill_tracker.py add <bill_number>")
        print("  Example: python3 scripts/wa_dui_bill_tracker.py add 6045")
        return
    
    updates = []
    
    for bill_num in state["tracked_bills"]:
        print(f"  Checking: {bill_num}")
        status = get_bill_status(bill_num)
        
        old_status = state["tracked_bills"].get(bill_num, {})
        old_status_text = old_status.get("status", {})
        
        # Determine if there's a change
        new_status_text = status.get("status", "")
        change_type = "checked"
        notes = ""
        
        if not old_status:
            change_type = "New bill added to tracking"
            updates.append({
                "bill_number": bill_num,
                "status": new_status_text,
                "change_type": change_type,
                "notes": notes,
                "url": status.get("url", "")
            })
            state["tracked_bills"][bill_num] = {
                "first_seen": datetime.now().isoformat(),
                "status": new_status_text,
                "last_check": datetime.now().isoformat()
            }
        elif old_status_text != new_status_text:
            change_type = f"Status changed: {old_status_text} → {new_status_text}"
            notes = f"Previous: {old_status_text}"
            updates.append({
                "bill_number": bill_num,
                "status": new_status_text,
                "change_type": change_type,
                "notes": notes,
                "url": status.get("url", "")
            })
            state["tracked_bills"][bill_num]["status"] = new_status_text
            state["tracked_bills"][bill_num]["last_check"] = datetime.now().isoformat()
        
        # Create/update individual bill log
        if change_type != "checked" or not old_status:
            try:
                create_individual_bill_log(bill_num, {
                    "status": new_status_text,
                    "change_type": change_type,
                    "notes": notes
                })
            except Exception as e:
                print(f"  Could not create bill log: {e}")
    
    # Create daily log
    try:
        daily_log = create_daily_log(date_str, updates)
        print(f"  Daily log: {daily_log}")
    except Exception as e:
        print(f"  Could not create daily log: {e}")
    
    # Send alerts
    new_bills = [u for u in updates if "New bill" in u.get("change_type", "")]
    updated_bills = [u for u in updates if "New bill" not in u.get("change_type", "")]
    
    if new_bills or updated_bills:
        print(f"  {len(new_bills)} new, {len(updated_bills)} updated")
        send_telegram_alert(new_bills, updated_bills)
    else:
        print("  No updates")
    
    # Update state
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    
    print(f"[{datetime.now()}] Check complete")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "add" and len(sys.argv) > 2:
            # Add a bill to track
            state = load_state()
            bill_num = sys.argv[2]
            state["tracked_bills"][bill_num] = {
                "added": datetime.now().isoformat(),
                "added_by": "cli"
            }
            save_state(state)
            print(f"Added bill {bill_num} to tracking list")
        elif sys.argv[1] == "list":
            state = load_state()
            print("Tracked bills:")
            for bill_num in state["tracked_bills"]:
                print(f"  {bill_num}")
        elif sys.argv[1] == "remove" and len(sys.argv) > 2:
            state = load_state()
            bill_num = sys.argv[2]
            if bill_num in state["tracked_bills"]:
                del state["tracked_bills"][bill_num]
                save_state(state)
                print(f"Removed bill {bill_num} from tracking list")
            else:
                print(f"Bill {bill_num} not found in tracking list")
        else:
            print("Usage:")
            print("  python3 wa_dui_bill_tracker.py           # Run check")
            print("  python3 wa_dui_bill_tracker.py add 6045  # Add bill to track")
            print("  python3 wa_dui_bill_tracker.py list      # List tracked bills")
            print("  python3 wa_dui_bill_tracker.py remove 6045  # Remove bill")
    else:
        main()
