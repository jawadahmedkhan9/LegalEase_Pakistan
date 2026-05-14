# ============================================================================
# E-LEARNING PORTAL — AI-Powered Backend Router
# File: education_router.py
# Version: 2.0 — Per-law course generation + rich lesson content
#
# Key changes from v1:
#   - _generate_course_for_law(): generates one course per individual law
#     with rich lessons (content, key_points, real_world_example, what_to_know)
#   - POST /admin/generate-law-courses: generates 20+ courses automatically
#   - Updated bootstrap to call law-level course generation
#   - GET /courses/categories now returns dynamic list from generated courses
#   - All existing endpoints fully preserved
#
# Mount: app.include_router(education_router, prefix="/api/education")
# ============================================================================

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import os
import uuid
import re
import random
from datetime import datetime
import logging

logger = logging.getLogger("LegalEase.Education")

education_router = APIRouter(tags=["E-Learning Portal"])

# ============================================================================
# CONFIG — maps category name to the JSON file on disk
# ============================================================================

JSON_FILES = {
    "Family Law":          "family_laws.json",
    "Banking Law":         "Banking_Laws.json",
    "Land & Property Law": "Land-Property_Law.json",
    "Police Law":          "Police_Laws.json",
    "Religious Law":       "Religious_Laws.json",
}

# Default difficulty levels per category
COURSE_LEVELS = {
    "Family Law":          "Intermediate",
    "Banking Law":         "Advanced",
    "Land & Property Law": "Beginner",
    "Police Law":          "Intermediate",
    "Religious Law":       "Beginner",
}

# Category emoji for UI
CATEGORY_EMOJI = {
    "Family Law":          "👨‍👩‍👧",
    "Banking Law":         "🏦",
    "Land & Property Law": "🏘️",
    "Police Law":          "👮",
    "Religious Law":       "🕌",
}

# ── Law-specific URL lookup (mirrors App.py LAW_SPECIFIC_URL_MAP) ────────────
# Maps lowercased law name → direct pakistancode.gov.pk URL
_CATEGORY_FALLBACK_URLS = {
    "Family Law":          "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJaW-sg-jjjjjjjjjjjjj",
    "Banking Law":         "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ%2BV-sg-jjjjjjjjjjjjj",
    "Land & Property Law": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJw%3D-sg-jjjjjjjjjjjjj",
    "Police Law":          "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5s%3D-sg-jjjjjjjjjjjjj",
    "Religious Law":       "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZ2V-sg-jjjjjjjjjjjjj",
}

_LAW_SPECIFIC_URL_MAP = {
    # Banking / Financial
    "asian development bank ordinance, 1971": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Fw-sg-jjjjjjjjjjjjj",
    "bankers' books evidence act, 1891": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJo%3D-sg-jjjjjjjjjjjjj",
    "banking companies ordinances, 1962": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ%2BV-sg-jjjjjjjjjjjjj",
    "the banking companies ordinance, 1962": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ%2BV-sg-jjjjjjjjjjjjj",
    "banking tribunals (validation of orders) act, 1994": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apmcbA%3D%3D-sg-jjjjjjjjjjjjj",
    "banks (transfer of assets and liabilities) act, 1994": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUZWJu-sg-jjjjjjjjjjjjj",
    "foreign currency accounts (protection) ordinance, 2001": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cp%2BUY2Ju-sg-jjjjjjjjjjjjj",
    "foreign exchange (prevention of payments) act, 1972": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUZWFs-sg-jjjjjjjjjjjjj",
    "foreign private investment (promotion and protection) act, 1976": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUZWRv-sg-jjjjjjjjjjjjj",
    "government savings banks act, 1873": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a58%3D-sg-jjjjjjjjjjjjj",
    "industrial development bank of pakistan (reorganization and conversion) act, 2011": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FsZ5o%3D-sg-jjjjjjjjjjjjj",
    "islamic development bank ordinance, 1978": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cZiY-sg-jjjjjjjjjjjjj",
    "modaraba companies and modaraba (floatation and control) ordinance, 1980": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cpyb-sg-jjjjjjjjjjjjj",
    "national bank of pakistan (nbp) ordinance, 1949": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aVaQ%3D%3D-sg-jjjjjjjjjjjjj",
    "non-performing assets and rehabilitation of industrial undertaking (legal proceedings) ordinance, 2000": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FobZk%3D-sg-jjjjjjjjjjjjj",
    "pakistan banking (prevention of default and evasion of liabilities) ordinance, 1947": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aUag%3D%3D-sg-jjjjjjjjjjjjj",
    "the pakistan banking (prevention of default and evasion of liabilities) ordinance, 1947": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aUag%3D%3D-sg-jjjjjjjjjjjjj",
    "pakistan banking and finance services commision act, 1992": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apmZag%3D%3D-sg-jjjjjjjjjjjjj",
    "state bank of pakistan (sbp) act, 1956": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BbZw%3D%3D-sg-jjjjjjjjjjjjj",
    "stock exchange (corporatisation, demutualization and integration) act, 2012": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2Fqapg%3D-sg-jjjjjjjjjjjjj",
    "establishment of the federal bank for cooperatives and regulation of cooperative banking act, 1977": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2hv-sg-jjjjjjjjjjjjj",
    "the establishment of the federal bank for cooperatives and regulation of cooperative banking act, 1977": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2hv-sg-jjjjjjjjjjjjj",
    # Religious
    "ehtram-e-ramazan ordinance, 1981": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZ2V-sg-jjjjjjjjjjjjj",
    "enforcement of shari'ah act, 1991": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apmXZA%3D%3D-sg-jjjjjjjjjjjjj",
    "pakistan madarasah education (establishment and affiliation of model dini madaris) board ordinance, 2001": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cp%2BUY2Jr-sg-jjjjjjjjjjjjj",
    "publication of holy quran (elimination of printing errors) act, 1973": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUZWJo-sg-jjjjjjjjjjjjj",
    "sikh gurdwaras (supplementary) act, 1925": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap6X-sg-jjjjjjjjjjjjj",
    # Land / Property
    "agricultural produce (grading and marketing) act, 1937": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b56d-sg-jjjjjjjjjjjjj",
    "agricultural produce cess act, 1940": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJac-sg-jjjjjjjjjjjjj",
    "agriculturists loans act, 1884": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bp4%3D-sg-jjjjjjjjjjjjj",
    "dekkhan agriculturists relief act, 1879": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZs%3D-sg-jjjjjjjjjjjjj",
    "land acquisition (mines) act, 1885": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5Y%3D-sg-jjjjjjjjjjjjj",
    "land control (karachi division) act, 1952": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BXbA%3D%3D-sg-jjjjjjjjjjjjj",
    "land improvement loans act, 1883": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpw%3D-sg-jjjjjjjjjjjjj",
    "protection of communal properties of minorities ordinance, 2001": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FrbZ4%3D-sg-jjjjjjjjjjjjj",
    "requisitioned land (continuance of powers) ordinance, 1969": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cZad-sg-jjjjjjjjjjjjj",
    "sindh revenue jurisdiction act, 1876": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJw%3D-sg-jjjjjjjjjjjjj",
    "the sindh revenue jurisdiction act, 1876": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJw%3D-sg-jjjjjjjjjjjjj",
    "waste lands (claims) act, 1863": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apw%3D-sg-jjjjjjjjjjjjj",
    "zakat and ushr ordinance, 1980": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cpuY-sg-jjjjjjjjjjjjj",
    # Police
    "airports security force act, 1975": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Fr-sg-jjjjjjjjjjjjj",
    "pakistan railways police act, 1977": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2hv-sg-jjjjjjjjjjjjj",
    "police (incitement to disaffection) act, 1922": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apyX-sg-jjjjjjjjjjjjj",
    "police act, 1888": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5s%3D-sg-jjjjjjjjjjjjj",
    # Family
    "anand marriage act, 1909": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apeX-sg-jjjjjjjjjjjjj",
    "arya marriage validation act, 1937": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5%2BW-sg-jjjjjjjjjjjjj",
    "child marriage restraint act, 1929": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2Bb-sg-jjjjjjjjjjjjj",
    "christian marriage act, 1872": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a54%3D-sg-jjjjjjjjjjjjj",
    "claims for maintenance (recovery abroad) ordinance, 1959": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aZZg%3D%3D-sg-jjjjjjjjjjjjj",
    "dissolution of muslims marriages act, 1939": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJaW-sg-jjjjjjjjjjjjj",
    "divorce act, 1869": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5Y%3D-sg-jjjjjjjjjjjjj",
    "dowry and bridal gifts (restriction) act, 1976": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Rp-sg-jjjjjjjjjjjjj",
    "guardians and wards act, 1890": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJc%3D-sg-jjjjjjjjjjjjj",
    "hindu disposition of property act, 1916": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apic-sg-jjjjjjjjjjjjj",
    "hindu inheritance (removal of disablities) act, 1928": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BZ-sg-jjjjjjjjjjjjj",
    "hindu marriage disabilities removal act, 1946": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJiV-sg-jjjjjjjjjjjjj",
    "hindu married women's right to separate residence and maintenance act, 1946": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJed-sg-jjjjjjjjjjjjj",
    "hindu widows' re-marriage act, 1856": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apc%3D-sg-jjjjjjjjjjjjj",
    "hindu women's rights to property act, 1937": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5%2BV-sg-jjjjjjjjjjjjj",
    "marriage functions (prohibition of ostentatious displays and wasteful expenses) ordinance, 2000": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaXZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "married women's property act, 1874": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJg%3D-sg-jjjjjjjjjjjjj",
    "parsi marriage and divorce act, 1936": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b56a-sg-jjjjjjjjjjjjj",
    "special marriage act, 1872": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5s%3D-sg-jjjjjjjjjjjjj",
    "muslim family laws ordinance, 1961": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aZZA%3D%3D-sg-jjjjjjjjjjjjj",
    "the muslim family laws ordinance, 1961": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aZZA%3D%3D-sg-jjjjjjjjjjjjj",
}

def _get_law_download_url(law_name: str, category: str) -> str:
    """
    Returns the most specific pakistancode.gov.pk URL for a law.
    Tries exact law-name match, then strips 'The ' prefix, then falls back to category URL.
    """
    key = law_name.strip().lower()
    if key in _LAW_SPECIFIC_URL_MAP:
        return _LAW_SPECIFIC_URL_MAP[key]
    stripped = re.sub(r"^the\s+", "", key)
    if stripped in _LAW_SPECIFIC_URL_MAP:
        return _LAW_SPECIFIC_URL_MAP[stripped]
    return _CATEGORY_FALLBACK_URLS.get(category, "https://pakistancode.gov.pk")

COURSES_DB_FILE      = "edu_courses_db.json"
PROGRESS_DB_FILE     = "edu_progress_db.json"
ASSESSMENTS_DB_FILE  = "edu_assessments_db.json"
LIBRARY_DB_FILE      = "edu_library_db.json"

_courses_cache:     Dict[str, Dict] = {}
_progress_cache:    Dict[str, Dict] = {}
_assessments_cache: Dict[str, Dict] = {}
_library_cache:     Dict[str, Dict] = {}

# ============================================================================
# DB HELPERS
# ============================================================================

def _load(path: str, cache: dict):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cache.update(json.load(f))
        except Exception as e:
            logger.warning(f"Could not load {path}: {e}")

def _dump(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ============================================================================
# LAW JSON PARSER — normalises both file structures into flat sections list
# ============================================================================

def _load_law_sections(filepath: str) -> List[Dict]:
    """
    Handles two JSON structures:
      A) [{law_name, sections:[{title, content, metadata}]}]   <- most files
      B) [{title, source, content, section_path, metadata}]    <- Religious_Laws.json (flat)
    Returns a unified flat list.
    """
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return []

    sections = []
    first = data[0]

    if "sections" in first:
        # Structure A: nested
        for law in data:
            law_name = law.get("law_name", "Unknown Law")
            for sec in law.get("sections", []):
                sections.append({
                    "law_name":     law_name,
                    "title":        sec.get("title", ""),
                    "content":      sec.get("content", ""),
                    "metadata":     sec.get("metadata", {}),
                    "section_path": sec.get("section_path", []),
                })
    else:
        # Structure B: flat (Religious_Laws.json)
        for sec in data:
            sections.append({
                "law_name":     sec.get("source", "Unknown Law"),
                "title":        sec.get("title", ""),
                "content":      sec.get("content", ""),
                "metadata":     sec.get("metadata", {}),
                "section_path": sec.get("section_path", []),
            })
    return sections


def _get_laws_in_category(category: str) -> List[Dict]:
    """
    Returns a list of all individual laws in a category file.
    Each entry: { law_name, sections: [...] }
    """
    fname = JSON_FILES.get(category)
    if not fname or not os.path.exists(fname):
        return []

    with open(fname, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data:
        return []

    first = data[0]

    if "sections" in first:
        # Structure A: each item is one law
        return [
            {
                "law_name": law.get("law_name", "Unknown Law"),
                "sections": law.get("sections", []),
                "category": category,
            }
            for law in data
            if law.get("law_name") and law.get("sections")
        ]
    else:
        # Structure B: flat — group by source
        grouped: Dict[str, List] = {}
        for sec in data:
            source = sec.get("source", "Unknown Law")
            if source not in grouped:
                grouped[source] = []
            grouped[source].append({
                "title":        sec.get("title", ""),
                "content":      sec.get("content", ""),
                "metadata":     sec.get("metadata", {}),
                "section_path": sec.get("section_path", []),
            })
        return [
            {"law_name": law_name, "sections": secs, "category": category}
            for law_name, secs in grouped.items()
        ]


def _get_rich_sections_text(category: str, max_chars: int = 5000) -> str:
    """Return the most content-rich sections as a single string for AI prompting."""
    fname = JSON_FILES.get(category)
    if not fname:
        return ""
    sections = _load_law_sections(fname)
    sections.sort(key=lambda s: len(s.get("content", "")), reverse=True)
    parts, total = [], 0
    for s in sections:
        content = s.get("content", "").strip()
        if len(content) < 60:
            continue
        chunk = f"[{s['law_name']} — {s['title']}]\n{content}"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n".join(parts)


# ============================================================================
# GROQ CLIENT
# ============================================================================

def _get_groq():
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        return Groq(api_key=api_key)
    except Exception as e:
        logger.error(f"Groq init failed: {e}")
        return None


def _groq_complete(prompt: str, system: str, max_tokens: int = 2000) -> Optional[str]:
    client = _get_groq()
    if not client:
        return None
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return None


def _parse_json_safe(raw: str):
    """Strip markdown fences and parse JSON."""
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)

# ============================================================================
# COURSE GENERATION — per-category (original, kept for compatibility)
# ============================================================================

def _generate_course_from_rag(category: str) -> Optional[Dict]:
    law_text = _get_rich_sections_text(category, max_chars=5000)
    if not law_text:
        return None

    system = (
        "You are a Pakistani legal education expert. "
        "Generate a structured online course based ONLY on the actual Pakistani law text provided. "
        "Respond ONLY with a valid JSON object — no markdown fences, no preamble, no trailing text."
    )

    prompt = f"""Using the following actual Pakistani {category} text, generate a course with this exact JSON structure:

{{
  "title": "Specific descriptive course title",
  "desc": "2-sentence description of what students will learn",
  "overview": "3-4 sentence overview of this area of Pakistani law",
  "key_topics": ["topic 1", "topic 2", "topic 3", "topic 4", "topic 5"],
  "lessons": [
    {{
      "index": 0,
      "title": "Lesson title",
      "summary": "What this lesson covers in 1-2 sentences",
      "content": "3-4 paragraph plain-language explanation of this topic. Explain what the law says, why it matters, and what it means for ordinary people in Pakistan.",
      "key_points": ["Key point 1", "Key point 2", "Key point 3"],
      "real_world_example": "A realistic scenario showing how this law applies in everyday life in Pakistan.",
      "what_to_know": "The single most important takeaway from this lesson in one sentence.",
      "law_references": ["Law name — Section X"]
    }}
  ],
  "learning_outcomes": ["outcome 1", "outcome 2", "outcome 3"],
  "difficulty_notes": "Who this course is for and prerequisites"
}}

Generate 8-12 lessons. Each lesson must have full content, key_points, real_world_example and what_to_know.

LAW TEXT:
{law_text}

Return ONLY the JSON object:"""

    raw = _groq_complete(prompt, system, max_tokens=3500)
    if not raw:
        return None
    try:
        return _parse_json_safe(raw)
    except Exception as e:
        logger.error(f"Course JSON parse error ({category}): {e} | Raw: {raw[:300]}")
        return None


# ============================================================================
# COURSE GENERATION — per individual law (NEW in v2)
# ============================================================================

def _generate_course_for_law(law_name: str, category: str, sections: List[Dict]) -> Optional[Dict]:
    """
    Generate a rich course for ONE specific law (e.g. "The Divorce Act, 1869").
    Each lesson has: content, key_points, real_world_example, what_to_know.
    """
    # Build law text from sections, prefer longer/richer sections
    rich_sections = sorted(
        [s for s in sections if len(s.get("content", "")) > 80],
        key=lambda s: len(s.get("content", "")),
        reverse=True,
    )[:15]

    law_text = "\n\n".join(
        f"[Section: {s.get('title', 'Untitled')}]\n{s.get('content', '')[:700]}"
        for s in rich_sections
    )

    if not law_text.strip():
        return None

    system = (
        "You are a Pakistani legal educator creating accessible, practical online courses. "
        "Write in plain English that any educated Pakistani citizen can understand. "
        "Respond ONLY with a valid JSON object — no markdown fences, no preamble."
    )

    prompt = f"""Create a comprehensive educational course on "{law_name}" using ONLY the law text below.

Return EXACTLY this JSON structure:

{{
  "title": "Clear, descriptive course title (can differ from the law name, make it educational)",
  "desc": "2-sentence description of what students will learn and why it matters",
  "overview": "3-4 sentence overview explaining this law's purpose, who it protects, and its significance in Pakistan",
  "key_topics": ["topic 1", "topic 2", "topic 3", "topic 4", "topic 5"],
  "lessons": [
    {{
      "index": 0,
      "title": "Lesson title",
      "summary": "1-2 sentence summary of what this lesson covers",
      "content": "Write 3-5 substantial paragraphs explaining this topic in plain language. Cover: what does this section of the law say, what does it mean in practice, who is affected, what rights or obligations does it create, and why it matters. Use clear, simple language a non-lawyer can understand.",
      "key_points": [
        "Clear, actionable key point 1",
        "Clear, actionable key point 2",
        "Clear, actionable key point 3",
        "Clear, actionable key point 4"
      ],
      "real_world_example": "Write a realistic 3-4 sentence scenario showing exactly how this law applies in a real Pakistani context. Use Pakistani names and situations.",
      "what_to_know": "The single most critical takeaway from this lesson — one sentence that summarises the most important thing to remember.",
      "law_references": ["Exact section reference from the law"]
    }}
  ],
  "learning_outcomes": [
    "Specific outcome 1 — what the student will be able to do or understand",
    "Specific outcome 2",
    "Specific outcome 3",
    "Specific outcome 4"
  ],
  "difficulty_notes": "Brief note on who this course is for and any background knowledge needed"
}}

Rules:
- Generate 6-10 lessons covering the major sections of the law
- Each lesson MUST have a full "content" field with 3-5 paragraphs — not just a summary
- Each lesson MUST have 3-4 "key_points" as a JSON array
- Each lesson MUST have a "real_world_example" with a Pakistani scenario
- Each lesson MUST have a "what_to_know" sentence
- Focus on practical understanding, not legal jargon

LAW TEXT FOR "{law_name}":
{law_text}

Return ONLY the JSON object, no other text:"""

    raw = _groq_complete(prompt, system, max_tokens=4000)
    if not raw:
        return None
    try:
        data = _parse_json_safe(raw)
        # Validate lessons have rich content
        for i, lesson in enumerate(data.get("lessons", [])):
            if "content" not in lesson or len(lesson["content"]) < 100:
                lesson["content"] = lesson.get("summary", "Content not available for this lesson.")
            if "key_points" not in lesson or not isinstance(lesson["key_points"], list):
                lesson["key_points"] = []
            if "real_world_example" not in lesson:
                lesson["real_world_example"] = ""
            if "what_to_know" not in lesson:
                lesson["what_to_know"] = ""
            lesson["index"] = i
        return data
    except Exception as e:
        logger.error(f"Law course JSON parse error ({law_name}): {e} | Raw: {raw[:400]}")
        return None


def _law_name_to_course_id(law_name: str) -> str:
    """Convert a law name to a stable course ID."""
    slug = re.sub(r"[^a-z0-9]", "-", law_name.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")[:60]
    return f"law-{slug}"


def _build_course_record(category: str, ai_data: Dict, law_name: Optional[str] = None) -> Dict:
    now = datetime.utcnow().isoformat()
    if law_name:
        course_id = _law_name_to_course_id(law_name)
    else:
        course_id = f"course-{re.sub(r'[^a-z0-9]', '-', category.lower())}"

    lessons = ai_data.get("lessons", [])
    return {
        "id":                course_id,
        "category":          category,
        "law_name":          law_name or "",
        "title":             ai_data.get("title", law_name or f"{category} Course"),
        "desc":              ai_data.get("desc", ""),
        "overview":          ai_data.get("overview", ""),
        "key_topics":        ai_data.get("key_topics", []),
        "lessons":           lessons,
        "lesson_titles":     [l.get("title", f"Lesson {i+1}") for i, l in enumerate(lessons)],
        "learning_outcomes": ai_data.get("learning_outcomes", []),
        "difficulty_notes":  ai_data.get("difficulty_notes", ""),
        "level":             COURSE_LEVELS.get(category, "Intermediate"),
        "hours":             round(len(lessons) * 0.4, 1),
        "active":            True,
        "ai_generated":      True,
        "created_at":        now,
        "updated_at":        now,
    }

# ============================================================================
# MCQ GENERATION
# ============================================================================

def _generate_mcqs(category: str, count: int = 10) -> List[Dict]:
    fname = JSON_FILES.get(category)
    if not fname:
        return []
    sections = _load_law_sections(fname)
    rich = [s for s in sections if len(s.get("content", "")) > 100]
    random.shuffle(rich)
    selected = rich[:15]

    law_text = "\n\n".join(
        f"[{s['law_name']} — {s['title']}]\n{s['content'][:500]}"
        for s in selected
    )

    system = (
        "You are a Pakistani legal examiner creating exam questions. "
        "Every question must be directly answerable from the law text provided. "
        "Respond ONLY with a valid JSON array — no markdown, no preamble."
    )

    prompt = f"""Generate exactly {count} multiple-choice questions from this Pakistani {category} text.

Return a JSON array:
[
  {{
    "text": "Question text?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct": 0,
    "explanation": "Brief explanation citing the specific law or section",
    "law_reference": "Law name — Section number"
  }}
]

Rules:
- "correct" is the 0-based index of the correct answer
- All 4 options must be plausible
- Cover different laws and sections
- Questions must be factual

LAW TEXT:
{law_text}

Return ONLY the JSON array:"""

    raw = _groq_complete(prompt, system, max_tokens=3000)
    if not raw:
        return []

    raw = re.sub(r"```json|```", "", raw).strip()
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        questions = json.loads(raw)
        validated = []
        for i, q in enumerate(questions):
            if not all(k in q for k in ("text", "options", "correct", "explanation")):
                continue
            opts = q["options"][:4]
            correct = int(q["correct"])
            if len(opts) < 2 or not (0 <= correct < len(opts)):
                continue
            validated.append({
                "id":            f"q{i+1}",
                "text":          str(q["text"]),
                "options":       opts,
                "correct":       correct,
                "explanation":   str(q.get("explanation", "")),
                "law_reference": str(q.get("law_reference", "")),
            })
        return validated
    except Exception as e:
        logger.error(f"MCQ parse error ({category}): {e}")
        return []

# ============================================================================
# LAW LIBRARY AUTO-POPULATE
# ============================================================================

def _populate_library_from_json() -> Dict:
    library = {}

    for category, fname in JSON_FILES.items():
        if not os.path.exists(fname):
            logger.warning(f"JSON file not found: {fname}")
            continue

        with open(fname, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            continue

        first = data[0]

        if "sections" in first:
            for law in data:
                law_name = law.get("law_name", "").strip()
                if not law_name:
                    continue
                sections = law.get("sections", [])
                year = 0
                for sec in sections:
                    y = sec.get("metadata", {}).get("year")
                    if y:
                        year = int(y)
                        break
                if not year:
                    m = re.search(r'\b(1[6-9]\d{2}|20[0-2]\d)\b', law_name)
                    year = int(m.group(1)) if m else 0
                tags = list({
                    w.lower() for sec in sections[:5]
                    for w in sec.get("title", "").split()
                    if len(w) > 4
                })[:8]
                entry_id = f"lib-{uuid.uuid4().hex[:8]}"
                library[entry_id] = {
                    "id":            entry_id,
                    "title":         law_name,
                    "category":      category,
                    "description":   f"Pakistani {category} legislation — {len(sections)} sections.",
                    "year":          year,
                    "section_count": len(sections),
                    "tags":          tags,
                    "download_url":  _get_law_download_url(law_name, category),
                    "active":        True,
                    "created_at":    datetime.utcnow().isoformat(),
                }
        else:
            seen = set()
            for sec in data:
                source = sec.get("source", "").strip()
                if not source or source in seen:
                    continue
                seen.add(source)
                year = 0
                y = sec.get("metadata", {}).get("year")
                if y:
                    year = int(y)
                else:
                    m = re.search(r'\b(1[6-9]\d{2}|20[0-2]\d)\b', source)
                    year = int(m.group(1)) if m else 0
                tags = [w.lower() for w in source.split() if len(w) > 4][:6]
                entry_id = f"lib-{uuid.uuid4().hex[:8]}"
                library[entry_id] = {
                    "id":            entry_id,
                    "title":         source,
                    "category":      category,
                    "description":   f"Pakistani {category} — {source}.",
                    "year":          year,
                    "section_count": 1,
                    "tags":          tags,
                    "download_url":  _get_law_download_url(source, category),
                    "active":        True,
                    "created_at":    datetime.utcnow().isoformat(),
                }
    return library

# ============================================================================
# INITIALISE ON IMPORT
# ============================================================================

_load(COURSES_DB_FILE,     _courses_cache)
_load(PROGRESS_DB_FILE,    _progress_cache)
_load(ASSESSMENTS_DB_FILE, _assessments_cache)
_load(LIBRARY_DB_FILE,     _library_cache)

if not _library_cache:
    logger.info("Auto-populating law library from JSON files...")
    _library_cache.update(_populate_library_from_json())
    _dump(LIBRARY_DB_FILE, _library_cache)
    logger.info(f"Library ready: {len(_library_cache)} laws loaded")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class CoursePublic(BaseModel):
    id: str
    category: str
    title: str
    desc: str
    overview: str = ""
    key_topics: List[str] = []
    lessons: List[Dict] = []
    lesson_titles: List[str] = []
    learning_outcomes: List[str] = []
    difficulty_notes: str = ""
    level: str
    hours: float
    active: bool
    ai_generated: bool = False
    law_name: str = ""

class ProgressUpdate(BaseModel):
    user_id: str
    course_id: str
    lesson_index: int = Field(..., ge=0)

class ProgressResponse(BaseModel):
    user_id: str
    course_id: str
    lessons_completed: int
    total_lessons: int
    progress_percent: int
    last_lesson: int
    completed: bool
    updated_at: str

class LawEntry(BaseModel):
    id: str
    title: str
    category: str
    description: str
    year: int
    section_count: int
    tags: List[str]
    download_url: str
    active: bool

class QuestionPublic(BaseModel):
    id: str
    text: str
    options: List[str]

class AssessmentPublic(BaseModel):
    id: str
    course_id: str
    title: str
    description: str
    pass_mark: int
    question_count: int
    ai_generated: bool = False

class AssessmentWithQuestions(AssessmentPublic):
    questions: List[QuestionPublic]

class AnswerSubmit(BaseModel):
    answers: Dict[str, int]

class AnswerResult(BaseModel):
    question_id: str
    correct: bool
    chosen: int
    correct_answer: int
    explanation: str
    law_reference: str = ""

class AssessmentResult(BaseModel):
    assessment_id: str
    score: int
    total: int
    percentage: float
    passed: bool
    pass_mark: int
    results: List[AnswerResult]

class GenerateCourseRequest(BaseModel):
    category: str

class GenerateLawCourseRequest(BaseModel):
    category: str
    law_name: str

class GenerateAssessmentRequest(BaseModel):
    course_id: str
    question_count: int = Field(10, ge=3, le=20)

class CourseCreate(BaseModel):
    title: str
    desc: str
    overview: str = ""
    key_topics: List[str] = []
    lessons: List[Dict] = []
    level: str = "Intermediate"
    hours: float = 4.0
    category: str = ""

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    desc: Optional[str] = None
    overview: Optional[str] = None
    level: Optional[str] = None
    hours: Optional[float] = None
    active: Optional[bool] = None

# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _course_to_dict(c: Dict, user_id: Optional[str] = None) -> Dict:
    result = {k: c.get(k) for k in CoursePublic.__fields__ if k in c}
    total = len(c.get("lessons", []))
    prog = _progress_cache.get(user_id or "", {}).get(c["id"], {}) if user_id else {}
    completed = prog.get("lessons_completed", 0)
    result["progress_percent"]  = round((completed / total) * 100) if total else 0
    result["lessons_completed"] = completed
    result["last_lesson"]       = prog.get("last_lesson", 0)
    result["completed"]         = prog.get("completed", False)
    return result

# ============================================================================
# ROUTES — ADMIN: CATEGORY INFO
# ============================================================================

@education_router.get("/admin/categories")
async def list_available_categories():
    """Returns which categories have JSON files and how many laws each contains."""
    result = []
    for cat, fname in JSON_FILES.items():
        laws = _get_laws_in_category(cat)
        result.append({
            "category":       cat,
            "file":           fname,
            "file_exists":    os.path.exists(fname),
            "law_count":      len(laws),
            "law_names":      [l["law_name"] for l in laws],
        })
    return result


@education_router.get("/admin/laws")
async def list_all_laws():
    """Returns all individual laws available across all JSON files."""
    result = []
    for cat in JSON_FILES.keys():
        laws = _get_laws_in_category(cat)
        for law in laws:
            course_id = _law_name_to_course_id(law["law_name"])
            result.append({
                "law_name":      law["law_name"],
                "category":      cat,
                "section_count": len(law["sections"]),
                "course_exists": course_id in _courses_cache,
                "course_id":     course_id if course_id in _courses_cache else None,
            })
    return result

# ============================================================================
# ROUTES — ADMIN: COURSE GENERATION
# ============================================================================

@education_router.post("/admin/generate-course", status_code=201)
async def generate_category_course(req: GenerateCourseRequest):
    """
    Generate one overview course per law category (original behaviour).
    """
    if req.category not in JSON_FILES:
        raise HTTPException(status_code=400, detail=f"Unknown category. Available: {list(JSON_FILES.keys())}")

    course_id = f"course-{re.sub(r'[^a-z0-9]', '-', req.category.lower())}"
    if course_id in _courses_cache:
        return {"message": "Course already exists.", "course_id": course_id, "course": _courses_cache[course_id]}

    logger.info(f"Generating category course: {req.category}")
    ai_data = _generate_course_from_rag(req.category)
    if not ai_data:
        raise HTTPException(status_code=500, detail="AI generation failed.")

    course = _build_course_record(req.category, ai_data)
    _courses_cache[course["id"]] = course
    _dump(COURSES_DB_FILE, _courses_cache)
    return {"message": "Course generated successfully", "course": course}


@education_router.post("/admin/generate-law-course", status_code=201)
async def generate_single_law_course(req: GenerateLawCourseRequest):
    """
    Generate a rich course for ONE specific law (e.g. 'The Divorce Act, 1869').
    """
    if req.category not in JSON_FILES:
        raise HTTPException(status_code=400, detail=f"Unknown category.")

    course_id = _law_name_to_course_id(req.law_name)
    if course_id in _courses_cache:
        return {"message": "Course already exists.", "course_id": course_id}

    laws = _get_laws_in_category(req.category)
    law = next((l for l in laws if l["law_name"] == req.law_name), None)
    if not law:
        raise HTTPException(status_code=404, detail=f"Law '{req.law_name}' not found in {req.category}")

    logger.info(f"Generating law course: {req.law_name}")
    ai_data = _generate_course_for_law(req.law_name, req.category, law["sections"])
    if not ai_data:
        raise HTTPException(status_code=500, detail=f"AI generation failed for '{req.law_name}'")

    course = _build_course_record(req.category, ai_data, law_name=req.law_name)
    _courses_cache[course_id] = course
    _dump(COURSES_DB_FILE, _courses_cache)
    logger.info(f"Law course created: {course['title']} ({len(course['lessons'])} lessons)")
    return {"message": "Course generated successfully", "course": course}


@education_router.post("/admin/generate-law-courses", status_code=201)
async def generate_all_law_courses(
    category: Optional[str] = Query(None, description="Limit to one category"),
    limit: int = Query(30, ge=1, le=120, description="Max courses to generate"),
    skip_existing: bool = Query(True),
):
    """
    Generate one rich course per individual law across all (or one) categories.
    This will generate 20-119 courses depending on what's in your JSON files.
    Call this once — it skips already-generated courses on subsequent calls.
    """
    results = []
    generated = 0

    cats = [category] if category and category in JSON_FILES else list(JSON_FILES.keys())

    for cat in cats:
        if generated >= limit:
            break
        laws = _get_laws_in_category(cat)
        logger.info(f"Processing {len(laws)} laws in {cat}...")

        for law in laws:
            if generated >= limit:
                break

            law_name = law["law_name"]
            course_id = _law_name_to_course_id(law_name)

            if skip_existing and course_id in _courses_cache:
                results.append({"law": law_name, "category": cat, "status": "skipped"})
                continue

            if len(law["sections"]) < 2:
                results.append({"law": law_name, "category": cat, "status": "skipped_too_small"})
                continue

            try:
                logger.info(f"Generating: {law_name}")
                ai_data = _generate_course_for_law(law_name, cat, law["sections"])
                if ai_data:
                    course = _build_course_record(cat, ai_data, law_name=law_name)
                    _courses_cache[course_id] = course
                    generated += 1
                    results.append({
                        "law":      law_name,
                        "category": cat,
                        "status":   "generated",
                        "title":    course["title"],
                        "lessons":  len(course["lessons"]),
                    })
                    logger.info(f"  ✓ {course['title']} — {len(course['lessons'])} lessons")
                else:
                    results.append({"law": law_name, "category": cat, "status": "ai_failed"})
            except Exception as e:
                logger.error(f"  ✗ {law_name}: {e}")
                results.append({"law": law_name, "category": cat, "status": "error", "detail": str(e)})

    _dump(COURSES_DB_FILE, _courses_cache)

    generated_count = sum(1 for r in results if r["status"] == "generated")
    return {
        "message":        f"Done! Generated {generated_count} new courses.",
        "total_courses":  len(_courses_cache),
        "results":        results,
    }


@education_router.post("/admin/generate-all-courses", status_code=201)
async def generate_all_category_courses():
    """Generate one overview course per law category (original 5-course behaviour)."""
    results = []
    for category in JSON_FILES.keys():
        course_id = f"course-{re.sub(r'[^a-z0-9]', '-', category.lower())}"
        if course_id in _courses_cache:
            results.append({"category": category, "status": "skipped"})
            continue
        try:
            ai_data = _generate_course_from_rag(category)
            if ai_data:
                course = _build_course_record(category, ai_data)
                _courses_cache[course["id"]] = course
                results.append({"category": category, "status": "generated", "title": course["title"], "lessons": len(course["lessons"])})
            else:
                results.append({"category": category, "status": "failed"})
        except Exception as e:
            results.append({"category": category, "status": "error", "detail": str(e)})

    _dump(COURSES_DB_FILE, _courses_cache)
    return {"results": results, "total_courses": len(_courses_cache)}


@education_router.post("/admin/generate-assessment", status_code=201)
async def generate_assessment(req: GenerateAssessmentRequest):
    """Generate MCQ assessment for a course."""
    course = _courses_cache.get(req.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found.")

    category = course.get("category", "")
    if category not in JSON_FILES:
        raise HTTPException(status_code=400, detail=f"No law JSON for category: {category}")

    logger.info(f"Generating {req.question_count} MCQs for: {category}")
    questions = _generate_mcqs(category, count=req.question_count)
    if not questions:
        raise HTTPException(status_code=500, detail="MCQ generation failed.")

    assess_id = f"assess-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().isoformat()
    assessment = {
        "id":           assess_id,
        "course_id":    req.course_id,
        "title":        f"{course['title']} — Knowledge Assessment",
        "description":  f"AI-generated from actual Pakistani {category} legislation.",
        "pass_mark":    70,
        "active":       True,
        "ai_generated": True,
        "created_at":   now,
        "updated_at":   now,
        "questions":    questions,
    }
    _assessments_cache[assess_id] = assessment
    _dump(ASSESSMENTS_DB_FILE, _assessments_cache)
    return {
        "message":       f"Assessment generated with {len(questions)} questions",
        "assessment_id": assess_id,
    }


@education_router.post("/admin/bootstrap")
async def bootstrap_portal():
    """
    ONE-SHOT FULL SETUP.
    Generates 20+ law-level courses + assessments for the first 5 categories.
    Call: POST /api/education/admin/bootstrap
    """
    summary: Dict[str, Any] = {
        "law_courses": [],
        "assessments": [],
        "library":     len(_library_cache),
    }

    # Step 1: Generate per-law courses (up to 30 to keep bootstrap fast)
    generated = 0
    for cat in JSON_FILES.keys():
        if generated >= 30:
            break
        laws = _get_laws_in_category(cat)
        for law in laws:
            if generated >= 30:
                break
            law_name = law["law_name"]
            course_id = _law_name_to_course_id(law_name)

            if course_id in _courses_cache:
                summary["law_courses"].append({"law": law_name, "status": "exists"})
                continue

            if len(law["sections"]) < 2:
                continue

            try:
                ai_data = _generate_course_for_law(law_name, cat, law["sections"])
                if ai_data:
                    course = _build_course_record(cat, ai_data, law_name=law_name)
                    _courses_cache[course_id] = course
                    generated += 1
                    summary["law_courses"].append({"law": law_name, "status": "generated", "lessons": len(course["lessons"])})
                else:
                    summary["law_courses"].append({"law": law_name, "status": "failed"})
            except Exception as e:
                summary["law_courses"].append({"law": law_name, "status": "error", "detail": str(e)})

    _dump(COURSES_DB_FILE, _courses_cache)

    # Step 2: Generate one assessment per category
    for category in list(JSON_FILES.keys())[:3]:
        # Find a course for this category
        cat_courses = [c for c in _courses_cache.values() if c.get("category") == category and c.get("active")]
        if not cat_courses:
            continue
        course = cat_courses[0]
        has_assessment = any(a["course_id"] == course["id"] for a in _assessments_cache.values())
        if not has_assessment:
            questions = _generate_mcqs(category, count=10)
            if questions:
                assess_id = f"assess-{uuid.uuid4().hex[:8]}"
                now = datetime.utcnow().isoformat()
                _assessments_cache[assess_id] = {
                    "id": assess_id, "course_id": course["id"],
                    "title": f"{course['title']} — Assessment",
                    "description": f"AI-generated from Pakistani {category} legislation.",
                    "pass_mark": 70, "active": True, "ai_generated": True,
                    "created_at": now, "updated_at": now, "questions": questions,
                }
                summary["assessments"].append({"category": category, "status": "generated"})

    _dump(ASSESSMENTS_DB_FILE, _assessments_cache)

    return {
        "message": "Bootstrap complete!",
        "summary": summary,
        "totals": {
            "courses":     len([c for c in _courses_cache.values() if c.get("active")]),
            "assessments": len(_assessments_cache),
            "library":     len(_library_cache),
        },
    }

# ============================================================================
# ROUTES — COURSES (public)
# ============================================================================

@education_router.get("/courses")
async def list_courses(
    user_id:  Optional[str] = Query(None),
    level:    Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search:   Optional[str] = Query(None),
):
    courses = [c for c in _courses_cache.values() if c.get("active", True)]
    if level:
        courses = [c for c in courses if c.get("level","").lower() == level.lower()]
    if category:
        courses = [c for c in courses if c.get("category","").lower() == category.lower()]
    if search:
        q = search.lower()
        courses = [
            c for c in courses
            if q in c.get("title","").lower()
            or q in c.get("desc","").lower()
            or q in c.get("law_name","").lower()
        ]
    # Sort: by category then title
    courses.sort(key=lambda c: (c.get("category", ""), c.get("title", "")))
    return [_course_to_dict(c, user_id) for c in courses]


@education_router.get("/courses/categories")
async def list_categories():
    """Returns categories that actually have generated courses."""
    cats = sorted({
        c.get("category", "")
        for c in _courses_cache.values()
        if c.get("active", True) and c.get("category")
    })
    return cats if cats else list(JSON_FILES.keys())


@education_router.get("/courses/{course_id}")
async def get_course(course_id: str, user_id: Optional[str] = Query(None)):
    course = _courses_cache.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_to_dict(course, user_id)


@education_router.post("/admin/courses", status_code=201)
async def create_course_manual(data: CourseCreate):
    new_id = f"course-{uuid.uuid4().hex[:8]}"
    now = datetime.utcnow().isoformat()
    course = {
        "id": new_id, **data.dict(),
        "law_name": "",
        "lesson_titles": [l.get("title","") for l in data.lessons],
        "learning_outcomes": [], "difficulty_notes": "",
        "active": True, "ai_generated": False,
        "created_at": now, "updated_at": now,
    }
    _courses_cache[new_id] = course
    _dump(COURSES_DB_FILE, _courses_cache)
    return course


@education_router.patch("/admin/courses/{course_id}")
async def update_course(course_id: str, data: CourseUpdate):
    course = _courses_cache.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    updates = {k: v for k, v in data.dict().items() if v is not None}
    updates["updated_at"] = datetime.utcnow().isoformat()
    course.update(updates)
    _dump(COURSES_DB_FILE, _courses_cache)
    return course


@education_router.delete("/admin/courses/{course_id}")
async def delete_course(course_id: str):
    course = _courses_cache.get(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    course["active"] = False
    course["updated_at"] = datetime.utcnow().isoformat()
    _dump(COURSES_DB_FILE, _courses_cache)
    return {"success": True, "message": f"'{course['title']}' deactivated."}

# ============================================================================
# ROUTES — USER PROGRESS
# ============================================================================

@education_router.post("/progress", response_model=ProgressResponse)
async def update_progress(data: ProgressUpdate):
    course = _courses_cache.get(data.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    total = len(course.get("lessons", []))
    if data.user_id not in _progress_cache:
        _progress_cache[data.user_id] = {}

    existing = _progress_cache[data.user_id].get(data.course_id, {
        "lessons_completed": 0, "completed_indices": [],
        "last_lesson": 0, "completed": False,
        "updated_at": datetime.utcnow().isoformat(),
    })

    indices: list = existing.get("completed_indices", [])
    if data.lesson_index not in indices:
        indices.append(data.lesson_index)

    count = len(indices)
    last = max(indices) if indices else 0
    done = count >= total
    pct = round((count / total) * 100) if total else 0

    record = {
        "lessons_completed": count, "completed_indices": indices,
        "last_lesson": last, "completed": done,
        "updated_at": datetime.utcnow().isoformat(),
    }
    _progress_cache[data.user_id][data.course_id] = record
    _dump(PROGRESS_DB_FILE, _progress_cache)

    return ProgressResponse(
        user_id=data.user_id, course_id=data.course_id,
        lessons_completed=count, total_lessons=total,
        progress_percent=pct, last_lesson=last,
        completed=done, updated_at=record["updated_at"],
    )


@education_router.get("/progress/{user_id}")
async def get_user_progress(user_id: str):
    user_prog = _progress_cache.get(user_id, {})
    result = {}
    for course_id, prog in user_prog.items():
        course = _courses_cache.get(course_id)
        if not course:
            continue
        total = len(course.get("lessons", []))
        count = prog.get("lessons_completed", 0)
        result[course_id] = {
            "course_title":      course.get("title", ""),
            "lessons_completed": count,
            "total_lessons":     total,
            "progress_percent":  round((count / total) * 100) if total else 0,
            "last_lesson":       prog.get("last_lesson", 0),
            "completed":         prog.get("completed", False),
            "updated_at":        prog.get("updated_at", ""),
        }
    return result

# ============================================================================
# ROUTES — LAW LIBRARY
# ============================================================================

@education_router.get("/library")
async def list_library(
    search:   Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tag:      Optional[str] = Query(None),
):
    entries = [e for e in _library_cache.values() if e.get("active", True)]
    if category:
        entries = [e for e in entries if e["category"].lower() == category.lower()]
    if tag:
        entries = [e for e in entries if tag.lower() in [t.lower() for t in e.get("tags", [])]]
    if search:
        q = search.lower()
        entries = [
            e for e in entries
            if q in e["title"].lower() or q in e["description"].lower()
            or any(q in t.lower() for t in e.get("tags", []))
        ]
    return sorted(entries, key=lambda x: x.get("year", 0), reverse=True)


@education_router.get("/library/categories")
async def library_categories():
    cats = {e["category"] for e in _library_cache.values() if e.get("active", True)}
    return sorted(cats)


@education_router.get("/library/stats")
async def library_stats():
    active = [e for e in _library_cache.values() if e.get("active", True)]
    by_cat = {}
    for e in active:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    return {
        "total_laws":      len(active),
        "by_category":     by_cat,
        "total_sections":  sum(e.get("section_count", 0) for e in active),
    }


@education_router.post("/admin/library/refresh")
async def refresh_library():
    _library_cache.clear()
    _library_cache.update(_populate_library_from_json())
    _dump(LIBRARY_DB_FILE, _library_cache)
    return {"success": True, "total": len(_library_cache)}

# ============================================================================
# ROUTES — ASSESSMENTS
# ============================================================================

@education_router.get("/assessments")
async def list_assessments(course_id: Optional[str] = Query(None)):
    items = [a for a in _assessments_cache.values() if a.get("active", True)]
    if course_id:
        items = [a for a in items if a["course_id"] == course_id]
    return [
        AssessmentPublic(
            id=a["id"], course_id=a["course_id"], title=a["title"],
            description=a["description"], pass_mark=a["pass_mark"],
            question_count=len(a.get("questions", [])),
            ai_generated=a.get("ai_generated", False),
        )
        for a in items
    ]


@education_router.get("/assessments/{assessment_id}", response_model=AssessmentWithQuestions)
async def get_assessment(assessment_id: str):
    a = _assessments_cache.get(assessment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    safe_qs = [QuestionPublic(id=q["id"], text=q["text"], options=q["options"]) for q in a.get("questions", [])]
    return AssessmentWithQuestions(
        id=a["id"], course_id=a["course_id"], title=a["title"],
        description=a["description"], pass_mark=a["pass_mark"],
        question_count=len(safe_qs), ai_generated=a.get("ai_generated", False),
        questions=safe_qs,
    )


@education_router.post("/assessments/{assessment_id}/submit", response_model=AssessmentResult)
async def submit_assessment(assessment_id: str, submission: AnswerSubmit):
    a = _assessments_cache.get(assessment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")

    questions = a.get("questions", [])
    results, correct_count = [], 0

    for q in questions:
        chosen = submission.answers.get(q["id"])
        if chosen is None:
            results.append(AnswerResult(
                question_id=q["id"], correct=False, chosen=-1,
                correct_answer=int(q["correct"]),
                explanation=q.get("explanation", ""),
                law_reference=q.get("law_reference", ""),
            ))
            continue
        is_correct = int(chosen) == int(q["correct"])
        if is_correct:
            correct_count += 1
        results.append(AnswerResult(
            question_id=q["id"], correct=is_correct, chosen=int(chosen),
            correct_answer=int(q["correct"]),
            explanation=q.get("explanation", ""),
            law_reference=q.get("law_reference", ""),
        ))

    total = len(questions)
    pct = round((correct_count / total) * 100, 1) if total else 0.0

    return AssessmentResult(
        assessment_id=assessment_id, score=correct_count,
        total=total, percentage=pct,
        passed=pct >= a["pass_mark"], pass_mark=a["pass_mark"],
        results=results,
    )


@education_router.delete("/admin/assessments/{assessment_id}")
async def delete_assessment(assessment_id: str):
    a = _assessments_cache.get(assessment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    a["active"] = False
    a["updated_at"] = datetime.utcnow().isoformat()
    _dump(ASSESSMENTS_DB_FILE, _assessments_cache)
    return {"success": True, "message": f"'{a['title']}' deactivated."}