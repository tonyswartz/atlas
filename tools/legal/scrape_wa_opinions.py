#!/usr/bin/env python3
"""
WA Case Law Digest - Complete Scraper
Processes opinions and categorizes into Legal Research folders
"""
import requests
import pdfplumber
import json
import re
import io
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
BASE_URL = "https://www.courts.wa.gov"
OUTPUT_DIR = Path("Legal Research")
KANBAN_FILE = Path("kanban/tasks.json")
PROGRESS_FILE = Path(".scraper_progress")

# Comprehensive opinion URLs
OPINION_URLS = [
    # Supreme Court
    ("https://www.courts.wa.gov/opinions/pdf/1034695.pdf", "Supreme Court"),
    ("https://www.courts.wa.gov/opinions/pdf/1034512.pdf", "Supreme Court"),
    ("https://www.courts.wa.gov/opinions/pdf/1035861.pdf", "Supreme Court"),
    ("https://www.courts.wa.gov/opinions/pdf/1035306.pdf", "Supreme Court"),
    # Division I
    ("https://www.courts.wa.gov/opinions/pdf/59813-2-II Published Opinion.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/867113 order and opinion.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/877801 orderandopinion.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/864742 orderpubandopin.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/867911 order and opinion.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/874497.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/877771.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/878727.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/875264.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/871960.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/862162.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/870114.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/864041.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/878638.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/865099.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/875981.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/873245.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/874195.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/871463.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/874381.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/876597.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/880322.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/863673.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/866621.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/868802.pdf", "Div I"),
    ("https://www.courts.wa.gov/opinions/pdf/872621.pdf", "Div I"),
    # Division II
    ("https://www.courts.wa.gov/opinions/pdf/D2 60089-7-II Unpublished Opinion.pdf", "Div II"),
    ("https://www.courts.wa.gov/opinions/pdf/D2 59161-8-II Unpublished Opinion.pdf", "Div II"),
    ("https://www.courts.wa.gov/opinions/pdf/D2 60288-1-II Unpublished Opinion.pdf", "Div II"),
    ("https://www.courts.wa.gov/opinions/pdf/D2 59373-4-II Unpublished Opinion.pdf", "Div II"),
    ("https://www.courts.wa.gov/opinions/pdf/D2 59978-3-II Unpublished Opinion.pdf", "Div II"),
    # Division III
    ("https://www.courts.wa.gov/opinions/pdf/402711_unp.pdf", "Div III"),
    ("https://www.courts.wa.gov/opinions/pdf/407977_unp.pdf", "Div III"),
    ("https://www.courts.wa.gov/opinions/pdf/406423_unp.pdf", "Div III"),
    ("https://www.courts.wa.gov/opinions/pdf/407217_unp.pdf", "Div III"),
    ("https://www.courts.wa.gov/opinions/pdf/401910_unp.pdf", "Div III"),
    ("https://www.courts.wa.gov/opinions/pdf/403050_unp.pdf", "Div III"),
    ("https://www.courts.wa.gov/opinions/pdf/403777_unp.pdf", "Div III"),
]

# Categories with keywords
CATEGORIES = {
    "criminal-procedure": ["search", "seizure", "arrest", "miranda", "fourth amendment", 
                           "suppress", "warrant", "probable cause", "evidence", "motion to suppress"],
    "sentencing": ["sentencing", "sentence", "guidelines", "enhancement", "deferral",
                   "community custody", "release", "probation", "offender score"],
    "dui-vehicle": ["dui", "driving under", "intoxicated", "vehicle", "breathalyzer",
                    "blood test", "alcohol", "dwls", "physical control", "drive"],
    "family-law": ["marriage", "divorce", "custody", "parenting", "child support",
                   "dissolution", "dependency", "termination", "parentage", "detention"],
    "civil-litigation": ["civil", "procedure", "discovery", "summary judgment", 
                         "dismiss", "jurisdiction", "joinder"],
    "property": ["property", "real estate", "landlord", "tenant", "easement",
                 "title", "ownership", "possession", "zoning", "eminent domain"],
    "torts": ["tort", "negligence", "duty", "breach", "damages", "personal injury",
              "wrongful death", "defamation", "malpractice", "premises liability"],
    "contracts": ["contract", "breach", "formation", "consideration", "performance", "restitution"],
    "constitutional": ["constitutional", "first amendment", "equal protection", 
                       "free speech", "civil rights", "due process"],
    "admin": ["administrative", "agency", "regulation", "hearing", "appeal", "deference"]
}

def process_single_opinion(url_division):
    """Process a single opinion PDF."""
    url, div = url_division
    
    try:
        # Download
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            return None
        
        # Extract text
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        
        if not text.strip():
            return None
        
        # Parse case info
        case_info = parse_case_info(text, url, div)
        category = categorize_case(text, case_info.get('title', ''))
        summary = generate_summary(text)
        
        # Save
        filepath = save_case(case_info, summary, category)
        
        return {
            "title": case_info.get('title', 'Unknown')[:100],
            "case_number": case_info.get('case_number', 'N/A'),
            "court": case_info.get('court', 'N/A'),
            "date": case_info.get('date', 'N/A'),
            "category": category,
            "location": str(filepath)
        }
    except Exception as e:
        return None

def parse_case_info(text, url, div_hint):
    """Extract case information from PDF text."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    info = {
        "pdf_url": url,
        "title": "",
        "court": "",
        "date": "",
        "case_number": "",
        "full_text": text
    }
    
    text_lower = text.lower()
    
    # Court detection
    if "supreme court" in text_lower[:500]:
        info["court"] = "Washington Supreme Court"
    elif "division i" in text_lower[:400]:
        info["court"] = "WA Court of Appeals, Division I"
    elif "division ii" in text_lower[:400]:
        info["court"] = "WA Court of Appeals, Division II"
    elif "division iii" in text_lower[:400]:
        info["court"] = "WA Court of Appeals, Division III"
    elif div_hint == "Div I":
        info["court"] = "WA Court of Appeals, Division I"
    elif div_hint == "Div II":
        info["court"] = "WA Court of Appeals, Division II"
    elif div_hint == "Div III":
        info["court"] = "WA Court of Appeals, Division III"
    
    # Date extraction
    for line in lines[:15]:
        match = re.search(r'FILED\s+([a-z]+\.?\s+\d{1,2},?\s+\d{4})', line, re.IGNORECASE)
        if match:
            info["date"] = match.group(1)
            break
    
    # Case number
    for line in lines[:10]:
        match = re.search(r'No\.?\s*(\d+[-\s]\d+[-\s]\w+)', line, re.IGNORECASE)
        if match:
            info["case_number"] = match.group(1)
            break
    
    if not info["case_number"]:
        fn = url.split('/')[-1].replace('.pdf', '')
        info["case_number"] = re.sub(r'[^\d-]', '', fn)
    
    # Title
    for line in lines:
        if len(line) > 20 and ('v.' in line.lower() or 'in re' in line.lower()):
            if not any(x in line.lower()[:30] for x in ['filed', 'in the', 'court of']):
                info["title"] = line
                break
    
    return info

def categorize_case(text, title):
    """Categorize based on content."""
    search = (text + " " + (title or "")).lower()
    scores = {}
    
    for cat, keywords in CATEGORIES.items():
        score = sum(3 if kw in title.lower() else 1 for kw in keywords if kw in search)
        if score:
            scores[cat] = score
    
    return max(scores, key=scores.get) if scores else "civil-litigation"

def generate_summary(text):
    """Generate case summary."""
    tl = text.lower()
    parts = []
    
    # Outcome
    if "affirm" in tl:
        parts.append("Court affirmed the lower court's decision")
    elif "reverse" in tl:
        parts.append("Court reversed the lower court's decision")
    elif "remand" in tl:
        parts.append("Court remanded for further proceedings")
    elif "dismiss" in tl:
        parts.append("Appeal was dismissed")
    
    # Key issues
    issues = []
    issue_markers = {
        "Fourth Amendment/Search": ["fourth amendment", "search and seizure", "warrantless"],
        "Miranda": ["miranda"],
        "Ineffective Counsel": ["ineffective assistance"],
        "Sentencing": ["sentencing", "offender score"],
        "Custody": ["custody", "parenting plan"],
        "Child Support": ["child support"],
        "Dependency": ["dependency"],
        "Negligence": ["negligence"],
        "Contract Breach": ["breach of contract"],
        "Civil Rights": ["civil rights", "discrimination"]
    }
    
    for issue, markers in issue_markers.items():
        if any(m in tl for m in markers):
            issues.append(issue)
    
    if issues:
        parts.append(f"Key issues: {', '.join(issues[:3])}")
    
    return ". ".join(parts) if parts else "Court issued a decision."

def save_case(case_info, summary, category):
    """Save case to markdown file."""
    cat_dir = OUTPUT_DIR / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    
    case_num = case_info.get('case_number', 'unknown').replace(' ', '-')
    title = re.sub(r'[^\w\s-]', '', case_info.get('title', 'unknown'))[:35]
    title = re.sub(r'\s+', '-', title).lower()
    filename = f"{case_num[:15]}-{title}.md"
    
    filepath = cat_dir / filename
    
    content = f"""---
title: "{case_info.get('title', 'Unknown Case')}"
court: "{case_info.get('court', 'Washington Courts')}"
date: "{case_info.get('date', 'Unknown Date')}"
case_number: "{case_info.get('case_number', 'N/A')}"
category: "{category}"
source_url: "{case_info.get('pdf_url', '')}"
---

## Holding Summary

{summary}

## Case Details

- **Court:** {case_info.get('court', 'N/A')}
- **Date Filed:** {case_info.get('date', 'N/A')}
- **Case Number:** {case_info.get('case_number', 'N/A')}
- **Category:** {category}

---

*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    return filepath

def update_progress(current, total, cases):
    """Update progress tracking."""
    progress = {
        "current": current,
        "total": total,
        "percent": round(current/total*100, 1) if total > 0 else 0,
        "last_updated": datetime.now().isoformat()
    }
    
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)
    
    # Update Kanban
    try:
        if KANBAN_FILE.exists():
            with open(KANBAN_FILE, 'r') as f:
                tasks = json.load(f)
        else:
            tasks = []
        
        digest_task = {"id": "wa-case-digest", "title": "WA Case Law Digest Rebuild", 
                      "status": "in_progress", "progress": progress, "cases": cases}
        
        # Remove old and add new
        tasks = [t for t in tasks if t.get("id") != "wa-case-digest"]
        tasks.append(digest_task)
        
        with open(KANBAN_FILE, 'w') as f:
            json.dump(tasks, f, indent=2)
    except:
        pass

def main():
    print("="*60)
    print("WA CASE LAW DIGEST SYSTEM")
    print("="*60)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    total = len(OPINION_URLS)
    cases = []
    
    for i, url_div in enumerate(OPINION_URLS, 1):
        result = process_single_opinion(url_div)
        
        if result:
            cases.append(result)
            print(f"[{i}/{total}] ✅ {result['category']}: {result['title'][:50]}...")
        else:
            print(f"[{i}/{total}] ❌ Failed: {url_div[0].split('/')[-1][:40]}")
        
        # Progress every 50
        if i % 50 == 0:
            update_progress(i, total, cases)
            print(f"\n>>> PROGRESS: {i}/{total} ({round(i/total*100,1)}%) <<<")
        
        time.sleep(0.3)
    
    # Final updates
    update_progress(total, total, cases)
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "total": len(cases),
        "cases": cases
    }
    
    with open(OUTPUT_DIR / "digest_report.json", 'w') as f:
        json.dump(report, f, indent=2)
    
    # Count by category
    by_cat = {}
    for c in cases:
        cat = c['category']
        by_cat[cat] = by_cat.get(cat, 0) + 1
    
    print("\n" + "="*60)
    print(f"✅ COMPLETE: {len(cases)} cases processed")
    print(f"📁 Categories: {by_cat}")
    print("="*60)
    
    # WhatsApp progress message
    print("\n📱 WHATSAPP PROGRESS UPDATE:")
    print("-" * 40)
    print(f"✅ Processed {len(cases)} WA Court opinions")
    print(f"📊 Progress: {len(cases)}/{total} (100%)")
    print(f"📁 Categories: {', '.join(sorted(by_cat.keys()))}")
    for cat, count in sorted(by_cat.items()):
        print(f"   • {cat}: {count}")
    print("-" * 40)

if __name__ == "__main__":
    main()
