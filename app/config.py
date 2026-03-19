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
CHROMA_PERSIST_DIR = INDEX_DIR / "chroma"
CACHE_FILE = PROJECT_ROOT / "decision_cache.json"
EXCEL_FILE = PROJECT_ROOT / "decision_log.xlsx"

# ── API Keys ─────────────────────────────────────────────────────────────────

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Add it to .env (required for embeddings)")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
if ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

# ── Model Settings ───────────────────────────────────────────────────────────
# When ANTHROPIC_API_KEY is not set, all agents use OpenAI. Otherwise set USE_OPENAI_FOR_AGENTS=true to force OpenAI.
USE_OPENAI_FOR_AGENTS = (
    os.getenv("USE_OPENAI_FOR_AGENTS", "").lower() in ("1", "true", "yes")
    or not ANTHROPIC_API_KEY
)
OPENAI_AGENT_MODEL = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")

CLASSIFIER_MODEL = os.getenv("ANTHROPIC_CLASSIFIER_MODEL", "claude-haiku-4-5-20251001")
RESEARCHER_MODEL = os.getenv("ANTHROPIC_RESEARCHER_MODEL", "claude-sonnet-4-6")
LLM_MODEL = os.getenv("ANTHROPIC_LLM_MODEL", "claude-sonnet-4-6")  # analyst, writer, judge
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
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
DB_SEMANTIC_THRESHOLD = float(os.getenv("DB_SEMANTIC_THRESHOLD", "0.90"))
EMBEDDING_TIMEOUT = int(os.getenv("EMBEDDING_TIMEOUT", "30"))

# ── PostgreSQL (Decision DB) ────────────────────────────────────────────────

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB = os.getenv("POSTGRES_DB", "refund_db")

# ── DOT Regulatory Thresholds ────────────────────────────────────────────────
# Source: 14 CFR Part 259 / DOT Automatic Refund Rule (2024-07177)
# Update these when DOT regulations change — tools read from here.

DELAY_THRESHOLD_DOMESTIC_HOURS = 3.0       # domestic flight delay → significant
DELAY_THRESHOLD_INTL_HOURS = 6.0           # international flight delay → significant
BAGGAGE_THRESHOLD_DOMESTIC_HOURS = 12.0    # domestic bag delay → significantly delayed
BAGGAGE_THRESHOLD_INTL_SHORT_HOURS = 15.0  # intl flight ≤12h: bag delay threshold
BAGGAGE_THRESHOLD_INTL_LONG_HOURS = 30.0   # intl flight >12h: bag delay threshold
BAGGAGE_INTL_FLIGHT_DURATION_CUTOFF = 12.0 # flight duration that splits short/long intl

# ── LangFuse Observability ───────────────────────────────────────────────────

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
# Support both LANGFUSE_HOST (SDK standard) and LANGFUSE_BASE_URL (alias)
LANGFUSE_HOST = (
    os.getenv("LANGFUSE_HOST")
    or os.getenv("LANGFUSE_BASE_URL")
    or "https://cloud.langfuse.com"
)

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


def ensure_anthropic_or_fallback(logger=None):
    """
    Try a minimal Anthropic call. If it fails (e.g. credit too low, 400),
    set USE_OPENAI_FOR_AGENTS so all agents use OpenAI for this process.
    """
    global USE_OPENAI_FOR_AGENTS
    if USE_OPENAI_FOR_AGENTS or not ANTHROPIC_API_KEY:
        if logger and not ANTHROPIC_API_KEY:
            logger.info("ANTHROPIC_API_KEY not set; using OpenAI for agents.")
        return
    try:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=CLASSIFIER_MODEL, temperature=0, max_tokens=10)
        llm.invoke("Hi")
    except Exception as e:
        msg = str(e).lower()
        if "credit" in msg or "balance" in msg or "too low" in msg or "400" in msg:
            USE_OPENAI_FOR_AGENTS = True
            if logger:
                logger.info("Anthropic unavailable (%s); using OpenAI for all agents.", type(e).__name__)
            return
        raise
