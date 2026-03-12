"""
PostgreSQL store for refund decisions (exact hash + semantic similarity).

Embeddings stored as JSONB; cosine similarity computed in Python (no pgvector needed).
When POSTGRES_HOST is not set, all operations silently no-op.
"""

import json
import logging
from contextlib import contextmanager
from typing import List, Optional

from app.config import (
    DB_SEMANTIC_THRESHOLD,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from app.utils import cosine_similarity, hash_inputs

logger = logging.getLogger(__name__)

TABLE_NAME = "refund_decisions"


def _get_connection_params() -> Optional[dict]:
    if not POSTGRES_HOST:
        return None
    return {
        "host": POSTGRES_HOST,
        "port": POSTGRES_PORT,
        "user": POSTGRES_USER,
        "password": POSTGRES_PASSWORD,
        "dbname": POSTGRES_DB,
    }


@contextmanager
def _connection():
    params = _get_connection_params()
    if not params:
        yield None
        return
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        logger.warning("psycopg2 not installed — DB layer disabled.")
        yield None
        return
    conn = None
    try:
        conn = psycopg2.connect(
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=params["password"],
            dbname=params["dbname"],
            cursor_factory=RealDictCursor,
        )
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("DB connection error: %s", e)
        yield None
    finally:
        if conn:
            conn.close()


def _create_table(conn) -> None:
    if not conn:
        return
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                input_hash VARCHAR(64) UNIQUE NOT NULL,
                case_type TEXT,
                flight_type TEXT,
                ticket_type TEXT,
                payment_method TEXT,
                accepted_alternative TEXT,
                description_preview TEXT,
                embedding JSONB,
                result JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)


class DecisionDB:
    """PostgreSQL-backed decision store with exact hash and semantic lookup."""

    def __init__(self):
        self._enabled = _get_connection_params() is not None
        if self._enabled:
            with _connection() as conn:
                if conn:
                    _create_table(conn)
                    logger.info("PostgreSQL connected; table %s ready.", TABLE_NAME)
                else:
                    self._enabled = False
                    logger.warning("PostgreSQL connection failed — DB layer disabled.")
        else:
            logger.info("No POSTGRES_HOST set — DB layer disabled.")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get_by_hash(
        self,
        case_type: str,
        flight_type: str,
        ticket_type: str,
        payment_method: str,
        accepted_alternative: str,
        description: str,
    ) -> Optional[dict]:
        """Exact lookup by input hash. Returns result dict or None."""
        if not self._enabled:
            return None
        input_hash = hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        with _connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT result FROM {TABLE_NAME} WHERE input_hash = %s",
                    (input_hash,),
                )
                row = cur.fetchone()
                if row and row.get("result"):
                    logger.info("DB exact hit (hash=%s...).", input_hash[:12])
                    return row["result"] if isinstance(row["result"], dict) else json.loads(row["result"])
                logger.info("DB exact miss.")
                return None

    def get_by_semantic(
        self,
        query_embedding: list[float],
        threshold: float = DB_SEMANTIC_THRESHOLD,
    ) -> Optional[dict]:
        """Find best match by cosine similarity. Returns result dict or None."""
        if not self._enabled or not query_embedding:
            return None
        with _connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT embedding, result FROM {TABLE_NAME} "
                    f"WHERE embedding IS NOT NULL AND jsonb_array_length(embedding) > 0"
                )
                rows = cur.fetchall()
        if not rows:
            return None
        best_sim = 0.0
        best_result = None
        for row in rows:
            emb = row.get("embedding")
            if not emb:
                continue
            if isinstance(emb, str):
                emb = json.loads(emb)
            if not isinstance(emb, list) or len(emb) != len(query_embedding):
                continue
            sim = cosine_similarity(query_embedding, emb)
            if sim > best_sim:
                best_sim = sim
                res = row.get("result")
                best_result = res if isinstance(res, dict) else (json.loads(res) if res else None)
        if best_result and best_sim >= threshold:
            logger.info("DB semantic hit (similarity %.3f).", best_sim)
            return best_result
        logger.info("DB semantic miss (best %.3f).", best_sim)
        return None

    def insert(
        self,
        case_type: str,
        flight_type: str,
        ticket_type: str,
        payment_method: str,
        accepted_alternative: str,
        description: str,
        result: dict,
        embedding: Optional[list[float]] = None,
    ) -> None:
        """Insert a decision. Embedding stored as JSONB for semantic lookup."""
        if not self._enabled:
            return
        input_hash = hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        with _connection() as conn:
            if not conn:
                return
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE_NAME}
                    (input_hash, case_type, flight_type, ticket_type, payment_method,
                     accepted_alternative, description_preview, embedding, result)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (input_hash) DO NOTHING
                    """,
                    (
                        input_hash,
                        case_type,
                        flight_type,
                        ticket_type,
                        payment_method,
                        accepted_alternative,
                        (description or "")[:200],
                        json.dumps(embedding) if embedding else None,
                        json.dumps(result, ensure_ascii=False),
                    ),
                )
                if cur.rowcount:
                    logger.info("DB insert: 1 row added.")
                else:
                    logger.info("DB insert: skipped (duplicate hash).")

    def stats(self) -> dict:
        """Return row count."""
        if not self._enabled:
            return {"enabled": False, "count": 0}
        with _connection() as conn:
            if not conn:
                return {"enabled": True, "count": 0}
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS n FROM {TABLE_NAME}")
                row = cur.fetchone()
                count = row["n"] if row else 0
        return {"enabled": True, "count": count}
