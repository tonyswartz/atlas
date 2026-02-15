#!/usr/bin/env python3
"""
WA Prosecutors Weekly Case Law Summary
Scrapes the most recent week's case law roundup from waprosecutors.org/caselaw/
and sends it via Telegram, intelligently splitting by jurisdiction to avoid cutoffs.
"""

import re
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from html.parser import HTMLParser

# Add tools/ to path for common module imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Config
TZ = ZoneInfo("America/Los_Angeles")
CASE_LAW_URL = "https://waprosecutors.org/caselaw/"
TELEGRAM_CHAT_ID = "8241581699"  # Tony's personal chat
MAX_MESSAGE_LENGTH = 4000  # Telegram limit is 4096, leave some margin


def get_latest_post_url(index_html):
    """Extract the URL of the most recent weekly roundup post."""
    # Find links to weekly roundup posts
    pattern = r'<a href="(https://waprosecutors\.org/\d{4}/\d{2}/\d{2}/weekly-roundup-for-the-week-of[^"]+)"'
    matches = re.findall(pattern, index_html)

    if matches:
        # Return the first match (most recent)
        return matches[0]
    return None


def parse_post_html(html):
    """Parse a weekly roundup post to extract case summaries by jurisdiction.

    Returns: (week_header, sections)
    where sections = [(jurisdiction, [case_summaries])]
    """
    # Extract the title
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        week_header = title_match.group(1).replace(' | WAPA | Washington Association of Prosecuting Attorneys', '').strip()
    else:
        week_header = "Weekly Case Law Roundup"

    # Find the main content area (WordPress post content)
    content_match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*</article>', html, re.DOTALL)
    if not content_match:
        # Try alternate pattern
        content_match = re.search(r'<div[^>]*class="[^"]*fl-post-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)

    if not content_match:
        return week_header, []

    content_html = content_match.group(1)

    # Extract sections by jurisdiction (h3 or strong headers)
    jurisdictions = []

    # Pattern for jurisdiction headers - they're often in <p><strong> or <h3>
    jurisdiction_pattern = r'(?:<h3[^>]*>|<p[^>]*><strong>)(U\.S\. Supreme Court|Washington Supreme Court|Division I|Division II|Division III|9th Circuit|Federal Courts|[A-Z][^<]{5,40})(?:</strong></p>|</h3>)'

    jurisdiction_matches = list(re.finditer(jurisdiction_pattern, content_html, re.IGNORECASE))

    for i, match in enumerate(jurisdiction_matches):
        jurisdiction = re.sub(r'<[^>]+>', '', match.group(1)).strip()

        # Extract content between this jurisdiction and the next
        section_start = match.end()
        if i + 1 < len(jurisdiction_matches):
            section_end = jurisdiction_matches[i + 1].start()
        else:
            section_end = len(content_html)

        section_html = content_html[section_start:section_end]

        # Extract paragraphs
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', section_html, re.DOTALL)

        case_summaries = []
        for para in paragraphs:
            # Clean HTML tags but preserve structure
            clean_para = re.sub(r'<a[^>]*>', '', para)
            clean_para = re.sub(r'</a>', '', clean_para)
            clean_para = re.sub(r'<strong>(.*?)</strong>', r'*\1*', clean_para)
            clean_para = re.sub(r'<em>(.*?)</em>', r'_\1_', clean_para)
            clean_para = re.sub(r'<[^>]+>', '', clean_para)

            # Decode HTML entities (&#8211; -> em dash, &#8220; -> quotes, etc.)
            import html
            clean_para = html.unescape(clean_para)

            clean_para = clean_para.strip()

            if clean_para and len(clean_para) > 20:
                case_summaries.append(clean_para)

        if case_summaries:
            jurisdictions.append((jurisdiction, case_summaries))

    return week_header, jurisdictions


def fetch_case_law():
    """Fetch and parse the most recent week's case law from WA Prosecutors."""
    try:
        # First, fetch the index page to find the latest post URL
        req = urllib.request.Request(CASE_LAW_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            index_html = resp.read().decode("utf-8")

        latest_post_url = get_latest_post_url(index_html)
        if not latest_post_url:
            print("Could not find latest post URL", file=sys.stderr)
            return None, []

        print(f"Fetching post: {latest_post_url}", file=sys.stderr)

        # Fetch the individual post
        req = urllib.request.Request(latest_post_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            post_html = resp.read().decode("utf-8")

        # Parse the post
        week_header, sections = parse_post_html(post_html)

        return week_header, sections
    except Exception as e:
        print(f"Error fetching case law: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None, []


def format_for_telegram(week_header, sections):
    """Format case law into Telegram messages, splitting by jurisdiction to avoid cutoffs.

    Returns a list of message strings, each under MAX_MESSAGE_LENGTH.
    """
    if not week_header or not sections:
        return ["📚 **WA Prosecutors Weekly Case Law**\n\nNo new case law summaries available this week."]

    messages = []

    # First message: header + intro
    intro = f"📚 **{week_header}**\n\n"
    intro += f"_Case law summaries from the Washington Association of Prosecuting Attorneys_\n\n"
    intro += "---\n\n"

    current_message = intro

    for jurisdiction, case_summaries in sections:
        # Format jurisdiction header
        jurisdiction_text = f"**{jurisdiction}**\n\n"

        # Format each case
        cases_text = ""
        for i, case_summary in enumerate(case_summaries, 1):
            # Each case gets a bullet point and proper spacing
            cases_text += f"• {case_summary}\n\n"

        section_text = jurisdiction_text + cases_text + "---\n\n"

        # Check if adding this section would exceed the limit
        if len(current_message) + len(section_text) > MAX_MESSAGE_LENGTH:
            # Save current message and start a new one
            messages.append(current_message.rstrip())
            current_message = f"📚 **{week_header}** _(continued)_\n\n---\n\n{section_text}"
        else:
            current_message += section_text

    # Add the last message
    if current_message:
        messages.append(current_message.rstrip())

    return messages


def send_telegram(messages):
    """Send messages to Telegram via Bot API.

    Returns True if all messages sent successfully.
    """
    from common.credentials import get_telegram_token
    import time

    token = get_telegram_token()
    if not token:
        print("Telegram send failed: TELEGRAM_BOT_TOKEN not found", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    success_count = 0
    for i, message in enumerate(messages):
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }).encode()

        # Retry logic: 3 attempts with exponential backoff
        max_retries = 3
        sent = False
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        sent = True
                        success_count += 1
                        break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"Message {i+1} attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...", file=sys.stderr)
                    time.sleep(wait_time)
                else:
                    print(f"Message {i+1} failed after {max_retries} attempts: {e}", file=sys.stderr)

        if not sent:
            return False

        # Rate limit: wait 1 second between messages
        if i < len(messages) - 1:
            time.sleep(1)

    print(f"Successfully sent {success_count}/{len(messages)} messages", file=sys.stderr)
    return success_count == len(messages)


def main():
    """Main entry point."""
    print(f"Fetching case law from {CASE_LAW_URL}...", file=sys.stderr)

    week_header, sections = fetch_case_law()

    if not week_header:
        print("Failed to fetch case law", file=sys.stderr)
        return 1

    print(f"Found: {week_header}", file=sys.stderr)
    print(f"Sections: {len(sections)}", file=sys.stderr)

    messages = format_for_telegram(week_header, sections)
    print(f"Formatted into {len(messages)} Telegram messages", file=sys.stderr)

    # Send to Telegram
    success = send_telegram(messages)

    if success:
        print("Case law summary sent successfully", file=sys.stderr)
        return 0
    else:
        print("Failed to send case law summary", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
