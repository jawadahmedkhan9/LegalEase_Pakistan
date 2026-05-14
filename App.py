from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator, EmailStr
from lawyers_router import lawyers_router
from education_router import education_router
import chromadb
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq
import PyPDF2
import docx
import io
from typing import List, Optional, Dict, Any
import uvicorn
import re
from collections import Counter
import logging
from PIL import Image
import pytesseract
import base64
import sys
import io
import locale
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import hashlib
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
import numpy as np
import secrets
import uuid
from education_router import education_router


# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Dedicated UTF-8 stream for logging to avoid Windows cp1252 errors
utf8_stream = sys.stdout
try:
    utf8_stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('legalease_search.log', encoding='utf-8', errors='replace'),
        logging.StreamHandler(utf8_stream)
    ]
)

logger = logging.getLogger('LegalEase')
logger.setLevel(logging.INFO)

# Suppress watchfiles logging
logging.getLogger('watchfiles.main').setLevel(logging.WARNING)
logging.getLogger('watchfiles').setLevel(logging.WARNING)

# Load environment variables
load_dotenv()


# ============================================================================
# CATEGORY TO URL MAPPING FOR PAKISTANCODE.GOV.PK
# Two-tier system:
#   1. LAW_SPECIFIC_URL_MAP  — exact law-name → direct URL (highest priority)
#   2. CATEGORY_URL_MAPPING  — category fallback URL (used when no specific match)
# ============================================================================

LAW_SPECIFIC_URL_MAP = {
    # ── Banking / Financial Laws ─────────────────────────────────────────────
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

    # ── Islamic / Religious Laws ─────────────────────────────────────────────
    "ehtram-e-ramazan ordinance, 1981": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZ2V-sg-jjjjjjjjjjjjj",
    "enforcement of shari'ah act, 1991": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apmXZA%3D%3D-sg-jjjjjjjjjjjjj",
    "pakistan madarasah education (establishment and affiliation of model dini madaris) board ordinance, 2001": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cp%2BUY2Jr-sg-jjjjjjjjjjjjj",
    "publication of holy quran (elimination of printing errors) act, 1973": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUZWJo-sg-jjjjjjjjjjjjj",
    "sikh gurdwaras (supplementary) act, 1925": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap6X-sg-jjjjjjjjjjjjj",

    # ── Land / Property Laws ─────────────────────────────────────────────────
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

    # ── Police Laws ──────────────────────────────────────────────────────────
    "airports security force act, 1975": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Fr-sg-jjjjjjjjjjjjj",
    "pakistan railways police act, 1977": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2hv-sg-jjjjjjjjjjjjj",
    "police (incitement to disaffection) act, 1922": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apyX-sg-jjjjjjjjjjjjj",
    "police act, 1888": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5s%3D-sg-jjjjjjjjjjjjj",

    # ── Family Laws ──────────────────────────────────────────────────────────
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
    "married women's property act, 1874": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJg%3D-sg-jjjjjjjjjjjjj",
    "parsi marriage and divorce act, 1936": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b56a-sg-jjjjjjjjjjjjj",
    "special marriage act, 1872": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5s%3D-sg-jjjjjjjjjjjjj",
    "muslim family laws ordinance, 1961": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aZZA%3D%3D-sg-jjjjjjjjjjjjj",
    "the muslim family laws ordinance, 1961": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aZZA%3D%3D-sg-jjjjjjjjjjjjj",

    # ── Criminal Laws ────────────────────────────────────────────────────────
    "anti narcotics force act (anf 1997)": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apqXZA%3D%3D-sg-jjjjjjjjjjjjj",
    "arms act, 1878": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZc%3D-sg-jjjjjjjjjjjjj",
    "chemical weapons convention implementation ordinance, 2000": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FobZg%3D-sg-jjjjjjjjjjjjj",
    "drugs act, 1976": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Rq-sg-jjjjjjjjjjjjj",
    "electricity act, 1910": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apeZ-sg-jjjjjjjjjjjjj",
    "electricity control ordinance, 1965": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cZaV-sg-jjjjjjjjjjjjj",
    "explosives act, 1884": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bp0%3D-sg-jjjjjjjjjjjjj",
    "high treason (punishment) act, 1973": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Zp-sg-jjjjjjjjjjjjj",
    "indecent advertisements prohibition act, 1963": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJqU-sg-jjjjjjjjjjjjj",
    "motion pictures ordinance, 1979": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cpaa-sg-jjjjjjjjjjjjj",
    "offence of zina (enforcement of hudood) ordinance, 1979": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cZ2U-sg-jjjjjjjjjjjjj",
    "offences against property (enforcement of hudood) ordinance, 1979": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cZyd-sg-jjjjjjjjjjjjj",
    "pakistan (exchange of prisoners) ordinance, 1948": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aVZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "prevention of anti-national activities act, 1974": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2lw-sg-jjjjjjjjjjjjj",
    "prevention of smuggling act, 1977": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2lv-sg-jjjjjjjjjjjjj",
    "prisoners act, 1900": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cpw%3D-sg-jjjjjjjjjjjjj",
    "probation of offenders ordinance, 1960": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5acZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "reformatory schools act, 1897": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cZw%3D-sg-jjjjjjjjjjjjj",
    "security of pakistan act, 1952": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BYZw%3D%3D-sg-jjjjjjjjjjjjj",
    "traffic offences (special courts) ordinance, 1981": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZ6b-sg-jjjjjjjjjjjjj",

    # ── Civil Laws ───────────────────────────────────────────────────────────
    "abandoned properties (management) act, 1975": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Fp-sg-jjjjjjjjjjjjj",
    "births, deaths, marriages registration act, 1886": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5c%3D-sg-jjjjjjjjjjjjj",
    "canal and drainage act, 1873": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJY%3D-sg-jjjjjjjjjjjjj",
    "capital of the republic (determination of area) ordinance, 1963": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ%2BX-sg-jjjjjjjjjjjjj",
    "carriage of goods by sea act, 1925": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap6Y-sg-jjjjjjjjjjjjj",
    "carriers act, 1865": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap0%3D-sg-jjjjjjjjjjjjj",
    "charitable funds (regulation of collections) act, 1953": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BaZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "civil aviation ordinance, 1960": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5abaA%3D%3D-sg-jjjjjjjjjjjjj",
    "contract act, 1872": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a50%3D-sg-jjjjjjjjjjjjj",
    "court-fees act, 1870": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FqZps%3D-sg-jjjjjjjjjjjjj",
    "fatal accidents act, 1855": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cg%3D%3D-sg-jjjjjjjjjjjjj",
    "foreign exchange (temporary restrictions) act, 1998": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apqbaA%3D%3D-sg-jjjjjjjjjjjjj",
    "foreigners act, 1946": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJiW-sg-jjjjjjjjjjjjj",
    "interest act 1839": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ag%3D%3D-sg-jjjjjjjjjjjjj",
    "majority act, 1875": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJo%3D-sg-jjjjjjjjjjjjj",
    "marriages validation act, 1892": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJs%3D-sg-jjjjjjjjjjjjj",
    "national highway authority (nha) act, 1991": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apmXZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "national highway safety ordinance, 2000": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FobJ0%3D-sg-jjjjjjjjjjjjj",
    "naturalization act, 1926": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cp%2BUY2Fw-sg-jjjjjjjjjjjjj",
    "pakistan citizenship act, 1951": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BXZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "pakistan currency act, 1950": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BVaw%3D%3D-sg-jjjjjjjjjjjjj",
    "pakistan environmental protection act, 1997": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apqaZQ%3D%3D-sg-jjjjjjjjjjjjj",
    "partition act, 1893": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ8%3D-sg-jjjjjjjjjjjjj",
    "partnership act, 1932": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5ab-sg-jjjjjjjjjjjjj",
    "passports act, 1974": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2lp-sg-jjjjjjjjjjjjj",
    "patents ordinance, 2000": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apaUY2FobZo%3D-sg-jjjjjjjjjjjjj",
    "ports act, 1908": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apad-sg-jjjjjjjjjjjjj",
    "punjab laws act, 1872": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5w%3D-sg-jjjjjjjjjjjjj",
    "religious societies act, 1880": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZw%3D-sg-jjjjjjjjjjjjj",
    "sale of goods act, 1930": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-a5aU-sg-jjjjjjjjjjjjj",
    "securities act, 1920": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apuW-sg-jjjjjjjjjjjjj",
    "succession act, 1925": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap6Z-sg-jjjjjjjjjjjjj",
    "trade marks ordinance, 2001": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cp%2BUY2Fx-sg-jjjjjjjjjjjjj",
    "transfer of property act, 1882": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpk%3D-sg-jjjjjjjjjjjjj",
}

# Category-level fallback URLs (used when no specific law-name match is found)
CATEGORY_URL_MAPPING = {
    "criminal_laws":         {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-apqXZA%3D%3D-sg-jjjjjjjjjjjjj", "display_name": "Criminal Laws"},
    "civil_laws":            {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bpuUY2Fp-sg-jjjjjjjjjjjjj",    "display_name": "Civil Laws"},
    "family_laws":           {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJaW-sg-jjjjjjjjjjjjj",         "display_name": "Family Laws"},
    "banking_laws":          {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-cJ%2BV-sg-jjjjjjjjjjjjj",      "display_name": "Banking Laws"},
    "land_property_law":     {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bJw%3D-sg-jjjjjjjjjjjjj",      "display_name": "Land & Property Laws"},
    "police_laws":           {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-b5s%3D-sg-jjjjjjjjjjjjj",      "display_name": "Police Laws"},
    "religious_laws":        {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-bZ2V-sg-jjjjjjjjjjjjj",        "display_name": "Religious Laws"},
    "pakistan_constitution": {"url": "https://pakistancode.gov.pk/english/UY2FqaJw1-apaUY2Fqa-ap%2BbZw%3D%3D-sg-jjjjjjjjjjjjj", "display_name": "Constitution of Pakistan"},
    "pakistani_laws":        {"url": "https://pakistancode.gov.pk",                                                              "display_name": "Pakistani Laws"},
    "service_laws":          {"url": "https://pakistancode.gov.pk",                                                              "display_name": "Service Laws"},
    "labour_laws":           {"url": "https://pakistancode.gov.pk",                                                              "display_name": "Labour Laws"},
    "companies_laws":        {"url": "https://pakistancode.gov.pk",                                                              "display_name": "Companies Laws"},
}

def get_law_url(law_name: str, category_key: str) -> str:
    """
    Returns the most specific URL for a given law name.
    Priority: exact law-name match → strip 'The ' prefix → category fallback.
    """
    key = law_name.strip().lower()
    if key in LAW_SPECIFIC_URL_MAP:
        return LAW_SPECIFIC_URL_MAP[key]
    # Try without leading "the "
    stripped = re.sub(r"^the\s+", "", key)
    if stripped in LAW_SPECIFIC_URL_MAP:
        return LAW_SPECIFIC_URL_MAP[stripped]
    # Fall back to category URL
    cat = CATEGORY_URL_MAPPING.get(category_key, CATEGORY_URL_MAPPING["pakistani_laws"])
    return cat["url"]

def get_category_from_collection_name(collection_name: str) -> str:
    """Convert collection name to category key"""
    collection_to_category = {
        "criminal_laws": "criminal_laws",
        "civil_laws": "civil_laws",
        "family_laws": "family_laws",
        "banking_laws": "banking_laws",
        "land_property_law": "land_property_law",
        "land_property_laws": "land_property_law",
        "police_laws": "police_laws",
        "religious_laws": "religious_laws",
        "pakistan_constitution": "pakistan_constitution",
        "pakistani_laws": "pakistani_laws",
        "service_laws": "service_laws",
        "labour_laws": "labour_laws",
        "companies_laws": "companies_laws"
    }
    return collection_to_category.get(collection_name.lower(), "pakistani_laws")

def generate_source_url(metadata: Dict[str, Any], collection_name: str) -> Dict[str, Any]:
    """
    Generate a clickable URL for a legal source.
    Tries law-specific URL first, then falls back to category URL.
    """
    category_key = get_category_from_collection_name(collection_name)
    category_info = CATEGORY_URL_MAPPING.get(category_key, CATEGORY_URL_MAPPING["pakistani_laws"])

    source = metadata.get("source", "Unknown Law")
    section_number = metadata.get("section_number", "")
    year = metadata.get("year", "")
    title = metadata.get("title", "")

    # Resolve the most specific URL available for this exact law
    resolved_url = get_law_url(source, category_key)

    citation_parts = []
    if source:
        citation_parts.append(source)
    if section_number:
        citation_parts.append(f"Section {section_number}")
    if year:
        citation_parts.append(f"({year})")

    citation_text = ", ".join(citation_parts) if citation_parts else "Legal Reference"

    return {
        "url": resolved_url,
        "category": category_info["display_name"],
        "law_name": source,
        "section": f"Section {section_number}" if section_number else "",
        "year": str(year) if year else "",
        "title": title,
        "citation": citation_text
    }


app = FastAPI(title="LegalEase Pakistan API - Fixed Image/Document Pipeline", version="3.0.0")
app.include_router(lawyers_router,  prefix="/api/lawyers")
app.include_router(education_router, prefix="/api/education")
#app.include_router(education_router, prefix="/api/education")

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security
security = HTTPBearer()

# User database file
USERS_DB_FILE = "users_db.json"
SESSIONS_DB_FILE = "sessions_db.json"

# In-memory session storage (can be moved to Redis in production)
sessions: Dict[str, Dict] = {}
users: Dict[str, Dict] = {}

# Load users from file
def load_users():
    global users
    if os.path.exists(USERS_DB_FILE):
        try:
            with open(USERS_DB_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except:
            users = {}
    else:
        users = {}

# Save users to file
def save_users():
    with open(USERS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

# Load sessions from file
def load_sessions():
    global sessions
    if os.path.exists(SESSIONS_DB_FILE):
        try:
            with open(SESSIONS_DB_FILE, 'r', encoding='utf-8') as f:
                sessions = json.load(f)
        except:
            sessions = {}
    else:
        sessions = {}

# Save sessions to file
def save_sessions():
    with open(SESSIONS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(sessions, f, indent=2)

# Initialize on startup
load_users()
load_sessions()

# Password hashing
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


# Initialize Cross-Encoder for reranking (Legal-BERT optimized)
logger.info("Loading Cross-Encoder model for reranking...")
try:
    cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    logger.info("Cross-Encoder loaded successfully")
except Exception as e:
    logger.error(f"Cross-Encoder loading failed: {e}")
    cross_encoder = None

# ============================================================================
# EMBEDDING FUNCTION
# ============================================================================

def get_embedding_function():
    """Get the SAME embedding function used during data loading"""
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        logger.info("Using SentenceTransformer embedding function (all-MiniLM-L6-v2)")
        return SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2",
            device="cpu"
        )
    except ImportError:
        logger.warning("SentenceTransformer not available, using default")
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        return DefaultEmbeddingFunction()

# Constants
MAX_MESSAGE_LENGTH = 5000
MAX_DOCUMENT_CONTEXT_LENGTH = 50000  # Truncate large documents
MAX_DOCUMENT_CHARS_FOR_LLM = 10000  # Max chars to send to LLM

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., max_length=MAX_MESSAGE_LENGTH, description="Message content")

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH, description="User's message")
    conversation_history: List[ChatMessage] = Field(default=[], description="Previous conversation messages")
    document_context: Optional[str] = Field(None, max_length=MAX_DOCUMENT_CONTEXT_LENGTH, description="Extracted document text")
    document_name: Optional[str] = Field(None, description="Document filename")
    
    @validator('message')
    def validate_message(cls, v):
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters.")
        return v.strip()

class ChatResponse(BaseModel):
    response: str
    sources: List[Dict[str, Any]] = []
    collections_used: List[str] = []
    status: str = "success"

# ── Enhanced contract analysis models ────────────────────────────────────────

class RiskItem(BaseModel):
    severity: str                        # "critical" | "high" | "medium" | "low"
    category: str                        # e.g. "Payment Terms", "Jurisdiction"
    title: str                           # Short headline
    description: str                     # Full explanation of the problem
    original_clause: Optional[str]       # Exact / paraphrased problematic text
    suggested_fix: Optional[str]         # Rewritten/improved clause text
    law_reference: Optional[str]         # e.g. "Contract Act 1872, Section 73"

class MissingClause(BaseModel):
    title: str
    why_needed: str
    suggested_text: str                  # Draft clause the user can insert
    law_reference: Optional[str]

class ApplicableLaw(BaseModel):
    name: str
    year: Optional[str]
    relevance: str                       # How it applies to this contract
    key_sections: List[str]              # Specific sections that apply

class ContractAnalysis(BaseModel):
    document_type: str                   # "Employment Contract", "Property Sale", etc.
    parties: List[str]                   # Detected parties in the contract
    summary: str                         # 3-4 sentence overview
    compliance_score: int                # 0-100, overall legal health
    overall_risk: str                    # "critical" | "high" | "medium" | "low"
    risks: List[RiskItem]
    missing_clauses: List[MissingClause]
    applicable_laws: List[ApplicableLaw]
    recommendations: List[str]           # Top 5 action items (most urgent first)
    timeline: str
    estimated_cost: str
    key_dates: List[str]                 # Important dates found in the document
    jurisdiction: str                    # Detected or assumed jurisdiction

# ── Authentication models ─────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=6, description="User password (min 6 characters)")
    name: str = Field(..., min_length=2, description="User full name")

class LoginRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")

class AuthResponse(BaseModel):
    success: bool
    message: str
    session_token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None

class SessionResponse(BaseModel):
    authenticated: bool
    user: Optional[Dict[str, Any]] = None

# ============================================================================
# CHROMADB CONNECTION
# ============================================================================

def get_chroma_client():
    """Get ChromaDB client with persistent storage"""
    try:
        client_db = chromadb.PersistentClient(path="./chroma_db")
        logger.info("ChromaDB connected successfully")
        return client_db
    except Exception as e:
        logger.error(f"ChromaDB connection error: {e}")
        return None

# ============================================================================
# DOCUMENT TYPE DETECTION
# ============================================================================

def detect_document_type(document_name: str) -> str:
    """Detect if document is an image or text document"""
    if not document_name:
        return "text"
    
    ext = document_name.lower().split('.')[-1]
    image_extensions = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp']
    
    if ext in image_extensions:
        return "image"
    return "text"

# ============================================================================
# QUERY INTENT CLASSIFIER
# ============================================================================

def classify_query_intent(query: str, has_document: bool, document_type: str) -> dict:
    """
    Classify user intent to determine if RAG search is needed.
    Returns: {
        "intent": "document_analysis" | "legal_query" | "mixed",
        "needs_rag": bool,
        "confidence": float
    }
    """
    query_lower = query.lower()
    
    document_keywords = [
        'summarize', 'summary', 'explain', 'what does', 'what is in',
        'analyze', 'analysis', 'read', 'tell me about', 'describe',
        'extract', 'find in', 'look for', 'this image', 'this document',
        'uploaded', 'attached', 'picture', 'photo'
    ]
    
    legal_keywords = [
        'law', 'legal', 'section', 'act', 'regulation', 'statute',
        'rights', 'can i', 'should i', 'what if', 'procedure',
        'court', 'police', 'property', 'contract', 'penalty'
    ]
    
    doc_score = sum(1 for kw in document_keywords if kw in query_lower)
    legal_score = sum(1 for kw in legal_keywords if kw in query_lower)
    
    if has_document:
        if doc_score > legal_score:
            return {
                "intent": "document_analysis",
                "needs_rag": False,
                "confidence": 0.8,
                "reason": "User asking about attached document"
            }
        elif legal_score > doc_score * 2:
            return {
                "intent": "legal_query",
                "needs_rag": True,
                "confidence": 0.7,
                "reason": "Legal question with document as context"
            }
        else:
            return {
                "intent": "mixed",
                "needs_rag": True,
                "confidence": 0.6,
                "reason": "Both document analysis and legal query"
            }
    else:
        return {
            "intent": "legal_query",
            "needs_rag": True,
            "confidence": 0.9,
            "reason": "No document attached, pure legal query"
        }

# ============================================================================
# LAW FILTERING
# ============================================================================

UNIVERSALLY_RELEVANT_LAWS = [
    "transfer of property act",
    "specific relief act",
    "contract act",
    "sale of goods act",
    "negotiable instruments act",
    "indian evidence act",
    "limitation act",
    "registration act"
]

def is_universally_relevant_law(law_name: str) -> bool:
    """Check if law is old but still foundational/relevant"""
    law_lower = law_name.lower()
    return any(relevant in law_lower for relevant in UNIVERSALLY_RELEVANT_LAWS)

def is_completely_obsolete_law(law_name: str) -> bool:
    """Check if law is definitely obsolete and should be filtered"""
    obsolete_patterns = [
        "dekkhan agriculturists",
        "waste lands",
        "land acquisition.*mines",
        "agriculturists.*loans",
        "cantonment land"
    ]
    
    law_lower = law_name.lower()
    for pattern in obsolete_patterns:
        if re.search(pattern, law_lower):
            return True
    return False

def should_filter_law(law_name: str, cutoff_year: int = 1920) -> bool:
    """Determine if a law should be filtered"""
    if is_universally_relevant_law(law_name):
        logger.info(f"      KEEPING RELEVANT OLD LAW: {law_name}")
        return False
    
    if is_completely_obsolete_law(law_name):
        return True
    
    try:
        year_match = re.search(r'\b(18\d{2}|19\d{2}|20\d{2})\b', law_name)
        if year_match:
            year = int(year_match.group(1))
            if year < cutoff_year:
                return True
    except:
        pass
    
    return False

def is_generic_section(title: str) -> bool:
    """Check if section is generic/administrative"""
    generic_patterns = [
        r'^definitions?$',
        r'^short title',
        r'^interpretation$',
        r'^commencement$',
        r'^extent$',
        r'^application$',
        r'^preamble$',
        r'^\d+\.$',
        r'^[a-z]\.$',
    ]
    
    title_lower = title.lower().strip()
    for pattern in generic_patterns:
        if re.match(pattern, title_lower):
            return True
    return False

# ============================================================================
# AI QUERY CLASSIFIER (for legal queries only)
# ============================================================================

def classify_legal_query_with_ai(query: str) -> dict:
    """Use AI to classify legal queries"""
    classification_prompt = f"""Analyze this legal query and classify it:

QUERY: "{query}"

Respond with ONLY a JSON object (no other text):
{{
    "collections": ["list", "of", "relevant", "collections"],
    "query_type": "one of: informational, procedural, urgent, greeting",
    "urgency": "one of: low, medium, high"
}}

Available collections:
- banking_laws (Bank accounts, transactions, fraud)
- family_laws (Marriage, divorce, inheritance, custody)
- land_property_laws (Property, ownership, transfer, disputes)
- police_laws (FIR, crimes, penalties, rights)
- religious_laws (Islamic provisions, personal laws)
- pakistan_constitution (Constitution of Pakistan)
- pakistani_laws (General statutes and acts)

Classification rules:
- Use 2-3 most relevant collections
- greeting: "hi", "hello", "thanks" → query_type="greeting"
- Question words: "how to", "what is" → query_type="informational"
- Action-oriented: "file", "register" → query_type="procedural"
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": classification_prompt}],
            temperature=0.1,
            max_tokens=300
        )
        
        result = json.loads(response.choices[0].message.content.strip())
        logger.info(f"Classification: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Classification error: {e}")
        return {
            "collections": ["banking_laws", "family_laws", "land_property_laws", "police_laws"],
            "query_type": "informational",
            "urgency": "medium"
        }

# ============================================================================
# RAG CONTEXT FETCHING
# ============================================================================

# ============================================================================
# HYBRID RETRIEVAL: BM25 + COSINE + CROSS-ENCODER RERANKING
# ============================================================================

def fetch_relevant_context_enhanced(query: str, classification: dict, top_k: int = 10) -> dict:
    """
    Hybrid retrieval using BM25 + Cosine Similarity + Cross-Encoder Reranking
    Final Score = 0.5 * BM25 + 0.5 * CosineSimilarity
    Then rerank top 10 using Cross-Encoder
    """
    logger.info(f"\nFETCHING CONTEXT FROM RAG (HYBRID BM25 + COSINE)")
    
    query_type = classification.get("query_type", "informational")
    
    if query_type == "greeting":
        logger.info("   Greeting detected - skipping RAG search")
        return {"context": "", "collections_searched": [], "results_found": 0, "sources": []}
    
    try:
        client_db = get_chroma_client()
        if not client_db:
            raise Exception("Database not available")
        
        embedding_function = get_embedding_function()
        collections_to_search = classification.get("collections", [])
        
        if not collections_to_search:
            collections_to_search = [
                "banking_laws",
                "family_laws",
                "land_property_laws",
                "police_laws",
                "religious_laws",
                "pakistan_constitution",
                "pakistani_laws",
            ]
        
        all_results = []
        collections_used = set()
        
        # STEP 1: Get initial results from ChromaDB (Cosine Similarity)
        logger.info("   STEP 1: Fetching initial results (Cosine Similarity)...")
        
        for collection_name in collections_to_search:
            try:
                collection = client_db.get_collection(name=collection_name, embedding_function=embedding_function)
                
                # Get more results initially (top_k * 3) for better BM25 scoring
                initial_results = collection.query(query_texts=[query], n_results=top_k * 3)
                
                if initial_results and initial_results['documents'] and initial_results['documents'][0]:
                    documents = initial_results['documents'][0]
                    metadatas = initial_results['metadatas'][0]
                    distances = initial_results['distances'][0] if initial_results.get('distances') else [1.0] * len(documents)
                    
                    # Prepare for BM25
                    corpus = [doc for doc in documents]
                    tokenized_corpus = [doc.lower().split() for doc in corpus]
                    tokenized_query = query.lower().split()
                    
                    # STEP 2: Calculate BM25 scores
                    logger.info(f"   STEP 2: Calculating BM25 scores for {collection_name}...")
                    bm25 = BM25Okapi(tokenized_corpus)
                    bm25_scores = bm25.get_scores(tokenized_query)
                    
                    # Normalize BM25 scores to 0-1 range
                    max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
                    bm25_scores_normalized = [score / max_bm25 for score in bm25_scores]
                    
                    # STEP 3: Combine BM25 + Cosine (convert distance to similarity)
                    logger.info(f"   STEP 3: Combining BM25 + Cosine scores...")
                    
                    for i in range(len(documents)):
                        distance = distances[i]
                        metadata = metadatas[i]
                        
                        # Convert cosine distance to similarity (1 - distance)
                        cosine_similarity = max(0, 1 - distance)
                        
                        # Hybrid score: 0.5 * BM25 + 0.5 * Cosine
                        hybrid_score = 0.5 * bm25_scores_normalized[i] + 0.5 * cosine_similarity
                        
                        # Filter by law name and generic sections
                        law_name = metadata.get('law', 'Unknown Law')
                        if should_filter_law(law_name):
                            continue
                        
                        title = metadata.get('title', '')
                        if is_generic_section(title):
                            continue
                        
                        all_results.append({
                            "text": documents[i],
                            "metadata": metadata,
                            "distance": distance,
                            "cosine_similarity": cosine_similarity,
                            "bm25_score": bm25_scores_normalized[i],
                            "hybrid_score": hybrid_score,
                            "collection": collection_name
                        })
                        collections_used.add(collection_name)
                        
            except Exception as e:
                logger.warning(f"   Error searching {collection_name}: {e}")
                continue
        
        # Sort by hybrid score (higher is better)
        all_results.sort(key=lambda x: x['hybrid_score'], reverse=True)
        
        # Get top candidates for reranking
        top_candidates = all_results[:min(20, len(all_results))]
        
        if not top_candidates:
            logger.warning("   No results found in database")
            return {
                "context": "",
                "collections_searched": list(collections_used),
                "results_found": 0,
                "sources": []
            }
        
        # STEP 4: Cross-Encoder Reranking (if available)
        logger.info(f"   STEP 4: Cross-Encoder reranking top {len(top_candidates)} candidates...")
        
        if cross_encoder is not None:
            try:
                pairs = [[query, result['text']] for result in top_candidates]
                ce_scores = cross_encoder.predict(pairs)
                ce_scores_normalized = (ce_scores - ce_scores.min()) / (ce_scores.max() - ce_scores.min() + 1e-10)
                
                for i, result in enumerate(top_candidates):
                    result['ce_score'] = ce_scores_normalized[i]
                    result['final_score'] = 0.7 * ce_scores_normalized[i] + 0.3 * result['hybrid_score']
                
                top_candidates.sort(key=lambda x: x['final_score'], reverse=True)
                logger.info("   Cross-Encoder reranking complete")
                
            except Exception as e:
                logger.warning(f"   Cross-encoder reranking failed: {e}")
                for result in top_candidates:
                    result['final_score'] = result['hybrid_score']
        else:
            logger.info("   Cross-Encoder not available, using hybrid scores only")
            for result in top_candidates:
                result['final_score'] = result['hybrid_score']
        
        # Get final top results
        top_results = top_candidates[:top_k]
        
        # Build context string
        def meta_val(meta: dict, key: str, default: str = ""):
            return meta.get(key) or default

        def law_name(meta: dict) -> str:
            return meta.get("law") or meta.get("law_name") or meta.get("collection", "Unknown")

        def section_name(meta: dict) -> str:
            return meta.get("section") or meta.get("section_path") or ""

        context_string = "\n\n".join([
            f"[{law_name(r['metadata'])} - {meta_val(r['metadata'], 'title', 'No Title')}]"
            f"{' (' + section_name(r['metadata']) + ')' if section_name(r['metadata']) else ''}\n{r['text'][:1500]}"
            for r in top_results
        ])
        
        # Build sources with detailed scoring and URLs
        sources = []
        for i, r in enumerate(top_results):
            url_info = generate_source_url(r['metadata'], r['collection'])
            
            source_info = {
                "law": law_name(r['metadata']),
                "title": meta_val(r['metadata'], 'title', 'No Title'),
                "section": section_name(r['metadata']),
                "relevance": f"{r['final_score'] * 100:.1f}%",
                "cosine_similarity": f"{r['cosine_similarity']:.3f}",
                "bm25_score": f"{r['bm25_score']:.3f}",
                "hybrid_score": f"{r['hybrid_score']:.3f}",
                "final_score": f"{r['final_score']:.3f}",
                "url": url_info["url"],
                "category": url_info["category"],
                "law_name": url_info["law_name"],
                "year": url_info["year"],
                "citation": url_info["citation"],
                "citation_number": i + 1,
                "text": r['text'][:200] + "..." if len(r['text']) > 200 else r['text']
            }
            
            if 'ce_score' in r:
                source_info['ce_score'] = f"{r['ce_score']:.3f}"
            
            sources.append(source_info)
        
        logger.info("\n   LEGAL SOURCES (final top results):")
        for s in sources:
            logger.info(f"   - {s['law']} - {s['title']} ({s['section'] or 'n/a'}) - {s['relevance']}")
        
        max_log_results = min(10, len(top_results))
        logger.info(f"\n   TOP {max_log_results} RESULTS (RANKED BY FINAL SCORE):")
        for i, r in enumerate(top_results[:max_log_results], 1):
            law = law_name(r['metadata'])
            title = meta_val(r['metadata'], 'title', 'No Title')
            section = section_name(r['metadata'])
            parts = [
                f"   {i}. [{law}] {title}",
                f"      Section: {section}" if section else "      Section: n/a",
                f"      Cosine: {r['cosine_similarity']:.3f}",
                f"      BM25: {r['bm25_score']:.3f}",
                f"      Hybrid: {r['hybrid_score']:.3f}",
            ]
            if 'ce_score' in r:
                parts.append(f"      CE: {r['ce_score']:.3f}")
            parts.append(f"      FINAL: {r['final_score']:.3f}")
            logger.info(" | ".join(parts))
        
        logger.info(f"\n   Selected top {len(top_results)} results for context")
        
        return {
            "context": context_string,
            "collections_searched": list(collections_used),
            "results_found": len(top_results),
            "sources": sources
        }
        
    except Exception as e:
        logger.error(f"Context retrieval error: {e}")
        return {
            "context": f"Error retrieving context: {str(e)}",
            "collections_searched": [],
            "results_found": 0,
            "sources": []
        }

# ============================================================================
# RESPONSE GENERATION - ENHANCED WITH DOCUMENT HANDLING
# ============================================================================

def generate_response_with_document(query: str, document_context: str, document_name: str, 
                                   document_type: str, intent_classification: dict,
                                   legal_context_data: dict = None,
                                   conversation_history: List[ChatMessage] = []) -> str:
    """
    Generate response considering both document data and legal context
    """
    logger.info(f"\nGENERATING RESPONSE")
    logger.info(f"   Intent: {intent_classification['intent']}")
    logger.info(f"   Needs RAG: {intent_classification['needs_rag']}")
    
    current_date = datetime.now().strftime("%B %d, %Y")
    
    document_label = "IMAGE DATA" if document_type == "image" else "DOCUMENT DATA"
    document_section = f"""
{document_label}:
Filename: {document_name}
Content:
{document_context}
"""
    
    if intent_classification['intent'] == "document_analysis":
        system_prompt = f"""You are LegalEase, an AI legal assistant for Pakistani law (Today: {current_date}).

The user has uploaded a document/image and is asking about it. Focus on analyzing the document content.

{document_section}

USER QUERY: {query}

INSTRUCTIONS:
- Carefully analyze the document content provided above
- Answer the user's specific question about the document
- If the document contains legal text, explain it in simple terms
- If it's an image with text, transcribe or explain what you see
- Be direct and helpful
- Only mention legal provisions if directly relevant to the document

Provide a clear, focused response."""

    elif intent_classification['intent'] == "legal_query":
        legal_context = legal_context_data.get("context", "") if legal_context_data else ""
        sources = legal_context_data.get("sources", []) if legal_context_data else []
        
        system_prompt = f"""You are LegalEase, an AI legal assistant for Pakistani law (Today: {current_date}).

The user has a legal question and has provided a document for context.

{document_section}

LEGAL DATABASE CONTEXT:
{legal_context if legal_context else "No specific legal provisions found in database."}

USER QUERY: {query}

INSTRUCTIONS:
- Answer the legal question using both the document and legal database
- Reference specific laws/sections from LEGAL DATABASE CONTEXT
- Use the document as supporting evidence
- Provide practical legal advice
- Mention if consulting a lawyer is recommended

Provide a comprehensive legal analysis."""

    else:  # mixed intent
        legal_context = legal_context_data.get("context", "") if legal_context_data else ""
        
        system_prompt = f"""You are LegalEase, an AI legal assistant for Pakistani law (Today: {current_date}).

The user wants both document analysis and legal advice.

{document_section}

LEGAL DATABASE CONTEXT:
{legal_context if legal_context else "No specific legal provisions found in database."}

USER QUERY: {query}

INSTRUCTIONS:
- First, address what's in the document
- Then, provide relevant legal analysis
- Connect the document content to applicable laws
- Give practical advice

Provide a balanced response covering both aspects."""

    try:
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in conversation_history[-3:]:
            messages.append({"role": msg.role, "content": msg.content})
        
        messages.append({"role": "user", "content": query})
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.3,
            max_tokens=2500
        )
        
        response_text = response.choices[0].message.content
        
        if legal_context_data and legal_context_data.get("results_found", 0) > 0:
            sources = legal_context_data.get("sources", [])

        logger.info(f"   Response generated")
        return response_text
        
    except Exception as e:
        logger.error(f"Response generation error: {e}")
        return "I apologize, but I encountered an error. Please try again."

def generate_simple_response(query: str, classification: dict, 
                            context_data: dict,
                            conversation_history: List[ChatMessage] = []) -> str:
    """Generate response for queries without documents (original logic)"""
    logger.info(f"\nGENERATING SIMPLE RESPONSE")
    
    current_date = datetime.now().strftime("%B %d, %Y")
    context = context_data.get("context", "")[:20000]
    results_found = context_data.get("results_found", 0)
    sources = context_data.get("sources", [])

    query_type = classification.get("query_type", "informational")

    if query_type == "greeting":
        system_prompt = """You are LegalEase, a friendly AI legal assistant for Pakistani law.
Respond naturally and briefly (2-3 sentences). DO NOT mention laws or sections."""
    elif results_found == 0:
        system_prompt = f"""You are LegalEase, an AI legal assistant for Pakistani law (Today: {current_date}).

The database search found no directly relevant sections. However, you can still provide GENERAL legal guidance based on Pakistani legal principles.

USER QUERY: {query}

INSTRUCTIONS:
- Acknowledge that you don't have specific statutory provisions in your current database
- Provide general legal principles that apply in Pakistan
- Suggest what type of laws/sections would typically apply
- Recommend they consult a lawyer for specific statutory references
- Be helpful and informative despite lack of specific sources

Structure your response professionally but acknowledge the limitation."""
    else:
        system_prompt = f"""You are LegalEase, an AI legal assistant for Pakistani law (Today: {current_date}).

CRITICAL RULES:
1. ONLY cite sources from DATABASE CONTEXT below
2. Some sources may be from older laws - note if they may have been amended
3. Provide practical advice along with legal references

DATABASE CONTEXT:
{context}

Provide a structured response with:
- Brief overview of the situation
- Relevant legal provisions (from DATABASE CONTEXT only)
- Practical advice and next steps
- Note if consulting a lawyer is recommended"""

    try:
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in conversation_history[-3:]:
            messages.append({"role": msg.role, "content": msg.content})
        
        messages.append({"role": "user", "content": query})
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.2,
            max_tokens=2000
        )
        
        response_text = response.choices[0].message.content
        
        logger.info(f"   Response generated")
        return response_text
        
    except Exception as e:
        logger.error(f"Response generation error: {e}")

# ============================================================================
# DOCUMENT EXTRACTION FUNCTIONS
# ============================================================================

def extract_text_from_pdf(file_content: bytes) -> str:
    try:
        pdf_file = io.BytesIO(file_content)
        reader = PyPDF2.PdfReader(pdf_file)
        return "".join([page.extract_text() or "" for page in reader.pages])
    except Exception as e:
        return f"Error: {str(e)}"

def extract_text_from_docx(file_content: bytes) -> str:
    try:
        docx_file = io.BytesIO(file_content)
        doc = docx.Document(docx_file)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        return f"Error: {str(e)}"

def extract_text_from_image_utrnet(file_content: bytes) -> str:
    """
    Primary OCR: Extract Urdu/English text using UTRNet via Hugging Face Space.
    Returns extracted text or raises an exception on failure.
    """
    import tempfile
    import os
    from gradio_client import Client, handle_file

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name

    try:
        logger.info("[OCR] Attempting UTRNet OCR via HuggingFace Space...")
        hf_client = Client("abdur75648/UrduOCR-UTRNet")
        result = hf_client.predict(
            input=handle_file(tmp_path),
            api_name="/predict"
        )
        # result is a tuple: (annotated_image, recognized_text)
        recognized_text = result[1] if isinstance(result, (list, tuple)) else str(result)
        logger.info(f"[OK] UTRNet OCR completed: {len(recognized_text)} characters")
        return recognized_text
    finally:
        os.unlink(tmp_path)


def extract_text_from_image_tesseract(file_content: bytes) -> str:
    """
    Fallback OCR: Extract text using Tesseract with Urdu + English support.
    """
    image = Image.open(io.BytesIO(file_content))
    try:
        text = pytesseract.image_to_string(image, lang='eng+urd')
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "Tesseract OCR is not installed or not found in PATH. "
            "Install it from https://github.com/tesseract-ocr/tesseract"
        ) from e
    except Exception:
        text = pytesseract.image_to_string(image, lang='eng')
    return text.strip() if text.strip() else "No text detected in image"


def extract_text_from_image(file_content: bytes) -> str:
    """
    Extract text from image.
    Primary: UTRNet (HuggingFace Space) — optimized for Urdu printed text.
    Fallback: Tesseract OCR — handles both Urdu and English.
    """
    # --- Try UTRNet first ---
    try:
        text = extract_text_from_image_utrnet(file_content)
        if text and text.strip():
            return text.strip()
        logger.warning("[OCR] UTRNet returned empty text, falling back to Tesseract...")
    except Exception as e:
        logger.warning(f"[OCR] UTRNet failed ({e}), falling back to Tesseract...")

    # --- Fallback: Tesseract ---
    try:
        logger.info("[OCR] Using Tesseract as fallback...")
        text = extract_text_from_image_tesseract(file_content)
        logger.info(f"[OK] Tesseract OCR completed: {len(text)} characters")
        return text
    except Exception as e:
        return f"Error extracting text from image: {str(e)}"

# ============================================================================
# CONTRACT VALIDATION
# ============================================================================

def is_contract_document(text: str) -> tuple:
    """
    Validate whether the uploaded document is a legal document suitable for analysis.
    Accepts contracts, agreements, FIRs, court orders, legal notices, property papers,
    employment documents, and any other legal/official document.
    Rejects only clearly non-legal files: bank statements, invoices, stories, essays, etc.
    Defaults to ALLOW on any ambiguity or AI failure.
    """
    if not text or len(text.strip()) < 50:
        return False, (
            "Document is too short to analyse. "
            "Please upload a complete legal document."
        )

    # ── Quick keyword pre-check — if obvious legal terms present, skip the AI call ──
    legal_signals = [
        "agreement", "contract", "party", "parties", "whereas", "hereinafter",
        "shall", "obligations", "termination", "clause", "section", "article",
        "fir", "first information report", "plaintiff", "defendant", "court",
        "tribunal", "judgment", "order", "decree", "notice", "deed", "lease",
        "tenant", "landlord", "employment", "salary", "arbitration", "penalty",
        "damages", "signed", "witness", "stamp", "notary", "affidavit",
        "memorandum", "mou", "nda", "non-disclosure", "confidential",
        "property", "transfer", "mortgage", "power of attorney"
    ]
    text_lower = text[:3000].lower()
    signal_hits = sum(1 for kw in legal_signals if kw in text_lower)
    if signal_hits >= 2:
        logger.info(f"[CONTRACT CHECK] Keyword pre-check passed ({signal_hits} legal signals) — skipping AI call")
        return True, ""

    # ── AI validation for edge cases ─────────────────────────────────────────────
    detection_prompt = f"""You are a legal document classifier for a Pakistani legal AI assistant.

Determine whether the following document is a LEGAL DOCUMENT that should be analysed.

ACCEPT (respond YES) if the document is ANY of:
- Contracts and agreements (employment, service, lease, sale, purchase, partnership, etc.)
- Terms of service / terms and conditions
- MOUs, NDAs, affidavits, power of attorney
- FIRs (First Information Reports) or police documents
- Court orders, judgments, decrees, legal notices
- Property papers, title deeds, mutation documents
- Government or official documents
- Any document with legal clauses, obligations, or parties

REJECT (respond NO) ONLY if the document is clearly:
- A bank/account statement or financial record
- A simple invoice, receipt, or bill
- A news article, essay, story, or tutorial
- A personal letter or chat transcript
- A CV/resume or certificate with no legal content
- Clearly random or non-document text

When in doubt, respond YES.

Document text (first 3000 characters):
{text[:3000]}

Respond with ONLY the word YES or NO."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a legal document classifier. Respond with only 'YES' or 'NO'. When in doubt, say YES."
                },
                {"role": "user", "content": detection_prompt}
            ],
            temperature=0.1,
            max_tokens=10
        )

        ai_response = response.choices[0].message.content.strip().upper()
        logger.info(f"[CONTRACT CHECK] AI response: '{ai_response}'")

        # Accept if YES is anywhere in the response
        if "YES" in ai_response:
            return True, ""

        # Rejected — find out what type it is (single follow-up call)
        try:
            type_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "Identify the document type in 2-5 words."},
                    {
                        "role": "user",
                        "content": f"What type of document is this?\n\n{text[:1500]}\n\nRespond with just the document type (e.g. 'bank statement', 'invoice', 'news article')."
                    }
                ],
                temperature=0.1,
                max_tokens=15
            )
            doc_type = type_response.choices[0].message.content.strip()
            logger.info(f"[CONTRACT CHECK] Rejected document type: '{doc_type}'")
            return False, (
                f"This document appears to be a '{doc_type}', not a legal document. "
                "Please upload a contract, agreement, FIR, court document, property paper, "
                "legal notice, or similar legal document for analysis."
            )
        except Exception:
            # If the type-check call also fails, default to allow
            logger.warning("[CONTRACT CHECK] Type-check call failed — defaulting to allow")
            return True, ""

    except Exception as e:
        # Any failure in validation → default to allow so users are never blocked by AI errors
        logger.error(f"[CONTRACT CHECK] AI validation error: {e} — defaulting to allow")
        return True, ""

# ============================================================================
# ENHANCED CONTRACT ANALYSIS
# ============================================================================

ENHANCED_ANALYSIS_PROMPT = """You are LegalEase, a senior Pakistani legal expert specializing in contract law.

Analyze the following contract thoroughly and return a detailed JSON report.

CONTRACT TEXT:
{contract_text}

Return ONLY a valid JSON object with this EXACT structure (no markdown, no extra text):

{{
  "document_type": "string - what type of contract this is (e.g. Employment Agreement, Property Sale Agreement, Service Contract, NDA, Partnership Agreement, Lease Agreement, etc.)",
  "parties": ["list of party names/roles detected in the contract"],
  "summary": "3-4 sentences explaining what this contract does, who the parties are, and what obligations are created",
  "compliance_score": 0,
  "overall_risk": "one of: critical, high, medium, low",
  "risks": [
    {{
      "severity": "one of: critical, high, medium, low",
      "category": "category name e.g. Payment Terms / Jurisdiction / Termination / Liability / Confidentiality / IP Rights / Dispute Resolution / Force Majeure / Indemnification",
      "title": "Short title of the risk (max 8 words)",
      "description": "2-3 sentences explaining why this is a risk and what harm it could cause",
      "original_clause": "Quote or paraphrase the specific problematic text from the contract, or null if it is a general structural issue",
      "suggested_fix": "A rewritten version of the clause that fixes the problem, using Pakistani legal standards",
      "law_reference": "Relevant Pakistani law and section e.g. Contract Act 1872 Section 73, or null"
    }}
  ],
  "missing_clauses": [
    {{
      "title": "Name of the missing clause",
      "why_needed": "2 sentences explaining why this clause is important under Pakistani law",
      "suggested_text": "A full draft clause the user can add to their contract",
      "law_reference": "Relevant Pakistani law, or null"
    }}
  ],
  "applicable_laws": [
    {{
      "name": "Full name of the law",
      "year": "Year as string or null",
      "relevance": "1-2 sentences on how this law applies to this specific contract",
      "key_sections": ["Section X - description", "Section Y - description"]
    }}
  ],
  "recommendations": ["5 specific actionable steps the party should take, most urgent first"],
  "timeline": "Realistic time estimate for professional legal review",
  "estimated_cost": "PKR cost range for professional review",
  "key_dates": ["Any important dates found in the contract e.g. effective date, expiry date, payment due dates"],
  "jurisdiction": "Detected or assumed jurisdiction/court"
}}

SCORING GUIDE for compliance_score (0-100):
- Start at 100
- Deduct 20-25 per critical risk
- Deduct 10-15 per high risk
- Deduct 5-8 per medium risk
- Deduct 2-3 per missing clause
- Minimum score is 5

REQUIREMENTS:
- Identify 4-8 specific risks (not generic warnings)
- For each risk, provide a real suggested fix clause in proper legal language
- Identify 3-5 missing clauses that are standard in Pakistani contracts of this type
- Reference at least 3 applicable Pakistani laws with specific sections
- Be specific to this contract's actual content, not generic advice
- Reference: Contract Act 1872, Specific Relief Act 1877, Arbitration Act 1940, Punjab/Sindh tenancy laws, Employment Ordinance 1968, Companies Act 2017, Transfer of Property Act 1882, Stamp Act 1899 as applicable"""


def _fallback_analysis() -> ContractAnalysis:
    """Minimal fallback when the enhanced analysis path fails"""
    return ContractAnalysis(
        document_type="Legal Agreement",
        parties=[],
        summary=(
            "Automated analysis could not be completed. "
            "Please have this contract reviewed by a qualified Pakistani legal professional "
            "to ensure compliance and protect your interests."
        ),
        compliance_score=50,
        overall_risk="high",
        risks=[
            RiskItem(
                severity="high",
                category="General",
                title="Manual review required",
                description=(
                    "Automated analysis encountered an issue. The contract should be "
                    "reviewed manually to identify specific risks and problematic clauses."
                ),
                original_clause=None,
                suggested_fix=None,
                law_reference="Contract Act 1872"
            )
        ],
        missing_clauses=[
            MissingClause(
                title="Governing law and jurisdiction",
                why_needed=(
                    "Every contract must specify which law governs it and which courts "
                    "have jurisdiction. Without this, disputes become very difficult to resolve."
                ),
                suggested_text=(
                    "This Agreement shall be governed by and construed in accordance with "
                    "the laws of Pakistan. Any dispute arising under or in connection with "
                    "this Agreement shall be subject to the exclusive jurisdiction of the "
                    "courts of [City], Pakistan."
                ),
                law_reference="Contract Act 1872"
            )
        ],
        applicable_laws=[
            ApplicableLaw(
                name="Contract Act 1872",
                year="1872",
                relevance="Governs all aspects of contract formation, performance and breach in Pakistan.",
                key_sections=["Section 73 - Compensation for breach", "Section 74 - Liquidated damages"]
            )
        ],
        recommendations=[
            "Seek immediate review from a Pakistani legal expert",
            "Verify compliance with Contract Act 1872 and Specific Relief Act 1877",
            "Ensure all parties' rights and obligations are clearly defined",
            "Add proper signatures and witness requirements per Pakistani law",
            "Include clear dispute resolution mechanism"
        ],
        timeline="2-4 weeks for comprehensive legal review",
        estimated_cost="PKR 25,000 - 100,000 depending on contract complexity",
        key_dates=[],
        jurisdiction="Pakistan (unspecified)"
    )


def analyze_contract_text(contract_text: str) -> ContractAnalysis:
    """
    Enhanced contract analysis — returns a rich structured report with:
    - Compliance score (0-100)
    - Severity-graded risks with problematic clause text and suggested fix clauses
    - Missing clauses with draft text the user can insert
    - Applicable Pakistani laws with specific sections
    - Prioritised action plan
    """
    # Validate that this is actually a contract
    is_valid, error_message = is_contract_document(contract_text)
    if not is_valid:
        raise ValueError(error_message)

    prompt = ENHANCED_ANALYSIS_PROMPT.format(contract_text=contract_text[:10000])

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Pakistani legal expert. "
                        "Always respond with ONLY valid JSON. "
                        "No markdown fences, no preamble, no trailing text."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=4000
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if model wraps anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        data = json.loads(raw)

        # ── Validate and normalise fields ────────────────────────────────
        score = int(data.get("compliance_score", 60))
        score = max(5, min(100, score))

        risk_level = data.get("overall_risk", "medium").lower()
        if risk_level not in ("critical", "high", "medium", "low"):
            risk_level = "medium"

        # Risks
        risks = []
        for r in data.get("risks", [])[:8]:
            sev = r.get("severity", "medium").lower()
            if sev not in ("critical", "high", "medium", "low"):
                sev = "medium"
            risks.append(RiskItem(
                severity=sev,
                category=r.get("category", "General"),
                title=r.get("title", "Risk identified"),
                description=r.get("description", ""),
                original_clause=r.get("original_clause"),
                suggested_fix=r.get("suggested_fix"),
                law_reference=r.get("law_reference")
            ))

        # Missing clauses
        missing_clauses = []
        for m in data.get("missing_clauses", [])[:6]:
            missing_clauses.append(MissingClause(
                title=m.get("title", "Missing clause"),
                why_needed=m.get("why_needed", ""),
                suggested_text=m.get("suggested_text", ""),
                law_reference=m.get("law_reference")
            ))

        # Applicable laws
        applicable_laws = []
        for l in data.get("applicable_laws", [])[:6]:
            applicable_laws.append(ApplicableLaw(
                name=l.get("name", ""),
                year=str(l.get("year", "")) if l.get("year") else None,
                relevance=l.get("relevance", ""),
                key_sections=l.get("key_sections", [])
            ))

        recommendations = data.get("recommendations", [])
        if not recommendations:
            recommendations = [
                "Have this contract reviewed by a Pakistani legal expert",
                "Ensure compliance with Contract Act 1872",
                "Add all missing standard clauses before signing",
                "Clarify all ambiguous terms in writing",
                "Specify jurisdiction and dispute resolution mechanism"
            ]

        return ContractAnalysis(
            document_type=data.get("document_type", "Legal Agreement"),
            parties=data.get("parties", []),
            summary=data.get("summary", "Contract analysis completed."),
            compliance_score=score,
            overall_risk=risk_level,
            risks=risks,
            missing_clauses=missing_clauses,
            applicable_laws=applicable_laws,
            recommendations=recommendations,
            timeline=data.get("timeline", "2-4 weeks"),
            estimated_cost=data.get("estimated_cost", "PKR 25,000 - 100,000"),
            key_dates=data.get("key_dates", []),
            jurisdiction=data.get("jurisdiction", "Pakistan (jurisdiction unspecified)")
        )

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in enhanced analysis: {e}")
        return _fallback_analysis()
    except Exception as e:
        logger.error(f"Enhanced contract analysis error: {e}")
        return _fallback_analysis()

# ============================================================================
# API ROUTES
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "LegalEase Pakistan API - Fixed Image/Document Pipeline",
        "version": "3.0.0",
        "improvements": [
            "Proper image/document handling",
            "Query intent classification",
            "Smart RAG activation",
            "Labels image data clearly",
            "Document-first, RAG-second approach",
            "Enhanced contract analysis with compliance score, risk grades, suggested fixes"
        ],
        "status": "active"
    }

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.post("/auth/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user"""
    email = request.email.lower().strip()
    
    if email in users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    if "@" not in email or "." not in email.split("@")[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )
    
    user_id = str(uuid.uuid4())
    users[email] = {
        "id": user_id,
        "email": email,
        "name": request.name.strip(),
        "password_hash": hash_password(request.password),
        "created_at": datetime.now().isoformat()
    }
    save_users()
    
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {
        "user_id": user_id,
        "email": email,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
    }
    save_sessions()
    
    logger.info(f"New user registered: {email}")
    
    return AuthResponse(
        success=True,
        message="Registration successful",
        session_token=session_token,
        user={
            "id": user_id,
            "email": email,
            "name": request.name.strip()
        }
    )

@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Login user and create session"""
    email = request.email.lower().strip()
    
    if email not in users:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    user = users[email]
    
    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {
        "user_id": user["id"],
        "email": email,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
    }
    save_sessions()
    
    logger.info(f"User logged in: {email}")
    
    return AuthResponse(
        success=True,
        message="Login successful",
        session_token=session_token,
        user={
            "id": user["id"],
            "email": email,
            "name": user["name"]
        }
    )

@app.post("/auth/logout")
async def logout(request: Request = None):
    """Logout user and invalidate session"""
    try:
        body = await request.json() if request else {}
        session_token = body.get("session_token") if body else None
    except:
        session_token = None
    
    if session_token and session_token in sessions:
        del sessions[session_token]
        save_sessions()
        logger.info("User logged out")
    
    return {"success": True, "message": "Logged out successfully"}

@app.get("/auth/session", response_model=SessionResponse)
async def check_session(session_token: str = None):
    """Check if session is valid and return user info"""
    if not session_token or session_token not in sessions:
        return SessionResponse(authenticated=False, user=None)
    
    session = sessions[session_token]
    
    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.now() > expires_at:
        del sessions[session_token]
        save_sessions()
        return SessionResponse(authenticated=False, user=None)
    
    email = session["email"]
    if email not in users:
        return SessionResponse(authenticated=False, user=None)
    
    user = users[email]
    return SessionResponse(
        authenticated=True,
        user={
            "id": user["id"],
            "email": email,
            "name": user["name"]
        }
    )

# Helper function to get current user from session
async def get_current_user(session_token: str = None) -> Optional[Dict]:
    """Get current user from session token"""
    if not session_token or session_token not in sessions:
        return None
    
    session = sessions[session_token]
    expires_at = datetime.fromisoformat(session["expires_at"])
    if datetime.now() > expires_at:
        del sessions[session_token]
        save_sessions()
        return None
    
    email = session["email"]
    if email not in users:
        return None
    
    user = users[email]
    return {
        "id": user["id"],
        "email": email,
        "name": user["name"]
    }

def truncate_document_context(context: str, max_length: int = MAX_DOCUMENT_CHARS_FOR_LLM) -> str:
    """Truncate document context if too long"""
    if not context or len(context) <= max_length:
        return context
    truncated = context[:max_length]
    return f"{truncated}\n\n[Document truncated - showing first {max_length} characters of {len(context)} total]"

@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute per IP
async def chat_endpoint(request: Request, chat_request: ChatRequest):
    try:
        logger.info(f"\n{'*'*80}")
        logger.info(f"NEW CHAT REQUEST: {chat_request.message}")
        
        document_context = chat_request.document_context
        if document_context:
            original_length = len(document_context)
            document_context = truncate_document_context(document_context)
            if len(document_context) < original_length:
                logger.info(f"   Document truncated from {original_length} to {len(document_context)} characters")
        
        has_document = bool(document_context and document_context.strip())
        
        if has_document:
            logger.info(f"Document attached: {chat_request.document_name}")
            logger.info(f"   Length: {len(document_context)} characters")
            
            doc_type = detect_document_type(chat_request.document_name)
            logger.info(f"   Type: {doc_type}")
            
            intent_classification = classify_query_intent(
                chat_request.message, 
                has_document=True, 
                document_type=doc_type
            )
            logger.info(f"   Intent: {intent_classification}")
            
            legal_context_data = None
            if intent_classification['needs_rag']:
                logger.info("   RAG search needed")
                legal_classification = classify_legal_query_with_ai(chat_request.message)
                legal_context_data = fetch_relevant_context_enhanced(
                    chat_request.message, 
                    legal_classification, 
                    top_k=10
                )
            else:
                logger.info("   Skipping RAG - pure document analysis")
            
            response = generate_response_with_document(
                query=chat_request.message,
                document_context=document_context,
                document_name=chat_request.document_name,
                document_type=doc_type,
                intent_classification=intent_classification,
                legal_context_data=legal_context_data,
                conversation_history=chat_request.conversation_history
            )
            
            sources = legal_context_data.get("sources", []) if legal_context_data else []
            collections = legal_context_data.get("collections_searched", []) if legal_context_data else []
            
        else:
            logger.info("   No document attached - standard legal query")
            
            classification = classify_legal_query_with_ai(chat_request.message)
            context_data = fetch_relevant_context_enhanced(
                chat_request.message, 
                classification, 
                top_k=10
            )
            response = generate_simple_response(
                chat_request.message, 
                classification, 
                context_data, 
                chat_request.conversation_history
            )
            
            sources = context_data.get("sources", [])
            collections = context_data.get("collections_searched", [])
        
        logger.info(f"\nREQUEST COMPLETE\n")
        
        return ChatResponse(
            response=response,
            sources=sources,
            collections_used=collections,
            status="success"
        )
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/analyze-contract")
async def analyze_contract(file: UploadFile = File(...)):
    try:
        file_content = await file.read()
        
        if file.content_type == "application/pdf":
            contract_text = extract_text_from_pdf(file_content)
        elif file.content_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]:
            contract_text = extract_text_from_docx(file_content)
        elif file.content_type == "text/plain":
            contract_text = file_content.decode("utf-8")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")
        
        return analyze_contract_text(contract_text)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-document")
async def extract_document_text(file: UploadFile = File(...)):
    """
    Extract text from uploaded document (PDF, DOCX, TXT, or Images with OCR).
    Returns the extracted text to be used in chat context.
    """
    try:
        file_content = await file.read()
        extracted_text = ""
        
        logger.info(f"[DOC] Extracting text from: {file.filename} (type: {file.content_type})")
        
        if file.content_type == "application/pdf":
            extracted_text = extract_text_from_pdf(file_content)
            logger.info(f"[OK] PDF extracted: {len(extracted_text)} characters")
            
        elif file.content_type in ["application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                                     "application/msword"]:
            extracted_text = extract_text_from_docx(file_content)
            logger.info(f"[OK] DOCX extracted: {len(extracted_text)} characters")
            
        elif file.content_type == "text/plain":
            extracted_text = file_content.decode("utf-8")
            logger.info(f"[OK] TXT extracted: {len(extracted_text)} characters")
            
        elif file.content_type in ["image/jpeg", "image/jpg", "image/png", "image/webp"]:
            extracted_text = extract_text_from_image(file_content)
            logger.info(f"[OK] Image OCR completed: {len(extracted_text)} characters")
            
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {file.content_type}. Supported: PDF, DOCX, TXT, JPG, PNG"
            )
        
        if not extracted_text or extracted_text.startswith("Error"):
            return {
                "success": False,
                "extracted_text": "",
                "message": extracted_text if extracted_text.startswith("Error") else "No text could be extracted",
                "filename": file.filename
            }
        
        return {
            "success": True,
            "extracted_text": extracted_text,
            "message": "Text extracted successfully",
            "filename": file.filename,
            "char_count": len(extracted_text)
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Document extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    client_db = get_chroma_client()
    collections_count = len(client_db.list_collections()) if client_db else 0
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "database_connected": client_db is not None,
        "collections_available": collections_count
    }

@app.get("/collections")
async def list_collections():
    client_db = get_chroma_client()
    if not client_db:
        raise HTTPException(status_code=500, detail="Database connection error")
    
    collections = client_db.list_collections()
    return {
        "collections": [
            {"name": col.name, "count": col.count()}
            for col in collections
        ]
    }

if os.path.exists("build"):
    app.mount("/", StaticFiles(directory="build", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("App:app", host="0.0.0.0", port=8000, reload=True, log_level="info")