#!/usr/bin/env python3
"""
Clear decision cache (JSON) and PostgreSQL refund_decisions table.

Run this after changing OPENAI_EMBEDDING_MODEL so that:
  - cache exact hit / cache semantic hit
  - db exact hit / db semantic hit
  - RAG (full pipeline)
all use the same embedding model and the flow order stays consistent.

Usage (from repo root):
  python scripts/clear_decision_data.py
"""

import json
import os
import sys
from pathlib import Path

# Run from repo root so imports work
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")

CACHE_FILE = REPO_ROOT / "decision_cache.json"
TABLE_NAME = "refund_decisions"


def _get_db_params():
    url = os.getenv("DATABASE_URL")
    if url:
        return {"url": url}
    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "dbname": os.getenv("POSTGRES_DB", "refund_db"),
    }


def clear_cache():
    """Overwrite decision_cache.json with empty list."""
    CACHE_FILE.write_text("[]", encoding="utf-8")
    print(f"[CLEAN] Cache cleared: {CACHE_FILE}")


def clear_db():
    """Truncate refund_decisions table."""
    params = _get_db_params()
    if not params:
        print("[CLEAN] No PostgreSQL config (POSTGRES_* / DATABASE_URL); skipping DB.")
        return
    try:
        import psycopg2
    except ImportError:
        print("[CLEAN] psycopg2 not installed; skipping DB.")
        return
    try:
        if "url" in params:
            conn = psycopg2.connect(params["url"])
        else:
            conn = psycopg2.connect(
                host=params["host"],
                port=params["port"],
                user=params["user"],
                password=params["password"],
                dbname=params["dbname"],
            )
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE TABLE {TABLE_NAME} RESTART IDENTITY CASCADE")
        conn.commit()
        conn.close()
        print(f"[CLEAN] PostgreSQL table {TABLE_NAME} truncated.")
    except Exception as e:
        print(f"[CLEAN] DB error: {e}")


def main():
    print("Clearing decision data for fresh start with current embedding model...")
    clear_cache()
    clear_db()
    print("Done. Flow order: cache exact → cache semantic → db exact → db semantic → RAG.")


if __name__ == "__main__":
    main()
