# ============================================================================
# LAWYER CONNECT PORTAL — Backend Router
# File: lawyers_router.py
# Mount in App.py with: app.include_router(lawyers_router, prefix="/api/lawyers")
# ============================================================================

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import json
import os
import uuid
from datetime import datetime

lawyers_router = APIRouter(tags=["Lawyer Connect Portal"])

# ============================================================================
# FILE-BASED DB  (same pattern as users_db.json in App.py)
# ============================================================================

LAWYERS_DB_FILE = "lawyers_db.json"
REVIEWS_DB_FILE = "lawyer_reviews_db.json"

_lawyers_cache: Dict[str, Dict] = {}
_reviews_cache: Dict[str, List] = {}   # lawyer_id -> list of reviews


def _load_lawyers():
    global _lawyers_cache
    if os.path.exists(LAWYERS_DB_FILE):
        try:
            with open(LAWYERS_DB_FILE, "r", encoding="utf-8") as f:
                _lawyers_cache = json.load(f)
        except Exception:
            _lawyers_cache = {}
    else:
        # Seed with the 5 dummy lawyers that are already in the UI
        _lawyers_cache = {str(l["id"]): l for l in _SEED_LAWYERS}
        _save_lawyers()


def _save_lawyers():
    with open(LAWYERS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(_lawyers_cache, f, indent=2, ensure_ascii=False)


def _load_reviews():
    global _reviews_cache
    if os.path.exists(REVIEWS_DB_FILE):
        try:
            with open(REVIEWS_DB_FILE, "r", encoding="utf-8") as f:
                _reviews_cache = json.load(f)
        except Exception:
            _reviews_cache = {}
    else:
        _reviews_cache = {}
        _save_reviews()


def _save_reviews():
    with open(REVIEWS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(_reviews_cache, f, indent=2, ensure_ascii=False)


# ============================================================================
# SEED DATA  (mirrors the LAWYERS const in App.js exactly)
# ============================================================================

_SEED_LAWYERS = [
    {
        "id": "1",
        "name": "Advocate Ayesha Khan",
        "specialization": "Family Law & Women Rights",
        "experience_years": 12,
        "location": "Karachi",
        "availability": "2 hours",
        "languages": ["English", "Urdu"],
        "rating": 4.8,
        "review_count": 156,
        "hourly_rate": 5000,
        "currency": "PKR",
        "emoji": "👩‍⚖️",
        "bio": "Specializes in family disputes, khula cases, inheritance, and women's rights under Pakistani law.",
        "contact_email": "ayesha.khan@legalease.pk",
        "contact_phone": "+92-300-1234567",
        "bar_council": "Sindh Bar Council",
        "bar_number": "SBC-2012-4521",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "2",
        "name": "Advocate Muhammad Ali",
        "specialization": "Criminal Defense & Civil Rights",
        "experience_years": 15,
        "location": "Lahore",
        "availability": "1 hour",
        "languages": ["English", "Urdu", "Punjabi"],
        "rating": 4.9,
        "review_count": 203,
        "hourly_rate": 7000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Senior criminal defense advocate with expertise in FIR challenges, bail, and constitutional petitions.",
        "contact_email": "m.ali@legalease.pk",
        "contact_phone": "+92-300-9876543",
        "bar_council": "Punjab Bar Council",
        "bar_number": "PBC-2009-1103",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "3",
        "name": "Advocate Sarah Ahmed",
        "specialization": "Corporate Law & Business",
        "experience_years": 10,
        "location": "Islamabad",
        "availability": "3 hours",
        "languages": ["English", "Urdu"],
        "rating": 4.7,
        "review_count": 89,
        "hourly_rate": 6000,
        "currency": "PKR",
        "emoji": "🏛️",
        "bio": "Corporate law specialist for SMEs and startups — contracts, compliance, SECP filings, and M&A.",
        "contact_email": "sarah.ahmed@legalease.pk",
        "contact_phone": "+92-300-5556677",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-2014-0890",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "4",
        "name": "Advocate Bilal Hassan",
        "specialization": "Property & Real Estate Law",
        "experience_years": 8,
        "location": "Karachi",
        "availability": "Today",
        "languages": ["English", "Urdu", "Sindhi"],
        "rating": 4.6,
        "review_count": 64,
        "hourly_rate": 4500,
        "currency": "PKR",
        "emoji": "🏠",
        "bio": "Handles property disputes, title transfers, housing scheme fraud, and DHA/CDGK matters.",
        "contact_email": "bilal.hassan@legalease.pk",
        "contact_phone": "+92-300-7778899",
        "bar_council": "Sindh Bar Council",
        "bar_number": "SBC-2016-7742",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "5",
        "name": "Advocate Fatima Malik",
        "specialization": "Labor & Employment Law",
        "experience_years": 6,
        "location": "Faisalabad",
        "availability": "Tomorrow",
        "languages": ["English", "Urdu", "Punjabi"],
        "rating": 4.5,
        "review_count": 41,
        "hourly_rate": 3500,
        "currency": "PKR",
        "emoji": "👩‍💼",
        "bio": "Focuses on EOBI, labor tribunals, wrongful termination, and worker rights under NIRC.",
        "contact_email": "fatima.malik@legalease.pk",
        "contact_phone": "+92-300-3334455",
        "bar_council": "Punjab Bar Council",
        "bar_number": "PBC-2018-3312",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    # ── TOP 20 ISLAMABAD LAWYERS (SJP / Pakarbiter / Public Profiles) ────────
    {
        "id": "6",
        "name": "Advocate Jaseem Ahmed Bhutto",
        "specialization": "Civil Law, Criminal Law, Family Law & IP",
        "experience_years": 9,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.6,
        "review_count": 0,
        "hourly_rate": 5000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "High Court advocate practising civil, criminal, family law and intellectual property / trademarks from District Court F-8 Markaz, Islamabad.",
        "contact_email": "jaseem.bhutto@gmail.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0006",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "7",
        "name": "Advocate Sayed Asad Abbas Naqvi",
        "specialization": "Criminal Law, Family Law & Intellectual Property",
        "experience_years": 12,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.7,
        "review_count": 0,
        "hourly_rate": 6000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "High Court advocate with 12 years of experience in criminal defence, family matters, and IP law, based at AAA Plaza, G-11 Markaz, Islamabad.",
        "contact_email": "asadshah196@gmail.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0007",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "8",
        "name": "Advocate Muhammad Abdul Wali Irfan",
        "specialization": "Banking, Civil, Criminal, Property & Arbitration",
        "experience_years": 22,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.8,
        "review_count": 0,
        "hourly_rate": 8000,
        "currency": "PKR",
        "emoji": "🏛️",
        "bio": "Senior High Court advocate with 22 years handling banking & financial law, civil disputes, criminal cases, property matters, and arbitration from Abu Dhabi Towers, F-7, Islamabad.",
        "contact_email": "awirfan@hotmail.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0008",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "9",
        "name": "Advocate Usman Anwar Awan",
        "specialization": "Criminal Law, Family Law, Corporate & Cybercrime",
        "experience_years": 16,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.7,
        "review_count": 0,
        "hourly_rate": 7000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "High Court advocate specialising in criminal defence, family law, civil litigation, corporate law, and cybercrime cases at District Court F-8 Markaz, Islamabad.",
        "contact_email": "usman.anwar24@yahoo.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0009",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "10",
        "name": "Advocate Riaz Ahmad Khalil",
        "specialization": "Civil Law, Constitutional Law & Energy Law",
        "experience_years": 35,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.9,
        "review_count": 0,
        "hourly_rate": 10000,
        "currency": "PKR",
        "emoji": "🏛️",
        "bio": "Veteran High Court advocate with 35 years in civil, constitutional, energy/oil & gas law, and consumer protection. Office at Al-Mustafa Apartments, G-8 Markaz, Islamabad.",
        "contact_email": "ubairkhalil@gmail.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0010",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "11",
        "name": "Advocate Zeeshan Babar Awan",
        "specialization": "Banking Law, Labour Law & Civil Litigation",
        "experience_years": 10,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.6,
        "review_count": 0,
        "hourly_rate": 5500,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "High Court advocate covering banking law, labour law, civil and criminal matters, based at District Courts F-8 Markaz, Islamabad.",
        "contact_email": "lawyer.zeeshan@yahoo.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0011",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "12",
        "name": "Advocate Malik Mohsin Abbas",
        "specialization": "Civil Law, Company Law & Corporate Matters",
        "experience_years": 8,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.5,
        "review_count": 0,
        "hourly_rate": 5000,
        "currency": "PKR",
        "emoji": "🏛️",
        "bio": "High Court advocate focusing on civil law, company law, and corporate legal matters at Shalimar Plaza, F-8 Markaz, Islamabad.",
        "contact_email": "advmohsin512@gmail.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0012",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "13",
        "name": "Advocate Bilal Saleem Kayani",
        "specialization": "Land & Property Law, Administrative & Appellate Law",
        "experience_years": 12,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.7,
        "review_count": 0,
        "hourly_rate": 6000,
        "currency": "PKR",
        "emoji": "🏠",
        "bio": "High Court advocate at Bilal Law Associates, F-8 Markaz, Islamabad — specialising in land & property law, administrative law, appeals, and civil litigation.",
        "contact_email": "bksaleem2@gmail.com",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJP-0013",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "14",
        "name": "Advocate Mubeen Ali Husnain",
        "specialization": "Arbitration, Bail Matters & Contract Disputes",
        "experience_years": 11,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.6,
        "review_count": 0,
        "hourly_rate": 5500,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate handling arbitration, pre/post-arrest bail applications, and breach of contract cases. Office at PHA Flats, G-11/3, Islamabad.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-PKA-0014",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "15",
        "name": "Advocate Shah Fahad Wazir",
        "specialization": "Arbitration, Bankruptcy & Bail Matters",
        "experience_years": 6,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.4,
        "review_count": 0,
        "hourly_rate": 4500,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate covering arbitration, bankruptcy/insolvency law, and bail matters. Office at Al-Mustafa Apartments, G-8 Markaz, Islamabad.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-PKA-0015",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "16",
        "name": "Advocate Sadia Javed",
        "specialization": "Civil Law, Property, Family & Immigration Law",
        "experience_years": 8,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.6,
        "review_count": 0,
        "hourly_rate": 5000,
        "currency": "PKR",
        "emoji": "👩‍⚖️",
        "bio": "Islamabad High Court advocate handling civil law, property disputes, family law, corporate law, and immigration cases. Based at G-11 Markaz, Islamabad.",
        "contact_email": "Ask.SJLawExperts@gmail.com",
        "contact_phone": "+92-335-4112288",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0016",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "17",
        "name": "Advocate Shajar Abbas Hamdani",
        "specialization": "Civil, Criminal, Corporate, Banking & NAB/FIA Cases",
        "experience_years": 14,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.8,
        "review_count": 0,
        "hourly_rate": 8000,
        "currency": "PKR",
        "emoji": "🏛️",
        "bio": "Supreme Court & Islamabad High Court advocate with broad expertise in civil, criminal, corporate, commercial, NAB/FIA cases, and banking law. Office at G-11 Markaz, Islamabad.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0017",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "18",
        "name": "Advocate Shakeel Akhtar",
        "specialization": "Civil, Criminal, Family & Corporate Law",
        "experience_years": 10,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.5,
        "review_count": 0,
        "hourly_rate": 5000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate practising civil, criminal, family, corporate, and commercial law.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0018",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "19",
        "name": "Advocate Umar Farooq",
        "specialization": "Family Law, Civil, Criminal, Corporate & Taxation",
        "experience_years": 9,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.5,
        "review_count": 0,
        "hourly_rate": 5000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate handling family law, civil and criminal cases, corporate law, and taxation matters.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0019",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "20",
        "name": "Advocate Zaka Ullah Malik",
        "specialization": "Family Law, Immigration, Human Rights & Corporate Law",
        "experience_years": 11,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.6,
        "review_count": 0,
        "hourly_rate": 5500,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate covering family law, civil and criminal matters, immigration law, human rights, and corporate law.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0020",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "21",
        "name": "Advocate Asif Mehmood",
        "specialization": "Family Law, Civil, Criminal & Corporate Law",
        "experience_years": 9,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.4,
        "review_count": 0,
        "hourly_rate": 4500,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate practising family law, civil, criminal, and corporate law.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0021",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "22",
        "name": "Advocate Sajjid Abbas",
        "specialization": "Family Law, Civil & Criminal Law",
        "experience_years": 8,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.4,
        "review_count": 0,
        "hourly_rate": 4000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "Islamabad High Court advocate handling family law, civil, and criminal cases.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0022",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "23",
        "name": "Advocate Qurat-ul-Ain",
        "specialization": "Family Law, Civil, Corporate & Legal Research",
        "experience_years": 7,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.5,
        "review_count": 0,
        "hourly_rate": 4500,
        "currency": "PKR",
        "emoji": "👩‍⚖️",
        "bio": "Islamabad High Court advocate specialising in family law, civil law, corporate law, and legal research.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-SJF-0023",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "24",
        "name": "Advocate Ahmed Raza",
        "specialization": "Civil Litigation, Property Law & Criminal Defence",
        "experience_years": 7,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.4,
        "review_count": 0,
        "hourly_rate": 4000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "District Court Islamabad advocate handling civil litigation, property law, and criminal defence matters.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-PKA-0024",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
    {
        "id": "25",
        "name": "Advocate Usman Tariq",
        "specialization": "Family Law, Civil Law & Contract Disputes",
        "experience_years": 6,
        "location": "Islamabad",
        "availability": "Available",
        "languages": ["English", "Urdu"],
        "rating": 4.3,
        "review_count": 0,
        "hourly_rate": 4000,
        "currency": "PKR",
        "emoji": "⚖️",
        "bio": "District Court Islamabad advocate covering family law, civil law, and contract disputes.",
        "contact_email": "",
        "contact_phone": "",
        "bar_council": "Islamabad Bar Council",
        "bar_number": "IBC-PKA-0025",
        "verified": True,
        "active": True,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    },
]

# Initialize on import
_load_lawyers()
_load_reviews()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class LawyerPublic(BaseModel):
    """Shape returned to the frontend — matches App.js LAWYERS array + extra fields"""
    id: str
    name: str
    specialization: str
    experience_years: int
    location: str
    availability: str
    languages: List[str]
    rating: float
    review_count: int
    hourly_rate: int
    currency: str
    emoji: str
    bio: str
    contact_email: str
    contact_phone: str
    bar_council: str
    bar_number: str
    verified: bool
    active: bool
    # Extended fields — optional so old seed records without them still work
    free_consultation: Optional[str] = ""
    website: Optional[str] = ""
    founded: Optional[int] = 0
    team_size: Optional[int] = 0


class LawyerCreate(BaseModel):
    """Admin: create a new lawyer profile"""
    name: str = Field(..., min_length=3)
    specialization: str = Field(..., min_length=3)
    experience_years: int = Field(..., ge=0, le=60)
    location: str
    availability: str = "Available"
    languages: List[str] = ["English", "Urdu"]
    hourly_rate: int = Field(..., ge=500)
    currency: str = "PKR"
    emoji: str = "⚖️"
    bio: str = ""
    contact_email: str
    contact_phone: str
    bar_council: str
    bar_number: str

    @validator("contact_email")
    def validate_email(cls, v):
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.lower().strip()


class LawyerUpdate(BaseModel):
    """Admin: partial update"""
    name: Optional[str] = None
    specialization: Optional[str] = None
    experience_years: Optional[int] = None
    location: Optional[str] = None
    availability: Optional[str] = None
    languages: Optional[List[str]] = None
    hourly_rate: Optional[int] = None
    currency: Optional[str] = None
    emoji: Optional[str] = None
    bio: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    bar_council: Optional[str] = None
    bar_number: Optional[str] = None
    active: Optional[bool] = None


class ReviewCreate(BaseModel):
    user_name: str = Field(..., min_length=2)
    rating: float = Field(..., ge=1.0, le=5.0)
    comment: str = Field(..., min_length=10, max_length=1000)


class ReviewPublic(BaseModel):
    id: str
    lawyer_id: str
    user_name: str
    rating: float
    comment: str
    created_at: str


class LawyerListResponse(BaseModel):
    lawyers: List[LawyerPublic]
    total: int
    page: int
    page_size: int


# ============================================================================
# HELPERS
# ============================================================================

def _recalculate_rating(lawyer_id: str):
    """Recompute average rating from the reviews DB after a new review is added."""
    reviews = _reviews_cache.get(lawyer_id, [])
    if not reviews:
        return
    avg = round(sum(r["rating"] for r in reviews) / len(reviews), 1)
    _lawyers_cache[lawyer_id]["rating"] = avg
    _lawyers_cache[lawyer_id]["review_count"] = len(reviews)
    _lawyers_cache[lawyer_id]["updated_at"] = datetime.utcnow().isoformat()
    _save_lawyers()


def _to_public(raw: Dict) -> LawyerPublic:
    return LawyerPublic(**{k: raw[k] for k in LawyerPublic.__fields__ if k in raw})


def _apply_filters(
    lawyers: List[Dict],
    search: Optional[str],
    specialization: Optional[str],
    location: Optional[str],
    min_rating: Optional[float],
    max_rate: Optional[int],
    language: Optional[str],
    verified_only: bool,
) -> List[Dict]:
    result = []
    for l in lawyers:
        if not l.get("active", True):
            continue
        if verified_only and not l.get("verified", False):
            continue
        if min_rating and l["rating"] < min_rating:
            continue
        if max_rate and l["hourly_rate"] > max_rate:
            continue
        if location and l["location"].lower() != location.lower():
            continue
        if specialization and specialization.lower() not in l["specialization"].lower():
            continue
        if language:
            langs_lower = [lang.lower() for lang in l.get("languages", [])]
            if language.lower() not in langs_lower:
                continue
        if search:
            q = search.lower()
            searchable = f"{l['name']} {l['specialization']} {l['location']} {l['bio']}".lower()
            if q not in searchable:
                continue
        result.append(l)
    return result


# ============================================================================
# ROUTES
# ============================================================================

# ── GET /api/lawyers  — list + search + filter ───────────────────────────────
@lawyers_router.get("/", response_model=LawyerListResponse)
async def list_lawyers(
    search: Optional[str] = Query(None, description="Search name, specialization, bio, or location"),
    specialization: Optional[str] = Query(None, description="Filter by specialization keyword"),
    location: Optional[str] = Query(None, description="Filter by city"),
    min_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Minimum rating"),
    max_rate: Optional[int] = Query(None, ge=0, description="Maximum hourly rate (PKR)"),
    language: Optional[str] = Query(None, description="Filter by language"),
    verified_only: bool = Query(False, description="Only return verified lawyers"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    all_lawyers = list(_lawyers_cache.values())
    filtered = _apply_filters(
        all_lawyers, search, specialization, location,
        min_rating, max_rate, language, verified_only
    )

    # Sort: verified first, then by rating desc
    filtered.sort(key=lambda x: (not x.get("verified", False), -x["rating"]))

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = filtered[start:end]

    return LawyerListResponse(
        lawyers=[_to_public(l) for l in page_data],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /api/lawyers/{lawyer_id}  — full profile ─────────────────────────────
@lawyers_router.get("/{lawyer_id}", response_model=LawyerPublic)
async def get_lawyer(lawyer_id: str = Path(...)):
    lawyer = _lawyers_cache.get(lawyer_id)
    if not lawyer:
        raise HTTPException(status_code=404, detail=f"Lawyer '{lawyer_id}' not found")
    return _to_public(lawyer)


# ── GET /api/lawyers/{lawyer_id}/reviews  — reviews for a lawyer ─────────────
@lawyers_router.get("/{lawyer_id}/reviews", response_model=List[ReviewPublic])
async def get_lawyer_reviews(lawyer_id: str = Path(...)):
    if lawyer_id not in _lawyers_cache:
        raise HTTPException(status_code=404, detail="Lawyer not found")
    reviews = _reviews_cache.get(lawyer_id, [])
    # Newest first
    return sorted(reviews, key=lambda r: r["created_at"], reverse=True)


# ── POST /api/lawyers/{lawyer_id}/reviews  — submit a review ─────────────────
@lawyers_router.post("/{lawyer_id}/reviews", response_model=ReviewPublic, status_code=201)
async def submit_review(lawyer_id: str, review: ReviewCreate):
    if lawyer_id not in _lawyers_cache:
        raise HTTPException(status_code=404, detail="Lawyer not found")

    new_review = {
        "id": str(uuid.uuid4()),
        "lawyer_id": lawyer_id,
        "user_name": review.user_name.strip(),
        "rating": round(review.rating, 1),
        "comment": review.comment.strip(),
        "created_at": datetime.utcnow().isoformat(),
    }

    if lawyer_id not in _reviews_cache:
        _reviews_cache[lawyer_id] = []
    _reviews_cache[lawyer_id].append(new_review)
    _save_reviews()

    # Recompute lawyer's aggregate rating
    _recalculate_rating(lawyer_id)

    return ReviewPublic(**new_review)


# ── POST /api/lawyers/admin/create  — admin: add a new lawyer ────────────────
@lawyers_router.post("/admin/create", response_model=LawyerPublic, status_code=201)
async def create_lawyer(data: LawyerCreate):
    new_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    lawyer = {
        "id": new_id,
        **data.dict(),
        "rating": 0.0,
        "review_count": 0,
        "verified": False,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    _lawyers_cache[new_id] = lawyer
    _save_lawyers()
    return _to_public(lawyer)


# ── PATCH /api/lawyers/admin/{lawyer_id}  — admin: update a lawyer ───────────
@lawyers_router.patch("/admin/{lawyer_id}", response_model=LawyerPublic)
async def update_lawyer(lawyer_id: str, data: LawyerUpdate):
    lawyer = _lawyers_cache.get(lawyer_id)
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer not found")

    updates = {k: v for k, v in data.dict().items() if v is not None}
    updates["updated_at"] = datetime.utcnow().isoformat()
    lawyer.update(updates)
    _lawyers_cache[lawyer_id] = lawyer
    _save_lawyers()
    return _to_public(lawyer)


# ── DELETE /api/lawyers/admin/{lawyer_id}  — admin: soft-delete ──────────────
@lawyers_router.delete("/admin/{lawyer_id}", status_code=200)
async def deactivate_lawyer(lawyer_id: str):
    lawyer = _lawyers_cache.get(lawyer_id)
    if not lawyer:
        raise HTTPException(status_code=404, detail="Lawyer not found")
    lawyer["active"] = False
    lawyer["updated_at"] = datetime.utcnow().isoformat()
    _save_lawyers()
    return {"success": True, "message": f"Lawyer '{lawyer['name']}' deactivated."}


# ── GET /api/lawyers/meta/specializations  — dropdown helper for frontend ─────
@lawyers_router.get("/meta/specializations", response_model=List[str])
async def get_specializations():
    specs = set()
    for l in _lawyers_cache.values():
        if l.get("active", True):
            specs.add(l["specialization"])
    return sorted(specs)


# ── GET /api/lawyers/meta/cities  — dropdown helper for frontend ─────────────
@lawyers_router.get("/meta/cities", response_model=List[str])
async def get_cities():
    cities = set()
    for l in _lawyers_cache.values():
        if l.get("active", True):
            cities.add(l["location"])
    return sorted(cities)