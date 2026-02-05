#!/usr/bin/env python3
"""Pull WA appellate opinions, append Obsidian stubs, and (optionally) upgrade stubs into short case summaries.

Idempotency:
- Maintains a JSON progress log keyed by WA Courts PDF filename stem.
- For summarization, only modifies entries that still contain the exact marker:
    "- **Notes:** _TBD_"

Usage examples:
  # Import new stubs
  python3 scripts/wa_opinions_to_obsidian.py --vault "/path/to/Vault" --days 365 --max-cases 250

  # Upgrade existing stubs (only those still TBD)
  OPENAI_API_KEY=... python3 scripts/wa_opinions_to_obsidian.py --vault "/path/to/Vault" --summarize --only-tbd --max-cases 25

Notes:
- Source: https://www.courts.wa.gov/opinions/index.cfm?fa=opinions.processSearch
- Summarization downloads PDFs and uses `pdftotext` (Poppler) to extract pages 1-N.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

BASE = "https://www.courts.wa.gov"
SEARCH_POST = BASE + "/opinions/index.cfm?fa=opinions.processSearch"
UA = {"User-Agent": "Mozilla/5.0 (compatible; wa-opinions-to-obsidian/1.1)"}

NOTES_TBD_MARKER = "- **Notes:** _TBD_"


@dataclass(frozen=True)
class Opinion:
    id: str                 # pdf stem, e.g., 1034695 or 403416_pub
    title: str
    case_no: str
    filed_date: str         # ISO YYYY-MM-DD
    court: str              # normalized human string
    division: Optional[str] # I/II/III
    pub_status: str         # Published/Unpublished/Unknown
    pdf_url: str
    source_section: str     # COA_PUB/COA_UNP/SUP


def _iso_date_from_cell(text: str) -> Optional[str]:
    # Examples: "Jan. 21, 2026" or "January 21, 2026"
    t = " ".join(text.strip().split())
    t = t.replace("Sept.", "Sep.")
    for fmt in ("%b. %d, %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            d = dt.datetime.strptime(t, fmt).date()
            return d.isoformat()
        except ValueError:
            pass
    return None


def fetch_search(court_level: str, begin: dt.date, end: dt.date, pub_status: str = "All") -> str:
    data = {
        "courtLevel": court_level,  # All|S|C
        "pubStatus": pub_status,    # All|PUB|UNP
        "beginDate": begin.strftime("%m/%d/%Y"),
        "endDate": end.strftime("%m/%d/%Y"),
        "SValue": "",
        "SType": "Phrase",
    }
    r = requests.post(SEARCH_POST, data=data, headers=UA, timeout=120)
    r.raise_for_status()
    return r.text


def is_truncated_to_200(html: str) -> bool:
    return "only the first 200 opinions are shown" in html.lower()


def fetch_all_in_range(court_level: str, begin: dt.date, end: dt.date, pub_status: str = "All") -> List[str]:
    """Fetch search result pages covering [begin, end].

    WA Courts truncates at 200 opinions per query. We adaptively split the date range until
    each query is not truncated.
    """

    html = fetch_search(court_level, begin, end, pub_status=pub_status)
    if not is_truncated_to_200(html):
        return [html]

    # Split range in half.
    if begin >= end:
        # can't split further
        return [html]

    mid = begin + (end - begin) // 2
    # Ensure progress (avoid infinite loop)
    if mid == begin:
        mid = begin + dt.timedelta(days=1)
        if mid > end:
            return [html]

    left = fetch_all_in_range(court_level, begin, mid, pub_status=pub_status)
    right = fetch_all_in_range(court_level, mid + dt.timedelta(days=1), end, pub_status=pub_status)
    return left + right


def infer_pub_status(section_pub_status: str, pdf_stem: str) -> str:
    """Infer publication status using robust filename heuristics.

    WA Courts filenames are inconsistent; COA divisional PDFs sometimes include:
      "D2 ... Published Opinion" / "... Unpublished Opinion"
    and older files often use suffixes: _pub / _unp.

    Priority: explicit filename cues > section label.
    """

    low = pdf_stem.lower()

    # Explicit cues in filenames (strongest)
    if re.search(r"(^|_)unp($|_)", low) or low.endswith("_unp") or "unpublished opinion" in low or "unpublished" in low:
        return "Unpublished"
    if re.search(r"(^|_)pub($|_)", low) or low.endswith("_pub") or "published opinion" in low:
        return "Published"

    # Fall back to section labels if present
    if section_pub_status in ("Published", "Unpublished"):
        return section_pub_status

    return "Unknown"


def _parse_table(table, court_kind: str, section_pub_status: str, section: str) -> List[Opinion]:
    # Identify header indices.
    header = table.find("tr")
    heads = [th.get_text(" ", strip=True).lower() for th in header.find_all(["td", "th"], recursive=False)]

    def idx_of(name: str) -> Optional[int]:
        for i, h in enumerate(heads):
            if name in h:
                return i
        return None

    date_i = idx_of("file date")
    case_i = idx_of("case info")
    div_i = idx_of("div")
    title_i = idx_of("case title")

    out: List[Opinion] = []
    for tr in table.find_all("tr"):
        pdf_a = tr.find("a", href=re.compile(r"^/opinions/pdf/.*\.pdf$", re.I))
        if not pdf_a:
            continue
        tds = tr.find_all("td")
        if not tds:
            continue

        def cell(i: Optional[int]) -> str:
            if i is None or i >= len(tds):
                return ""
            return tds[i].get_text(" ", strip=True)

        filed_raw = cell(date_i)
        filed_iso = _iso_date_from_cell(filed_raw) or ""

        case_no = cell(case_i)
        # sometimes case cell contains whitespace/newlines; also anchor with caseno displayed
        case_no = re.sub(r"\s+", " ", case_no).strip()

        division = cell(div_i) if div_i is not None else ""
        division = division.strip() or None

        title = cell(title_i)
        title = re.sub(r"\s+", " ", title).strip()

        pdf_href = pdf_a.get("href", "")
        pdf_url = BASE + pdf_href
        pdf_name = os.path.basename(pdf_href)
        pdf_stem = os.path.splitext(pdf_name)[0]

        court = "Washington Supreme Court (en banc)" if court_kind == "SUP" else (
            f"Washington Court of Appeals Division {division}" if division else "Washington Court of Appeals"
        )

        inferred = infer_pub_status(section_pub_status, pdf_stem)

        out.append(
            Opinion(
                id=pdf_stem,
                title=title,
                case_no=case_no,
                filed_date=filed_iso,
                court=court,
                division=division,
                pub_status=inferred,
                pdf_url=pdf_url,
                source_section=section,
            )
        )
    return out


def parse_search_html(html: str) -> List[Opinion]:
    soup = BeautifulSoup(html, "html.parser")

    opinions: List[Opinion] = []

    # The page contains many layout tables. We only want the opinion-list tables whose *first row*
    # is a compact header like: [File Date, Case Info/File, Div., Case Title, File Contains].
    tables = soup.find_all("table")

    def is_opinion_header_row(tr) -> bool:
        tds = tr.find_all(["td", "th"], recursive=False)
        if not tds:
            return False
        texts = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip().lower() for td in tds]
        # Must be a short header row (avoid huge wrapper rows).
        if len(texts) > 8:
            return False
        need = {"file date", "case info/file", "case title"}
        if not need.issubset(set(texts)):
            return False
        return True

    for tbl in tables:
        hdr = tbl.find("tr")
        if not hdr or not is_opinion_header_row(hdr):
            continue

        hdr_cells = [td.get_text(" ", strip=True).lower() for td in hdr.find_all(["td", "th"], recursive=False)]

        # Determine whether this table is COA (has Div.) or SUP (no Div.).
        is_coa = any("div" == c.strip().lower().strip(".") for c in hdr_cells)

        # Determine pub status by scanning nearby preceding labels.
        pub = "Unknown"
        prev = tbl
        for _ in range(10):
            prev = prev.find_previous()
            if prev is None:
                break
            if prev.name in ("strong", "b", "h3"):
                label = prev.get_text(" ", strip=True).lower()
                if "published opinions" in label or label.strip() == "published":
                    pub = "Published"
                    break
                if "unpublished opinions" in label or label.strip() == "unpublished":
                    pub = "Unpublished"
                    break

        section = "COA" if is_coa else "SUP"
        section = f"{section}_{'PUB' if pub=='Published' else 'UNP' if pub=='Unpublished' else 'UNK'}"

        opinions.extend(_parse_table(tbl, court_kind="COA" if is_coa else "SUP", section_pub_status=pub, section=section))

    # Deduplicate by id.
    return list({op.id: op for op in opinions}.values())


CRIM_INCLUDE_PATTERNS = [
    r"\bstate\s+of\s+washington\b",
    r"\bstate\s+v\.?\b",
    r"\bcity\s+of\b.*\bv\.?\b",
    r"\bpersonal\s+restraint\s+petition\b",
    r"\bpers\.?\s+restraint\b",
    r"\bprp\b",
    r"\bin\s+re\s+the\s+detention\b",
    r"\bin\s+the\s+matter\s+of\s+the\s+detention\b",
    r"\bin\s+re\s+detention\b",
    r"\bsexually\s+violent\s+predator\b",
]

CRIM_EXCLUDE_PATTERNS = [
    r"\bmarriage\b",
    r"\bdissolution\b",
    r"\bdependency\b",
    r"\badoption\b",
    r"\bestate\b",
    r"\bprobate\b",
    r"\bparenting\b",
    r"\bcustody\b",
    r"\bguardianship\b",
    r"\bforeclosure\b",
    r"\bcondominium\b",
    r"\bllc\b",
    r"\binc\b",
    r"\bcorporation\b",
    r"\binsurance\b",
    r"\btort\b",
    r"\bcontract\b",
    r"\bemployment\b",
    r"\bworkers'\s+comp\b",
    r"\bl&i\b",
]


def is_likely_criminal(title: str) -> bool:
    t = title.lower()
    if any(re.search(p, t) for p in CRIM_EXCLUDE_PATTERNS):
        # exclusions are soft; allow if clearly State v.
        if re.search(r"\bstate\s+of\s+washington\b", t) or re.search(r"\bstate\s+v\.?\b", t):
            return True
        return False
    return any(re.search(p, t) for p in CRIM_INCLUDE_PATTERNS)


TOPIC_RULES: List[Tuple[str, List[str]]] = [
    ("Postconviction — PRP", [r"personal restraint", r"\bprp\b", r"crr\s*7\.8", r"habeas", r"collateral"]),
    ("Search & Seizure — Miranda", [r"miranda", r"suppression", r"search", r"seizure", r"probable cause", r"warrant", r"frisk", r"stop", r"terry", r"traffic stop"]),
    ("Sentencing", [r"sentence", r"sentencing", r"sra", r"exceptional", r"community custody", r"enhancement", r"offender score", r"legal financial obligation", r"lfo", r"dosage", r"dna fee"]),
    ("Evidence", [r"er\s*404\(b\)", r"hearsay", r"confrontation", r"er\s*106", r"er\s*609", r"evidence", r"expert", r"chain of custody"]),
    ("Constitutional", [r"due process", r"double jeopardy", r"speedy trial", r"crr\s*3\.3", r"equal protection", r"ex post facto", r"cruel", r"fourth amendment", r"fifth amendment", r"sixth amendment"]),
    ("Criminal Procedure", [r"trial", r"continuance", r"jury", r"plea", r"crr\s*4\.2", r"crr\s*7\.5", r"crr\s*8\.3", r"competency", r"bail", r"detention"]),
    ("DUI/Vehicle", [r"dui", r"driving", r"vehicle", r"hit and run", r"reckless", r"ignition interlock"]),
    ("Juvenile", [r"juvenile", r"jucr", r"decline", r"manifest injustice", r"j\.r\.", r"youth"]),
]


def classify_topics(op: Opinion) -> List[str]:
    hay = (op.title + " " + op.case_no).lower()
    topics: List[str] = []
    for topic, pats in TOPIC_RULES:
        if any(re.search(p, hay) for p in pats):
            topics.append(topic)
    # default bucket
    if not topics:
        topics = ["Criminal Procedure"]
    return sorted(set(topics), key=topics.index)


def load_progress(path: Path) -> Dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "processed": {}, "runs": []}


def save_progress(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def topic_filename(topic: str) -> str:
    """Map a topic name to a safe markdown filename."""
    # Avoid accidental subfolders (e.g., "Search / Seizure").
    safe = topic.replace("/", " — ")
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe + ".md"


def ensure_topic_file(topic_path: Path, topic: str) -> None:
    if topic_path.exists():
        return
    topic_path.parent.mkdir(parents=True, exist_ok=True)
    topic_path.write_text(f"# {topic} (WA Criminal)\n\n", encoding="utf-8")


def entry_block(op: Opinion) -> str:
    # Human-readable filed date
    d = op.filed_date
    try:
        dd = dt.date.fromisoformat(d)
        filed_disp = dd.strftime("%b. %d, %Y")
    except Exception:
        filed_disp = d

    pub_line = f"- **Status:** {op.pub_status}\n" if op.pub_status and op.pub_status != "Unknown" else ""
    div_line = f"- **Division:** {op.division}\n" if op.division else ""

    return (
        f"\n## {op.title}, No. {op.case_no} (Filed {filed_disp})\n"
        f"- **Court:** {op.court}\n"
        f"{div_line}"
        f"{pub_line}"
        f"- PDF: {op.pdf_url}\n"
        f"{NOTES_TBD_MARKER}\n"
    )


def append_if_missing(path: Path, op: Opinion) -> bool:
    """Append entry if this opinion isn't already in file. Returns True if written."""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        # Use pdf stem and/or case no as a robust marker.
        if op.id in existing or f"No. {op.case_no}" in existing:
            return False
    else:
        ensure_topic_file(path, path.stem)

    with path.open("a", encoding="utf-8") as f:
        f.write(entry_block(op))
    return True


def update_wa_criminal_index(index_path: Path, topics: List[str]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# WA Criminal — Index\n",
        "\n",
        f"Last updated: {dt.date.today().isoformat()}\n",
        "\n",
        "## Topics\n",
    ]
    for t in sorted(topics, key=lambda s: s.lower()):
        lines.append(f"- [[{t}]]\n")
    index_path.write_text("".join(lines), encoding="utf-8")


def _download_pdf(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    r = requests.get(url, headers=UA, stream=True, timeout=180)
    r.raise_for_status()
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    with tmp.open("wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)
    tmp.replace(out_path)
    return out_path


def _pdftotext_extract(pdf_path: Path, pages: int = 4) -> str:
    """Extract first N pages as text using pdftotext."""
    pages = max(1, min(int(pages), 10))
    cmd = [
        "pdftotext",
        "-f",
        "1",
        "-l",
        str(pages),
        "-layout",
        str(pdf_path),
        "-",
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"pdftotext failed ({p.returncode}): {p.stderr.strip()}")
    return p.stdout


def _openai_summarize(text: str, *, op: Opinion, model: str) -> Dict[str, object]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot summarize.")

    # Keep payload bounded.
    excerpt = text
    if len(excerpt) > 20000:
        excerpt = excerpt[:20000]

    schema_hint = {
        "issue": "(1-2 sentences)",
        "holding": "(1 sentence)",
        "reasoning_bullets": ["(2-4 bullets)", "..."],
        "defense_takeaway_bullets": ["(1-2 bullets)", "..."],
    }

    prompt = (
        "You are summarizing a Washington Court of Appeals criminal opinion for a defense lawyer. "
        "Use ONLY the provided excerpt. If uncertain, say so briefly rather than inventing facts.\n\n"
        f"Case: {op.title} (No. {op.case_no}); Court: {op.court}; Filed: {op.filed_date}; Status: {op.pub_status}.\n\n"
        "Return STRICT JSON (no markdown) with keys exactly: issue, holding, reasoning_bullets, defense_takeaway_bullets. "
        f"Format example: {json.dumps(schema_hint)}\n\n"
        "Excerpt:\n"
        f"{excerpt}"
    )

    # Responses API (preferred)
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": prompt,
        "text": {"format": {"type": "json_object"}},
    }

    r = requests.post(url, headers=headers, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()

    # Extract JSON text from output
    out_text = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out_text += c.get("text", "")

    if not out_text.strip():
        raise RuntimeError("OpenAI response had no output_text")

    try:
        obj = json.loads(out_text)
    except Exception as e:
        raise RuntimeError(f"Failed to parse model JSON: {e}\nRaw: {out_text[:4000]}")

    return obj


def _format_summary_block(summary: Dict[str, object]) -> str:
    issue = str(summary.get("issue", "")).strip()
    holding = str(summary.get("holding", "")).strip()
    reasoning = summary.get("reasoning_bullets") or []
    takeaway = summary.get("defense_takeaway_bullets") or []

    if isinstance(reasoning, str):
        reasoning = [reasoning]
    if isinstance(takeaway, str):
        takeaway = [takeaway]

    def bullets(items: List[str]) -> str:
        clean = [str(x).strip().lstrip("-• ") for x in items if str(x).strip()]
        return "\n".join([f"  - {x}" for x in clean])

    lines = []
    lines.append(f"- **Issue:** {issue}\n")
    lines.append(f"- **Holding:** {holding}\n")
    lines.append("- **Reasoning:**\n")
    lines.append((bullets(reasoning) or "  - (Not stated in excerpt)") + "\n")
    lines.append("- **Defense takeaway:**\n")
    lines.append((bullets(takeaway) or "  - (Not stated in excerpt)") + "\n")
    return "".join(lines).rstrip() + "\n"


def _replace_notes_tbd_in_topic_file(topic_path: Path, *, op: Opinion, replacement_block: str) -> bool:
    if not topic_path.exists():
        return False
    txt = topic_path.read_text(encoding="utf-8")
    if NOTES_TBD_MARKER not in txt:
        return False

    heading = f"## {op.title}, No. {op.case_no}"
    hpos = txt.find(heading)
    if hpos == -1:
        # fallback: try case number only
        hpos = txt.find(f"No. {op.case_no}")
        if hpos == -1:
            return False

    # Replace the first TBD marker after heading, but only within the entry (before next "\n## ").
    next_h = txt.find("\n## ", hpos + 1)
    entry_end = next_h if next_h != -1 else len(txt)
    entry = txt[hpos:entry_end]

    npos = entry.find(NOTES_TBD_MARKER)
    if npos == -1:
        return False

    new_entry = entry.replace(NOTES_TBD_MARKER, replacement_block.rstrip("\n"), 1)
    new_txt = txt[:hpos] + new_entry + txt[entry_end:]
    if new_txt == txt:
        return False

    topic_path.write_text(new_txt, encoding="utf-8")
    return True


def summarize_existing(
    *,
    vault: Path,
    prog: Dict,
    progress_path: Path,
    max_cases: int,
    only_tbd: bool,
    pages: int,
    llm_model: str,
    cache_dir: Path,
) -> Dict[str, int]:
    """Upgrade existing COA stubs to include Issue/Holding/Reasoning/Defense takeaway."""

    target_dir = vault / "Case Law" / "WA Criminal"
    processed: Dict[str, Dict] = prog.get("processed", {})

    # Deterministic processing order: newest first.
    def key(item):
        _, rec = item
        return rec.get("filed_date", "0000-00-00")

    coa_items = [
        (oid, rec)
        for oid, rec in processed.items()
        if "Court of Appeals" in (rec.get("court") or "")
    ]
    coa_items.sort(key=key, reverse=True)

    done = 0
    touched_files = 0
    skipped = 0

    for oid, rec in coa_items:
        if done >= max_cases:
            break

        # Skip if already summarized.
        if rec.get("summarized") is True:
            skipped += 1
            continue

        op = Opinion(
            id=rec["id"],
            title=rec["title"],
            case_no=rec["case_no"],
            filed_date=rec.get("filed_date", ""),
            court=rec.get("court", ""),
            division=rec.get("division"),
            pub_status=rec.get("pub_status", "Unknown"),
            pdf_url=rec["pdf_url"],
            source_section=rec.get("source_section", ""),
        )

        topics = rec.get("topics") or []
        if not topics:
            topics = classify_topics(op)

        # If only_tbd, require the TBD marker be present in at least one topic file.
        any_has_tbd = False
        topic_paths = [target_dir / topic_filename(t) for t in topics]
        for tp in topic_paths:
            if tp.exists() and NOTES_TBD_MARKER in tp.read_text(encoding="utf-8"):
                any_has_tbd = True
                break
        if only_tbd and not any_has_tbd:
            skipped += 1
            continue

        pdf_path = cache_dir / (op.id + ".pdf")
        _download_pdf(op.pdf_url, pdf_path)
        extracted = _pdftotext_extract(pdf_path, pages=pages)
        summary = _openai_summarize(extracted, op=op, model=llm_model)
        replacement = _format_summary_block(summary)

        wrote_any = False
        for tp in topic_paths:
            if _replace_notes_tbd_in_topic_file(tp, op=op, replacement_block=replacement):
                wrote_any = True
                touched_files += 1

        if wrote_any:
            rec["summarized"] = True
            rec["summarized_timestamp"] = dt.datetime.now().isoformat(timespec="seconds")
            rec["summary"] = summary
            done += 1
        else:
            skipped += 1

        if done and done % 10 == 0:
            # periodic safe save
            save_progress(progress_path, prog)

    prog["processed"] = processed
    return {"summarized": done, "touched_files": touched_files, "skipped": skipped}


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="Path to Obsidian vault")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--max-cases", type=int, default=250, help="Max cases to import OR summarize (depending on flags)")
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--progress", default=str(Path(__file__).with_suffix("").parent / "wa_opinions_progress.json"))

    # Summarization flags
    ap.add_argument("--summarize", action="store_true", help="Upgrade existing stubs with Issue/Holding/Reasoning/Defense takeaway")
    ap.add_argument("--only-tbd", action="store_true", help="When summarizing, only touch entries that still have Notes TBD")
    ap.add_argument("--no-import", action="store_true", help="Skip fetching/writing new stubs (useful with --summarize)")
    ap.add_argument("--pages", type=int, default=4, help="Pages to extract from PDF for summarization (1-10)")
    ap.add_argument("--llm-model", default="gpt-4o-mini", help="OpenAI model name for summarization")
    ap.add_argument("--cache-dir", default=str(Path(__file__).with_suffix("").parent / ".wa_opinions_cache"), help="Where to cache PDFs")

    args = ap.parse_args(argv)

    vault = Path(args.vault)
    target_dir = vault / "Case Law" / "WA Criminal"
    target_dir.mkdir(parents=True, exist_ok=True)

    progress_path = Path(args.progress)
    prog = load_progress(progress_path)
    processed: Dict[str, Dict] = prog.get("processed", {})

    # -----------------------
    # Import new stubs (default behavior)
    # -----------------------
    written = 0
    examined = 0
    topic_set = set()
    div_counts: Dict[str, int] = {"I": 0, "II": 0, "III": 0, "SUP": 0, "UNK": 0}
    topic_counts: Dict[str, int] = {}

    crim: List[Opinion] = []

    if not args.no_import:
        end = dt.date.today()
        begin = end - dt.timedelta(days=args.days)

        all_ops: List[Opinion] = []

        # Court of Appeals (adaptive date-windowing to bypass 200-result truncation)
        for page in fetch_all_in_range("C", begin, end, pub_status="All"):
            all_ops.extend(parse_search_html(page))

        # Supreme Court (same)
        for page in fetch_all_in_range("S", begin, end, pub_status="All"):
            all_ops.extend(parse_search_html(page))

        # Dedup
        ded: Dict[str, Opinion] = {op.id: op for op in all_ops}
        ops = list(ded.values())

        # Filter criminal
        crim = [op for op in ops if is_likely_criminal(op.title)]

        # Sort newest first
        def sort_key(op: Opinion):
            return op.filed_date or "0000-00-00"

        crim.sort(key=sort_key, reverse=True)

        for op in crim:
            examined += 1
            if op.id in processed:
                continue
            topics = classify_topics(op)
            for t in topics:
                topic_set.add(t)

            wrote_any = False
            for t in topics:
                topic_path = target_dir / topic_filename(t)
                ensure_topic_file(topic_path, t)
                if append_if_missing(topic_path, op):
                    wrote_any = True
                    topic_counts[t] = topic_counts.get(t, 0) + 1

            # track division
            if "Supreme Court" in op.court:
                div_counts["SUP"] += 1
            elif op.division in ("I", "II", "III"):
                div_counts[op.division] += 1
            else:
                div_counts["UNK"] += 1

            processed[op.id] = {
                **asdict(op),
                "topics": topics,
                "written": wrote_any,
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            }
            written += 1

            if written % args.batch_size == 0:
                save_progress(progress_path, {**prog, "processed": processed})

            if written >= args.max_cases:
                break

        # Update index for any topics seen in this run.
        update_wa_criminal_index(target_dir / "Index.md", sorted(topic_set))

    prog["processed"] = processed
    prog.setdefault("runs", []).append(
        {
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "days": args.days,
            "max_cases": args.max_cases,
            "examined": examined,
            "new_written": written,
            "criminal_matched": len(crim),
            "division_counts_new": div_counts,
            "topic_counts_new": topic_counts,
            "summarize": bool(args.summarize),
        }
    )
    save_progress(progress_path, prog)

    summarize_stats: Dict[str, int] = {"summarized": 0, "touched_files": 0, "skipped": 0}
    if args.summarize:
        summarize_stats = summarize_existing(
            vault=vault,
            prog=prog,
            progress_path=progress_path,
            max_cases=args.max_cases,
            only_tbd=args.only_tbd,
            pages=args.pages,
            llm_model=args.llm_model,
            cache_dir=Path(args.cache_dir),
        )
        save_progress(progress_path, prog)

    print(
        json.dumps(
            {
                "examined": examined,
                "criminal_matched": len(crim),
                "new_written": written,
                "summarize": summarize_stats,
                "division_counts_new": div_counts,
                "topic_counts_new": topic_counts,
                "topics_in_index": sorted(topic_set),
                "progress": str(progress_path),
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
