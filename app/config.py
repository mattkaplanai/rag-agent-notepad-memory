"""
Central configuration for the Airlines Refund Decision Maker.
All settings in one place — model names, thresholds, paths, etc.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "bilgiler"
INDEX_DIR = PROJECT_ROOT / "storage"
CACHE_FILE = PROJECT_ROOT / "decision_cache.json"
EXCEL_FILE = PROJECT_ROOT / "decision_log.xlsx"

# ── API Keys ─────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Add it to .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# ── Model Settings ───────────────────────────────────────────────────────────

LLM_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
CLASSIFIER_TEMPERATURE = 0.0
SPECIALIST_TEMPERATURE = 0.1
JUDGE_TEMPERATURE = 0.0

# ── RAG Settings ─────────────────────────────────────────────────────────────

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
RETRIEVAL_TOP_K = 12
VECTOR_SEARCH_K = 16
BM25_SEARCH_K = 16
REQUIRED_EXTS = [".pdf", ".docx", ".doc", ".txt", ".md"]

# ── Cache Settings ───────────────────────────────────────────────────────────

SEMANTIC_THRESHOLD = 0.90

# ── UI Settings ──────────────────────────────────────────────────────────────

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 7861

# ── Dropdown Options ─────────────────────────────────────────────────────────

CASE_TYPES = [
    "Flight Cancellation",
    "Schedule Change / Significant Delay",
    "Downgrade to Lower Class",
    "Baggage Lost or Delayed",
    "Ancillary Service Not Provided",
    "24-Hour Cancellation (within 24h of booking)",
]

FLIGHT_TYPES = ["Domestic (within US)", "International"]
TICKET_TYPES = ["Refundable", "Non-refundable"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Cash", "Check", "Airline Miles", "Other"]

ACCEPTED_ALTERNATIVES = [
    "No — I did not accept any alternative",
    "Yes — I accepted a rebooked flight",
    "Yes — I accepted a travel voucher / credit",
    "Yes — I accepted other compensation (miles, etc.)",
    "Yes — I traveled on the flight anyway",
]
