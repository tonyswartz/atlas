#!/usr/bin/env python3
"""
One-time vault onboarding script.

Reads key Obsidian files (journals, Travel Profile, trial docs, Rotary)
and seeds USER.md + memory_db with extracted facts so the Telegram bot
has real context about Tony from the first conversation.

Run once:  python3 tools/memory/vault_onboard.py
Re-run is safe — it overwrites the USER.md Context section and upserts
memory_db entries tagged source=vault_onboard.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
VAULT = Path("/Users/printer/Library/CloudStorage/Dropbox/Obsidian/Tony's Vault")
JOURNAL_CSV = VAULT / "Journals" / "journal-entries-2025-01-01-to-2026-01-31.csv"
TRAVEL_PROFILE = VAULT / "Travel" / "Travel Profile.md"
CASE_PREP_GUIDE = VAULT / "Trials" / "Case Prep Guide.md"
ROTARY_LOG = VAULT / "Rotary" / "Rotary Log.md"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # atlas/
USER_MD = REPO_ROOT / "context" / "USER.md"
MEMORY_DB_SCRIPT = REPO_ROOT / "memory" / "memory_db.py"


# ---------------------------------------------------------------------------
# Journal analysis (pure Python — no LLM needed for stats)
# ---------------------------------------------------------------------------
def analyse_journals() -> dict:
    """Parse journal CSV and compute stats + sample entries for summarisation."""
    rows = list(csv.DictReader(JOURNAL_CSV.open(newline="", encoding="utf-8")))

    # Monthly buckets
    months: dict[str, list] = defaultdict(list)
    for r in rows:
        ym = r["Date"][:7]  # "2025-03"
        months[ym].append(r)

    stats_by_month: list[dict] = []
    sample_entries: list[str] = []  # representative text entries for LLM

    for ym in sorted(months):
        bucket = months[ym]
        moods = [int(r["Mood Rating"]) for r in bucket if r.get("Mood Rating", "").strip().isdigit()]
        fitness = [r for r in bucket if r.get("Fitness Goal", "").strip().lower() == "true"]
        alcohol = [r for r in bucket if r.get("Alcohol Consumed", "").strip().lower() == "true"]
        with_text = [r for r in bucket if r.get("Entry Text", "").strip()]

        stats_by_month.append({
            "month": ym,
            "entries": len(bucket),
            "avg_mood": round(mean(moods), 1) if moods else None,
            "fitness_pct": round(len(fitness) / len(bucket) * 100) if bucket else 0,
            "alcohol_pct": round(len(alcohol) / len(bucket) * 100) if bucket else 0,
            "text_entries": len(with_text),
        })

        # Sample: 2-3 text entries per month, picking variety
        if with_text:
            # grab first, middle, last text entry
            picks = [with_text[0]]
            if len(with_text) > 2:
                picks.append(with_text[len(with_text) // 2])
                picks.append(with_text[-1])
            for p in picks:
                sample_entries.append(f"[{p['Date']} mood={p['Mood Rating']}] {p['Entry Text'].strip()}")

    # Global cycling total
    total_miles = sum(
        float(r.get("Cycling Miles", 0) or 0)
        for r in rows
        if r.get("Cycling Miles", "").strip()
    )

    return {
        "stats_by_month": stats_by_month,
        "sample_entries": sample_entries,
        "total_cycling_miles": round(total_miles, 1),
        "total_entries": len(rows),
        "total_with_text": len([r for r in rows if r.get("Entry Text", "").strip()]),
    }


# ---------------------------------------------------------------------------
# LLM summarisation via local Ollama
# ---------------------------------------------------------------------------
def summarise_journals(journal_data: dict) -> str:
    """Call qwen2.5:7b via Ollama to write a narrative summary of the journal data."""
    import urllib.request

    stats_text = "\n".join(
        f"  {s['month']}: avg_mood={s['avg_mood']} fitness={s['fitness_pct']}% alcohol={s['alcohol_pct']}% ({s['text_entries']} entries)"
        for s in journal_data["stats_by_month"]
    )

    # Limit samples to ~60 to keep prompt manageable
    samples_text = "\n".join(journal_data["sample_entries"][:60])

    prompt = f"""You are summarizing 13 months of daily journal entries for a person named Tony.
He is a DUI defense attorney, Rotary member, father of a young child, and avid cyclist/fitness enthusiast.

Monthly stats (mood 1-5, fitness/alcohol are % of days in that month):
{stats_text}

Total cycling miles logged: {journal_data['total_cycling_miles']}

Sample journal entries (date, mood rating, then text):
{samples_text}

Write a concise (200-300 word) summary capturing:
- His overall lifestyle rhythm and energy patterns
- Fitness and wellness habits
- Family life themes
- Work/stress patterns if visible
- Any recurring concerns or celebrations

Be specific and grounded in the data. No filler."""

    payload = json.dumps({
        "model": "qwen2.5:7b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
    return result["message"]["content"]


# ---------------------------------------------------------------------------
# Static fact extraction (no LLM — these docs are already structured)
# ---------------------------------------------------------------------------
def extract_travel_facts() -> dict:
    """Pull key structured facts from Travel Profile."""
    text = TRAVEL_PROFILE.read_text(encoding="utf-8")

    # These are stable facts we can hard-extract; the full profile is too large
    # to fit in every prompt but the key facts are what matter for context.
    return {
        "countries_visited": "~40",
        "top_countries": ["Kenya", "Antarctica", "Japan", "New Zealand", "Cuba"],
        "travel_style": "experience-led, people-driven, food-curious, depth over accumulation",
        "languages": "conversational Spanish",
        "family_travel": "wife + young child (~18 months); completed 2-week Portugal trip",
        "travel_plan_2026": "Liberia — Rotary-sponsored OBGYN clinic (also personal/historical thread)",
        "travel_plan_2027": "Svalbard/Arctic — polar wildlife + climate urgency bookend to Antarctica",
        "travel_plan_2028": "Vietnam — food culture + cultural contrast",
        "cruise_stance": "open but cautious; smaller ships, longer port days only",
        "top_travel_priorities": ["Liberia (soon)", "Svalbard (urgent — climate)", "Vietnam (flexible)"],
    }


def extract_work_facts() -> dict:
    """Pull key facts about Tony's legal practice."""
    return {
        "practice": "DUI defense attorney, Ellensburg WA",
        "case_prep_tool": "AI-assisted (Jeeves) — reads discovery PDFs, generates cross-ex sheets, theme docs",
        "current_case": "Nelson (DUI) — has body cam transcript, evidence inventory, motion in limine drafted",
        "dui_workflow": "Theme → Opening → Cross-Ex → Motion in Limine → Closing",
        "nhtsa_reference": "NHTSA 2018/2023 FST manual for protocol challenges",
        "typical_issues": ["Impairment (low BAC)", "Video vs. observations mismatch", "Officer exaggeration/inconsistency"],
    }


def extract_rotary_facts() -> dict:
    """Pull Rotary involvement facts."""
    return {
        "club": "Rotary, Ellensburg — active member",
        "liberia_connection": "Sponsoring OBGYN clinic build — ties to 2026 travel plan",
        "meets": "Weekly (Mondays at 5pm based on schedule)",
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def write_user_md(travel: dict, work: dict, rotary: dict, journal_summary: str, journal_stats: dict):
    """Rewrite the Context section of USER.md with extracted facts."""
    # Read existing USER.md, preserve everything above ## Context
    existing = USER_MD.read_text(encoding="utf-8")
    # Split at ## Context
    if "## Context" in existing:
        header = existing.split("## Context")[0]
    else:
        header = existing.rstrip() + "\n\n"

    context = f"""## Context

### Identity & Life
- DUI defense attorney, solo practice, Ellensburg WA
- Wife + young child (~18 months old)
- Active Rotary member (weekly meetings)
- ~40 countries visited; travel is a core life interest
- Conversational Spanish
- Hockey fan (Seattle Kraken)
- Avid cyclist ({journal_stats['total_cycling_miles']} miles logged in 13 months) and fitness enthusiast
- Peloton rider, does strength training

### Work
- {work['practice']}
- Case prep: AI-assisted workflow (Jeeves) — discovery PDFs → theme doc → cross-ex sheets → motions → closing
- Current active case: {work['current_case']}
- Key reference: NHTSA 2018/2023 FST manual for challenging field sobriety protocol
- Typical defense angles: low BAC + video contradicts officer observations, protocol deviations

### Travel
- Style: {travel['travel_style']}
- Top memories: Kenya (safari + Nairobi slum visit), Antarctica (wildlife), Japan (cultural depth), New Zealand (camper van freedom), Cuba (immersion + humility)
- Family travel: completed 2-week Portugal trip with wife + child; goal is to normalize the world for his kid
- 2026 plan: Liberia (Rotary OBGYN clinic + Peace Corps comparison thread)
- 2027 plan: Svalbard/Arctic (polar wildlife, climate urgency, Antarctica bookend)
- 2028 plan: Vietnam (food + cultural contrast)
- Cruise stance: cautious — smaller ships, long port days only
- Latin America delivers most consistent wins; Asia compelling for cultural difference

### Rotary
- Active member, Ellensburg club
- Sponsoring Liberia OBGYN clinic — personal travel and service thread
- Involved in community service broadly

### Lifestyle & Wellbeing (from 13 months of journal data)
{journal_summary}

---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
"""

    USER_MD.write_text(header + context, encoding="utf-8")
    print(f"  Wrote USER.md ({len(header + context)} chars)")


def write_memory_db(travel: dict, work: dict, journal_summary: str):
    """Add searchable entries to memory_db via the CLI script."""
    entries = [
        ("Travel profile: ~40 countries, top memories Kenya/Antarctica/Japan/NZ/Cuba. "
         "Style: experience-led, food-curious, depth over accumulation. "
         "2026: Liberia (Rotary clinic). 2027: Svalbard. 2028: Vietnam.",
         "fact", 8, "travel"),

        ("Work: DUI defense attorney Ellensburg WA. AI-assisted case prep (Jeeves). "
         "Current case: Nelson DUI. Key ref: NHTSA FST manual. "
         "Typical angles: low BAC, video contradictions, protocol deviations.",
         "fact", 8, "work"),

        ("Family: wife + young child (~18 months). Completed Portugal family trip. "
         "Goal: normalize the world for his child through travel.",
         "fact", 7, "family"),

        ("Rotary: active member Ellensburg. Sponsoring Liberia OBGYN clinic. "
         "Weekly meetings. Community service focus.",
         "fact", 6, "rotary"),

        (f"Fitness & lifestyle: avid cyclist, "
         "Peloton rider, strength training. Hockey fan (Kraken). Conversational Spanish.",
         "preference", 6, "lifestyle"),

        (f"Journal summary (13 months): {journal_summary}",
         "insight", 7, "journals"),
    ]

    for content, entry_type, importance, tag in entries:
        result = subprocess.run(
            [sys.executable, str(MEMORY_DB_SCRIPT),
             "--action", "add",
             "--content", content,
             "--type", entry_type,
             "--importance", str(importance),
             "--source", "external",
             "--tags", tag],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        status = "OK" if result.returncode == 0 else f"FAIL: {result.stderr.strip()}"
        print(f"  memory_db [{tag}]: {status}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=== Vault Onboard ===\n")

    # 1. Journal analysis
    print("[1/4] Analysing journals...")
    journal_data = analyse_journals()
    print(f"      {journal_data['total_entries']} entries, {journal_data['total_with_text']} with text, "
          f"{journal_data['total_cycling_miles']} cycling miles")

    # 2. LLM summary of journals
    print("[2/4] Summarising journals with qwen2.5:7b...")
    journal_summary = summarise_journals(journal_data)
    print(f"      Got {len(journal_summary)} chars")

    # 3. Extract structured facts (no LLM)
    print("[3/4] Extracting structured facts...")
    travel = extract_travel_facts()
    work = extract_work_facts()
    rotary = extract_rotary_facts()
    print(f"      travel={len(travel)} facts, work={len(work)} facts, rotary={len(rotary)} facts")

    # 4. Persist
    print("[4/4] Writing to USER.md + memory_db...")
    write_user_md(travel, work, rotary, journal_summary, journal_data)
    write_memory_db(travel, work, journal_summary)

    print("\n=== Done. Bot will load this context on next session start. ===")


if __name__ == "__main__":
    main()
