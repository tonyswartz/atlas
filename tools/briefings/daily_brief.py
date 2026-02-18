#!/usr/bin/env python3
"""
Tony's 6am Daily Brief Generator
Outputs formatted brief to stdout for delivery + prepends to Tony Digest.md
"""

import subprocess
import sys
import json
import re
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import urllib.request
import urllib.parse
import ssl

# Config
ZIPCODE = "98926"
TZ = ZoneInfo("America/Los_Angeles")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OBSIDIAN_VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
REMINDERS_FILE = OBSIDIAN_VAULT / "Tony Reminders.md"
TASKS_FILE = OBSIDIAN_VAULT / "Tony Tasks.md"
KANBAN_FILE = OBSIDIAN_VAULT / "Tony Kanban.md"
DIGEST_FILE = OBSIDIAN_VAULT / "Tony Digest.md"
ACCOUNT = "tswartz@gmail.com"
COURTS_URL = "https://www.courts.wa.gov/opinions/index.cfm?fa=opinions.recent"
CASE_LAW_DIR = OBSIDIAN_VAULT / "Case Law/WA Criminal"
BRIEFS_DIR = OBSIDIAN_VAULT / "Research/Briefs"
STATE_FILE = OBSIDIAN_VAULT / "Research/.case_law_seen.json"
SUMMARY_CACHE_FILE = REPO_ROOT / "data" / "case_law_summaries.json"

# MiniMax config (coding plan)
MINIMAX_BASE_URL = "https://api.minimax.io/v1"
MINIMAX_MODEL = "MiniMax-M2.5"


def get_weather() -> str:
    """Fetch weather from Open-Meteo (reliable) with wttr.in fallback for emoji"""
    import time

    # Ellensburg, WA coordinates
    lat, lon = 47.0379, -120.5476

    # WMO weather codes to emoji/description
    wmo_codes = {
        0: ("☀️", "Clear"), 1: ("🌤️", "Mainly clear"), 2: ("⛅", "Partly cloudy"), 3: ("☁️", "Overcast"),
        45: ("🌫️", "Foggy"), 48: ("🌫️", "Icy fog"),
        51: ("🌧️", "Light drizzle"), 53: ("🌧️", "Drizzle"), 55: ("🌧️", "Heavy drizzle"),
        61: ("🌧️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
        71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"), 75: ("🌨️", "Heavy snow"),
        77: ("🌨️", "Snow grains"), 80: ("🌧️", "Rain showers"), 81: ("🌧️", "Moderate showers"),
        82: ("🌧️", "Heavy showers"), 85: ("🌨️", "Snow showers"), 86: ("🌨️", "Heavy snow showers"),
        95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Thunderstorm w/ hail"), 99: ("⛈️", "Severe thunderstorm")
    }

    # Try Open-Meteo with retry logic for SSL/network issues
    url = (f"https://api.open-meteo.com/v1/forecast?"
           f"latitude={lat}&longitude={lon}"
           f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
           f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
           f"&timezone=America/Los_Angeles&forecast_days=1")

    # Create SSL context that's more resilient to connection issues
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED

    # Retry logic: 3 attempts with exponential backoff (same pattern as Telegram send)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20, context=ssl_context) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            current = data.get("current", {})
            daily = data.get("daily", {})

            temp = current.get("temperature_2m", "?")
            humidity = current.get("relative_humidity_2m", "?")
            wind = current.get("wind_speed_10m", "?")
            code = current.get("weather_code", 0)

            high = daily.get("temperature_2m_max", ["?"])[0]
            low = daily.get("temperature_2m_min", ["?"])[0]
            precip_chance = daily.get("precipitation_probability_max", ["?"])[0]

            emoji, desc = wmo_codes.get(code, ("🌡️", "Unknown"))

            weather = f"{emoji} {desc}, {temp:.0f}°F (High {high:.0f}° / Low {low:.0f}°) | Humidity {humidity}% | Wind {wind:.0f} mph"
            if precip_chance and precip_chance > 20:
                weather += f" | {precip_chance}% chance precip"

            return weather
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff: 1s, 2s (only retry on transient errors)
                time.sleep(2 ** attempt)
                continue
            # If all retries fail, fall through to wttr.in fallback
            break

    # Fallback to wttr.in (uses curl with its own SSL handling)
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "10", f"wttr.in/{ZIPCODE}?format=%c+%t"],
            capture_output=True, text=True, timeout=15
        )
        if result.stdout.strip():
            return result.stdout.strip()
        # If wttr.in returns empty, return generic message
        return "Weather temporarily unavailable"
    except Exception:
        return "Weather temporarily unavailable"


def get_reminders() -> dict:
    """Parse Tony Reminders.md into sections"""
    sections = {"Shopping": [], "Today": [], "Later This Week": [], "Later This Month": [], "Later Later": []}
    current_section = None
    
    try:
        content = REMINDERS_FILE.read_text()
        for line in content.splitlines():
            line = line.strip()
            # Check for section headers
            for section in sections.keys():
                if line.lower() == f"[{section.lower()}]":
                    current_section = section
                    break
            else:
                # Add non-empty bullet items to current section
                if current_section and line.startswith("- ") and len(line) > 2:
                    item = line[2:].strip()
                    if item and not item.lower().startswith("[x]"):
                        sections[current_section].append(item)
        return sections
    except Exception as e:
        return {"error": str(e)}


def get_tasks() -> list[dict]:
    """Parse Tony Tasks.md for unchecked tasks (same source as JeevesUI kanban_read).
    Returns list of {"due_date": YYYY-MM-DD or None, "line": display text} sorted: due today first, then by due date, then no date.
    """
    today_dt = datetime.now(TZ).date()
    date_re = re.compile(r"📅 (\d{4}-\d{2}-\d{2})")
    lk_tag_re = re.compile(r"\s*\[LK-\d+\]\s*$")
    tasks: list[dict] = []

    try:
        if not TASKS_FILE.exists():
            return []
        content = TASKS_FILE.read_text()
        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("- [ ]"):
                continue
            # Strip checkbox: "- [ ] rest"
            rest = line[5:].strip()
            if not rest:
                continue
            # Drop [LK-123] from display
            rest = lk_tag_re.sub("", rest).strip()
            due_str = None
            m = date_re.search(rest)
            if m:
                due_str = m.group(1)
            try:
                due_dt = datetime.strptime(due_str, "%Y-%m-%d").date() if due_str else None
            except ValueError:
                due_dt = None
            tasks.append({"due_date": due_str, "due_dt": due_dt, "line": rest})
    except Exception:
        return []

    # Sort: due today first, then overdue, then future by date, then no date
    def key(t):
        d = t.get("due_dt")
        if d is None:
            return (2, None)
        if d == today_dt:
            return (0, d)
        if d < today_dt:
            return (1, d)
        return (2, d)

    tasks.sort(key=key)
    return tasks


def get_calendar() -> list:
    """Fetch today's calendar events from all calendars"""
    try:
        result = subprocess.run(
            ["/opt/homebrew/bin/gog", "calendar", "list", "--today", "--all", "--account", ACCOUNT, "--json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            err = (result.stderr or "").strip() or f"gog exited {result.returncode}"
            return [f"Calendar error: {err}"]

        data = json.loads(result.stdout) if result.stdout.strip() else {}
        events = data.get("events", []) if isinstance(data, dict) else data
        today = datetime.now(TZ).date()
        
        formatted = []
        for ev in events:
            summary = ev.get("summary", "No title")
            start_str = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date")
            
            if not start_str:
                continue
            
            # Parse start time
            if "T" in start_str:
                # Has time component
                try:
                    if start_str.endswith("Z"):
                        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    else:
                        start_dt = datetime.fromisoformat(start_str)
                    start_local = start_dt.astimezone(TZ)
                    
                    # Only include if it's actually today
                    if start_local.date() != today:
                        continue
                    
                    time_str = start_local.strftime("%-I:%M %p")
                    formatted.append((start_local, f"{time_str} — {summary}"))
                except:
                    formatted.append((datetime.min.replace(tzinfo=TZ), f"{summary}"))
            else:
                # All-day event
                try:
                    event_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                    if event_date != today:
                        continue
                    formatted.append((datetime.min.replace(tzinfo=TZ), f"All day — {summary}"))
                except:
                    pass
        
        # Sort by time
        formatted.sort(key=lambda x: x[0])
        return [item[1] for item in formatted]
    except Exception as e:
        return [f"Calendar error: {e}"]


def fetch_pdf_text(url: str) -> str:
    """Download a PDF and extract text via pdftotext."""
    import tempfile
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "30", "-L", url],
            capture_output=True, timeout=35
        )
        if not result.stdout:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(result.stdout)
            tmp_path = tmp.name
        try:
            text_result = subprocess.run(
                ["pdftotext", tmp_path, "-"],
                capture_output=True, text=True, timeout=30
            )
            return text_result.stdout
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except Exception:
        return ""


def _load_summary_cache() -> dict:
    """Load cached case summaries from JSON file."""
    if not SUMMARY_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(SUMMARY_CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_summary_cache(cache: dict):
    """Save case summaries cache to JSON file."""
    try:
        SUMMARY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        print(f"Warning: Could not save summary cache: {e}", file=sys.stderr)


def _get_minimax_api_key() -> str:
    """Get MiniMax API key from envchain or .env."""
    # Try environment variable first (set by envchain or .env)
    key = os.environ.get("MINIMIAX_CODING", "")
    if key:
        return key

    # Try loading from .env if not already loaded
    from dotenv import load_dotenv
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        return os.environ.get("MINIMIAX_CODING", "")

    return ""


def summarize_case_with_llm(text: str, case_name: str, case_url: str) -> str:
    """Generate a concise summary of the case using MiniMax LLM.

    Uses cached summaries when available to avoid redundant API calls.
    """
    if not text or len(text) < 200:
        return ""

    # Check cache first (keyed by URL to handle duplicate case names)
    cache = _load_summary_cache()
    cache_key = case_url if case_url else case_name
    if cache_key in cache:
        return cache[cache_key]

    # Get API key
    api_key = _get_minimax_api_key()
    if not api_key:
        print(f"Warning: MINIMIAX_CODING API key not found, skipping summary for {case_name}", file=sys.stderr)
        return ""

    # Truncate text to ~8000 chars (rough token limit for MiniMax context)
    if len(text) > 8000:
        text = text[:8000]

    # Build prompt
    prompt = f"""Summarize this Washington criminal appellate court opinion in 2-3 sentences. Focus on:
1. What crime/charge was involved
2. The key legal issue the court addressed
3. The court's holding/decision

Case: {case_name}

Opinion text:
{text}

Provide ONLY the summary, no preamble."""

    try:
        # Use OpenAI-compatible API (MiniMax supports this)
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=MINIMAX_BASE_URL,
            timeout=30.0
        )

        response = client.chat.completions.create(
            model=MINIMAX_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,  # Increased to handle verbose <think> blocks (200-400 tokens) + summary (100-200 tokens)
            temperature=0.3
        )

        summary = response.choices[0].message.content.strip()

        # Strip <think> tags if present (MiniMax includes these)
        summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()

        # Cache the summary
        cache[cache_key] = summary
        _save_summary_cache(cache)

        return summary

    except Exception as e:
        print(f"Warning: Could not generate summary for {case_name}: {e}", file=sys.stderr)
        return ""


def get_case_law() -> list:
    """Fetch recent WA appellate opinions with holdings"""
    try:
        req = urllib.request.Request(COURTS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
        
        # Consider cases from the last 7 days (courts.wa.gov lists "last 14 days")
        today = datetime.now(TZ).date()
        cutoff = today - timedelta(days=7)
        
        # Simple regex to find opinion entries with dates
        date_pattern = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s+(\d{1,2}),\s+(\d{4})"
        cases = []
        lines = html.split("\n")
        current_date = None
        
        for i, line in enumerate(lines):
            # Check for date
            date_match = re.search(date_pattern, line)
            if date_match:
                month_str, day, year = date_match.groups()
                months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
                try:
                    current_date = datetime(int(year), months[month_str], int(day)).date()
                except:
                    current_date = None
            
            # Look for State v. cases (criminal) within the window
            if current_date and current_date >= cutoff:
                if "State" in line and " v. " in line.lower():
                    # Extract case name
                    case_match = re.search(r"(State\s+(?:of\s+Washington,?\s+)?(?:Respondent\s+)?[Vv]\.?\s+[^<]+)", line, re.IGNORECASE)
                    if case_match:
                        case_name = case_match.group(1).strip()
                        case_name = re.sub(r"\s+", " ", case_name)
                        # Look for PDF link nearby (filenames may contain spaces)
                        line_pos = html.find(line)
                        pdf_match = re.search(r'/opinions/pdf/[^"]+\.pdf', html[max(0, line_pos-500):line_pos+500]) if line_pos >= 0 else None
                        pdf_url = f"https://www.courts.wa.gov{urllib.parse.quote(pdf_match.group(0), safe='/')}" if pdf_match else None
                        
                        cases.append({
                            "name": case_name[:80],
                            "date": current_date.strftime("%b %d"),
                            "url": pdf_url
                        })
        
        # Dedupe by case name
        seen = set()
        unique_cases = []
        for c in cases:
            if c["name"] not in seen:
                seen.add(c["name"])
                unique_cases.append(c)

        unique_cases = unique_cases[:10]

        # Generate AI summaries from PDFs
        for case in unique_cases:
            if case.get("url"):
                pdf_text = fetch_pdf_text(case["url"])
                case["holding"] = summarize_case_with_llm(pdf_text, case["name"], case["url"])

        return unique_cases
    except Exception as e:
        return []


def get_suggested_win() -> str:
    """Get a suggested win from Tony Kanban"""
    try:
        content = KANBAN_FILE.read_text()
        # Look for unchecked items in "Things to Do" section
        in_todo = False
        for line in content.splitlines():
            if "Things to Do" in line or "## To" in line:
                in_todo = True
                continue
            if in_todo and line.startswith("- [ ]"):
                item = line[5:].strip()
                if item:
                    return item
        return "Review and clear one small task"
    except:
        return "Review and clear one small task"


def get_motivational_quote() -> str:
    """Get a motivational quote relevant to Tony's life (hockey, law, family, music)"""
    import random
    
    quotes = [
        # Hockey-themed
        "The hardest work happens in the off-season. What you do when no one's watching defines what you do when everyone is.",
        "You miss 100% of the shots you don't take. — Wayne Gretzky",
        "The crease is crowded, but opportunity favors the relentless.",
        "Good teams win games. Great teams win championships. Elite teams do it every night.",
        # Law/Court
        "In the courtroom, preparation meets opportunity. Be prepared.",
        "The best lawyers aren't those who win every case, but who leave no stone unturned for their client.",
        "Justice delayed is not always justice denied—sometimes it's justice perfected.",
        # Work/Grind
        "Excellence isn't a destination, it's a daily decision. Make it today.",
        "Your reputation is built in the quiet moments when no one is grading.",
        "The gap between good and great is measured in the reps no one sees.",
        # Family/Dad life
        "Your kids won't remember the trophies on your shelf, but they'll remember the time you showed up.",
        "Being present is the most important case you'll ever win.",
        "The best inheritance you can give your children is your example, not your estate.",
        # Music/Creativity
        "Practice isn't about perfection. It's about progress, one measure at a time.",
        "The symphony starts with a single note. Start yours today.",
        "Creativity is intelligence having fun. — Albert Einstein",
        # General grit
        "Champions keep playing until they get it right. — Billie Jean King",
        "The only way to guarantee a loss is to not show up. Show up.",
        "Pressure is a privilege. It only exists when you have something worth playing for.",
    ]
    
    return random.choice(quotes)


def format_brief() -> str:
    """Generate the full brief"""
    now = datetime.now(TZ)
    date_str = now.strftime("%y-%m-%d")
    day_name = now.strftime("%a")
    
    # Advance recurring reminders before reading
    try:
        subprocess.run(
            [sys.executable, str(Path(__file__).parent / "reminder_add.py"), "--roll"],
            capture_output=True, cwd=str(Path(__file__).resolve().parent.parent.parent), timeout=15,
        )
    except Exception:
        pass

    # Gather data
    weather = get_weather()
    reminders = get_reminders()
    calendar = get_calendar()
    case_law = get_case_law()
    suggested_win = get_suggested_win()
    
    # Only show in brief cases not already in vault (avoid repeating same cases daily)
    seen_names: set[str] = set()
    if STATE_FILE.exists():
        try:
            seen_names = set(json.loads(STATE_FILE.read_text()))
        except Exception:
            pass
    new_cases_for_brief = [c for c in case_law if c["name"] not in seen_names]
    
    # Build brief
    lines = []
    lines.append(f"**Weather ({ZIPCODE}):** {weather}")
    lines.append("")
    
    # Reminders — overdue, today, and shopping
    lines.append("**Reminders:**")
    today_dt = now.date()
    date_tag_re = re.compile(r"\[(\d{2}-\d{2}-\d{2})\]")
    overdue = []
    for section_key in ["Shopping", "Today", "Later This Week", "Later This Month", "Later Later"]:
        for item in reminders.get(section_key) or []:
            m = date_tag_re.search(item)
            if m:
                try:
                    due = datetime.strptime(m.group(1), "%y-%m-%d").date()
                    if due < today_dt:
                        overdue.append(item)
                except ValueError:
                    pass
    today_items = reminders.get("Today") or []
    today_only = [i for i in today_items if i not in overdue]
    shopping_items = reminders.get("Shopping") or []
    any_reminders = False
    if overdue:
        for item in overdue:
            lines.append(f"• Overdue: {item}")
            any_reminders = True
    for item in today_only:
        lines.append(f"• Today: {item}")
        any_reminders = True
    if shopping_items:
        lines.append(f"• Shopping: {', '.join(shopping_items)}")
        any_reminders = True
    if not any_reminders:
        lines.append("• None")
    lines.append("")

    # Tasks (Tony Tasks.md — same source as JeevesUI)
    lines.append("**Tasks:**")
    tasks = get_tasks()
    today_dt_brief = now.date()
    today_tasks = [t for t in tasks if t.get("due_dt") == today_dt_brief]
    overdue_tasks = [t for t in tasks if t.get("due_dt") and t["due_dt"] < today_dt_brief]
    # Only show overdue and today tasks in daily brief
    shown = 0
    max_tasks = 15
    for item in overdue_tasks + today_tasks:
        if shown >= max_tasks:
            lines.append(f"• … and {len(overdue_tasks + today_tasks) - max_tasks} more (see Tony Tasks.md)")
            break
        prefix = ""
        if item.get("due_dt"):
            if item["due_dt"] < today_dt_brief:
                prefix = "Overdue: "
            elif item["due_dt"] == today_dt_brief:
                prefix = "Today: "
        lines.append(f"• {prefix}{item['line']}")
        shown += 1
    if not (overdue_tasks or today_tasks):
        lines.append("• None")
    lines.append("")
    
    # Calendar
    lines.append("**Calendar (today):**")
    if calendar:
        for event in calendar:
            lines.append(f"• {event}")
    else:
        lines.append("• No events scheduled")
    lines.append("")
    
    # Case Law
    lines.append("**Case Law:**")
    if new_cases_for_brief:
        for case in new_cases_for_brief:
            if case.get("url"):
                lines.append(f"• [{case['name']}]({case['url']}) ({case['date']})")
            else:
                lines.append(f"• *{case['name']}* ({case['date']})")
            if case.get("holding"):
                lines.append(f"  → {case['holding']}")
    else:
        lines.append("• No new criminal opinions in the last 7 days")
    lines.append("")
    
    # Suggested win
    lines.append(f"**Suggested win:** {suggested_win}")
    lines.append("")
    
    # Motivational quote
    quote = get_motivational_quote()
    lines.append(f"_{quote}_")
    
    brief_body = "\n".join(lines)
    
    # Format for digest file
    digest_header = f"## {date_str} ({day_name}) — 6:00am\n\n"
    digest_entry = digest_header + brief_body + "\n\n---\n\n"
    
    return brief_body, digest_entry, case_law


def update_digest(entry: str):
    """Prepend entry to Tony Digest.md"""
    try:
        current = DIGEST_FILE.read_text() if DIGEST_FILE.exists() else ""
        
        # Find where to insert (after the header line)
        header_end = current.find("---")
        if header_end > 0:
            # Insert after first ---
            new_content = current[:header_end+3] + "\n\n" + entry + current[header_end+3:].lstrip("\n")
        else:
            new_content = entry + current
        
        DIGEST_FILE.write_text(new_content)
    except Exception as e:
        print(f"Warning: Could not update digest: {e}", file=__import__("sys").stderr)


def save_to_obsidian(brief: str):
    """Save brief to Research/Briefs/YYYY-MM-DD.md"""
    try:
        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        file_path = BRIEFS_DIR / f"{today}.md"
        content = f"---\ndate: \"{today}\"\ntype: daily-brief\n---\n\n{brief}\n"
        file_path.write_text(content)
    except Exception as e:
        print(f"Warning: Could not save brief to Obsidian: {e}", file=__import__("sys").stderr)


def _md_to_html(text: str) -> str:
    """Convert the brief's markdown to Telegram-safe HTML.

    Order matters: extract markdown links into placeholders before HTML-escaping
    so that URLs aren't mangled by entity escaping.
    """
    import html as html_mod

    # 1. Pull out [text](url) links before escaping
    links: list[tuple[str, str]] = []
    def _stash_link(m: re.Match) -> str:
        links.append((m.group(1), m.group(2)))
        return f"\x00LINK{len(links) - 1}\x00"
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _stash_link, text)

    lines = text.split("\n")
    out = []
    for line in lines:
        line = html_mod.escape(line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"(?<!\*)\*(.+?)\*(?!\*)", r"<i>\1</i>", line)
        line = re.sub(r"_(.+?)_", r"<i>\1</i>", line)  # Also handle underscore italics
        out.append(line)
    result = "\n".join(out)

    # 2. Restore links as <a> tags (text was already escaped above)
    for i, (label, url) in enumerate(links):
        label_escaped = html_mod.escape(label)
        result = result.replace(f"\x00LINK{i}\x00", f'<a href="{url}">{label_escaped}</a>')

    return result


def send_telegram(text: str) -> bool:
    """Send the brief to Telegram via Bot API (HTML mode) with retry logic."""
    import os
    import time
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    # Send to Daily group
    chat_id = "-5254628791"
    if not token:
        print("Telegram send failed: TELEGRAM_BOT_TOKEN not found", file=__import__("sys").stderr)
        return False

    html_text = _md_to_html(text)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"}).encode()

    # Retry logic: 3 attempts with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    if attempt > 0:
                        print(f"Telegram send succeeded on attempt {attempt + 1}", file=__import__("sys").stderr)
                    return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                print(f"Telegram send attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...", file=__import__("sys").stderr)
                time.sleep(wait_time)
            else:
                print(f"Telegram send failed after {max_retries} attempts: {e}", file=__import__("sys").stderr)
                return False

    return False


def classify_case(case_name: str, holding: str) -> str:
    """Map a case to a category based on keywords in name + holding."""
    text = (case_name + " " + (holding or "")).lower()
    categories = {
        "dui": ["dui", "vehicle", "driving", "intoxication", "breath", "blood test", "bac"],
        "search seizure": ["search", "seizure", "warrant", "miranda", "fourth amendment", "suppression"],
        "evidence": ["evidence", "hearsay", "admissibility", "confrontation", "exclusion"],
        "procedure": ["procedure", "pretrial", "discovery", "plea", "sentencing", "judgment"],
        "trial": ["trial", "jury", "instruction", "verdict", "mistrial"],
        "postconviction": ["postconviction", "prp", "habeas", "collateral", "relief"],
        "constitutional": ["constitutional", "due process", "equal protection", "speedy trial"],
        "sentencing": ["sentencing", "sentence", "community custody"],
        "juvenile": ["juvenile", "minor", "youth", "family court"],
        "treatment": ["treatment", "involuntary", "commitment", "detention", "mental"],
    }
    for category, keywords in categories.items():
        if any(kw in text for kw in keywords):
            return category
    return "general"


def save_case_law(case_law: list):
    """Persist new cases to Obsidian under Case Law/WA Criminal/, deduped by name."""
    if not case_law:
        return
    try:
        # Load previously-seen case names
        seen: set[str] = set()
        if STATE_FILE.exists():
            try:
                seen = set(json.loads(STATE_FILE.read_text()))
            except Exception:
                pass

        new_cases = [c for c in case_law if c["name"] not in seen]
        if not new_cases:
            return

        # Update seen-cases state
        for c in case_law:
            seen.add(c["name"])
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(list(seen)))

        CASE_LAW_DIR.mkdir(parents=True, exist_ok=True)
        today_str = datetime.now(TZ).strftime("%Y-%m-%d")

        # Group by category
        by_cat: dict[str, list] = {}
        for case in new_cases:
            cat = classify_case(case["name"], case.get("holding", ""))
            by_cat.setdefault(cat, []).append(case)

        # Append each group to the matching category file
        for category, cases in by_cat.items():
            file_path = CASE_LAW_DIR / f"{category.title()}.md"

            existing = file_path.read_text() if file_path.exists() else ""
            # Strip trailing separator so we can append cleanly
            body = existing.rstrip()
            if body.endswith("---"):
                body = body[:-3].rstrip()

            if f"## {today_str}" not in body:
                body += f"\n\n## {today_str}\n"

            for case in cases:
                body += f"\n### {case['name']}\n\n"
                body += f"**Date:** {case['date']}\n\n"
                if case.get("url"):
                    body += f"**Opinion:** [Link]({case['url']})\n\n"
                if case.get("holding"):
                    body += f"**Holding:** {case['holding']}\n\n"
                body += "---\n"

            file_path.write_text(body + "\n")

    except Exception as e:
        print(f"Warning: Could not save case law: {e}", file=__import__("sys").stderr)


def main():
    brief_body, digest_entry, case_law = format_brief()

    # Update digest file
    update_digest(digest_entry)

    # Save brief to Research/Briefs/
    save_to_obsidian(brief_body)

    # Persist new cases to Obsidian
    save_case_law(case_law)

    # Send to Telegram
    send_telegram(brief_body)

    # Also print for stdout (run_tool / manual use)
    print(brief_body)


if __name__ == "__main__":
    main()
