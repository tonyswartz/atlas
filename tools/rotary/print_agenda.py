#!/usr/bin/env python3
"""
Print this week's Rotary meeting agenda to the Brother MFC-L3780CDW (one page).

Run only when the agenda is completed (saved for this week's Tuesday).
Sends a Telegram notification when the print job is sent.

Usage:
  python3 tools/rotary/print_agenda.py [--dry-run] [--date YYYY-MM-DD]
  # Scheduled: Tuesday 4:00 PM via launchd (com.atlas.rotary-print-agenda)
  # Test a specific agenda: --date 2026-02-10

Env:
  ROTARY_PRINTER     - CUPS printer name (default: Brother_MFC_L3780CDW_series)
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID or TELEGRAM_ID - for notification
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Add repo root to sys.path for common imports
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Obsidian vault Rotary paths (must match tool_runner.py)
VAULT_ROTARY = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault/Rotary")
ROTARY_MEETINGS = VAULT_ROTARY / "Meetings"

TZ = ZoneInfo("America/Los_Angeles")
MIN_AGENDA_BYTES = 200  # Consider "completed" if file exists and has at least this many bytes
DEFAULT_PRINTER = "Brother_MFC_L3780CDW_series"


def this_weeks_tuesday() -> datetime:
    """Return this week's Tuesday at midnight (for agenda file date). On Tuesday = today; else = last Tuesday."""
    from datetime import timedelta
    now = datetime.now(TZ)
    # weekday(): Monday=0 .. Sunday=6 → Tuesday=1
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now.weekday() == 1:
        return today
    # Not Tuesday: use most recent Tuesday
    days_back = (now.weekday() - 1) if now.weekday() >= 1 else (now.weekday() + 6)
    return today - timedelta(days=days_back)


def agenda_path_for(tuesday: datetime) -> Path:
    return ROTARY_MEETINGS / f"{tuesday.strftime('%Y-%m-%d')} Agenda.md"


def is_agenda_completed(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return path.stat().st_size >= MIN_AGENDA_BYTES
    except OSError:
        return False


# So pdflatex is found when run from launchd (minimal PATH)
TEXBIN = "/Library/TeX/texbin"


# Flexible space: \\vfill so all handwriting sections share remaining space; when content is long they shrink to fit one page
VFILL = "\\vfill"


def _markdown_with_list_spacing(md_path: Path, out_path: Path) -> None:
    """Rewrite markdown: space after date, blank after list items; replace (none)/(no guests) with \\vfill so all handwriting areas are flexible. \\vfill before closing Bell so it sits at bottom of page."""
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    result: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Closing line: no handwriting space below 50/50 — Bell — close meeting follows directly
        if "Bell" in stripped and "close" in stripped and stripped.startswith("###"):
            result.append(line)
            result.append("")
            continue

        # Replace placeholders with flexible \\vfill (all handwriting sections share space; shrink when content is long)
        if stripped == "*(no guests)*" or stripped == "*(none)*":
            result.append(VFILL)
            result.append("")
            continue
        if stripped == "- *(none)*" or (stripped.startswith("- ") and "*(none)*" in stripped):
            result.append(VFILL)
            result.append("")
            continue

        result.append(line)
        # Blank lines after meeting date so Bell is not on the same line as the date
        if i == 0 and "Meeting date:" in stripped:
            result.extend([""] * 2)
        # Blank line after list items so they don't run together
        elif stripped.startswith("- ") and (i + 1 >= len(lines) or lines[i + 1].strip() != ""):
            result.append("")

    out_path.write_text("\n".join(result), encoding="utf-8")


def _pdf_page_count(pdf_path: Path) -> int:
    """Return number of pages in PDF. Uses pypdf if available, else pdfinfo (poppler)."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except ImportError:
        pass
    try:
        r = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if line.strip().lower().startswith("pages:"):
                    return int(line.split(":", 1)[1].strip())
    except (FileNotFoundError, ValueError):
        pass
    return 0


def markdown_to_pdf(md_path: Path, pdf_path: Path, one_page: bool = True) -> bool:
    """Convert markdown to PDF. Uses \\vfill so blank space fills rest of page; if content overflows, shrink font to keep one page."""
    env = os.environ.copy()
    if Path(TEXBIN).exists():
        env["PATH"] = TEXBIN + os.pathsep + env.get("PATH", "")
    geometry = "top=0.35in,bottom=0.35in,left=0.35in,right=0.35in"
    # Preprocess once: spacing + section blanks + \\vfill at end (flexible blank to fill page)
    md_for_pandoc = pdf_path.parent / "rotary_agenda_spaced.md"
    _markdown_with_list_spacing(md_path, md_for_pandoc)

    font_sizes = ["12pt", "11pt", "10pt", "9pt", "8pt"]
    try:
        for fontsize in font_sizes:
            cmd = [
                "pandoc",
                str(md_for_pandoc),
                "-o", str(pdf_path),
                "-V", f"geometry:{geometry}",
                "-V", f"fontsize={fontsize}",
                "-V", "papersize=letter",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=env)
            if result.returncode != 0:
                continue
            if not one_page:
                return True
            pages = _pdf_page_count(pdf_path)
            if pages <= 1:
                return True
        # Last attempt without geometry (some setups)
        result = subprocess.run(
            ["pandoc", str(md_for_pandoc), "-o", str(pdf_path), "-V", "fontsize=8pt"],
            capture_output=True, text=True, timeout=45, env=env,
        )
        return result.returncode == 0 and (not one_page or _pdf_page_count(pdf_path) <= 1)
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def send_telegram(message: str) -> bool:
    # Use centralized credential loader (tries envchain, falls back to .env)
    from tools.common.credentials import get_credential

    token = get_credential("TELEGRAM_BOT_TOKEN")
    chat_id = get_credential("TELEGRAM_CHAT_ID") or get_credential("TELEGRAM_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = __import__("json").dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Print this week's Rotary agenda (one page) and notify via Telegram.")
    ap.add_argument("--dry-run", action="store_true", help="Only check for agenda and report; do not print or notify.")
    ap.add_argument("--date", metavar="YYYY-MM-DD", help="Use this meeting date's agenda (e.g. 2026-02-10) instead of this week's Tuesday.")
    args = ap.parse_args()

    if args.date:
        try:
            tuesday = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=TZ)
        except ValueError:
            print("ERROR: --date must be YYYY-MM-DD", file=sys.stderr)
            return 1
    else:
        tuesday = this_weeks_tuesday()
    agenda_file = agenda_path_for(tuesday)
    date_str = tuesday.strftime("%Y-%m-%d")

    if not is_agenda_completed(agenda_file):
        if args.dry_run:
            print(f"Agenda not ready: {agenda_file} missing or too small (need >= {MIN_AGENDA_BYTES} bytes).")
            return 0
        # Cron: exit quietly so we don't spam logs
        sys.exit(0)

    if args.dry_run:
        print(f"Agenda ready: {agenda_file} (date {date_str}). Would print and send Telegram.")
        return 0

    printer = os.environ.get("ROTARY_PRINTER", "").strip() or DEFAULT_PRINTER
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / "rotary_agenda.pdf"
        if markdown_to_pdf(agenda_file, pdf_path):
            to_print = pdf_path
        else:
            # Fallback: print raw markdown (readable, no PDF formatting)
            to_print = tmp_path / "rotary_agenda.md"
            to_print.write_text(agenda_file.read_text(encoding="utf-8"), encoding="utf-8")

        lp_cmd = ["lp", "-d", printer, str(to_print)]
        try:
            subprocess.run(lp_cmd, check=True, capture_output=True, text=True, timeout=15)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"ERROR: lp failed: {e}", file=sys.stderr)
            send_telegram(f"Rotary print failed: printer error. Agenda: {date_str}. Check printer name: {printer}.")
            return 1

    msg = f"Rotary agenda printed for *{date_str}* (1 page, {printer})."
    if send_telegram(msg):
        pass  # optional: log "Telegram sent"
    else:
        print("WARNING: Telegram notification not sent (check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
