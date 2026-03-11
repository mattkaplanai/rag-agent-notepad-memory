"""
PostgreSQL store for refund decisions (exact + semantic hit, no vector extension).
Use for durable cache at scale; embeddings stored as JSONB for later semantic match in app.
Optional: if DATABASE_URL / POSTGRES_* are unset, all operations no-op and the app runs without DB.
"""

import json
import os
from contextlib import contextmanager
from typing import List, Optional

# Reuse hash and similarity from cache to stay consistent
from decision_cache import _cosine_similarity, _hash_inputs

TABLE_NAME = "refund_decisions"
SEMANTIC_THRESHOLD_DEFAULT = 0.90


def _get_connection_params():
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
        yield None
        return
    conn = None
    try:
        if "url" in params:
            conn = psycopg2.connect(params["url"], cursor_factory=RealDictCursor)
        else:
            conn = psycopg2.connect(
                host=params["host"],
                port=params["port"],
                user=params["user"],
                password=params["password"],
                dbname=params["dbname"],
                cursor_factory=RealDictCursor,
            )
        yield conn
        if conn:
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[DB] Error: {e}")
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
    """PostgreSQL-backed decision store: exact hit by hash, semantic hit by embedding similarity in app."""

    def __init__(self):
        self._enabled = _get_connection_params() is not None
        if self._enabled:
            with _connection() as conn:
                if conn:
                    _create_table(conn)
                    print("[DB] PostgreSQL connected; table refund_decisions ready.")
        else:
            print("[DB] No POSTGRES_* / DATABASE_URL — DB layer disabled.")

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
        input_hash = _hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        short_hash = input_hash[:12] if input_hash else "?"
        print(f"[LOG] DB lookup by_hash: hash={short_hash}...", flush=True)
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
                    print("[LOG] DB lookup by_hash: hit.", flush=True)
                    return row["result"] if isinstance(row["result"], dict) else json.loads(row["result"])
                print("[LOG] DB lookup by_hash: miss.", flush=True)
                return None

    def get_by_semantic(
        self,
        query_embedding: list[float],
        threshold: float = SEMANTIC_THRESHOLD_DEFAULT,
    ) -> Optional[dict]:
        """Find best matching row by cosine similarity (computed in app). Returns result dict or None."""
        if not self._enabled or not query_embedding:
            return None
        print("[LOG] DB lookup by_semantic: comparing to stored embeddings...", flush=True)
        with _connection() as conn:
            if not conn:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT embedding, result FROM {TABLE_NAME} WHERE embedding IS NOT NULL AND jsonb_array_length(embedding) > 0"
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
            if not isinstance(emb, list):
                continue
            # Skip if embedding dimensions differ (e.g. DB has text-embedding-3-small, query uses text-embedding-3-large)
            if len(emb) != len(query_embedding):
                continue
            sim = _cosine_similarity(query_embedding, emb)
            if sim > best_sim:
                best_sim = sim
                res = row.get("result")
                best_result = res if isinstance(res, dict) else (json.loads(res) if res else None)
        if best_result and best_sim >= threshold:
            print(f"[LOG] DB lookup by_semantic: hit (similarity {best_sim:.3f} ≥ {threshold}).", flush=True)
            return best_result
        print(f"[LOG] DB lookup by_semantic: miss (best_sim={best_sim:.3f}).", flush=True)
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
        """Insert one decision. Embedding stored as JSONB for later semantic hit."""
        if not self._enabled:
            return
        print("[LOG] DB insert: writing 1 row to refund_decisions (PostgreSQL).", flush=True)
        input_hash = _hash_inputs(
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
                    print("[LOG] DB insert: done (1 row added to refund_decisions).", flush=True)
                else:
                    print("[LOG] DB insert: skipped (duplicate input_hash).", flush=True)

    def stats(self) -> dict:
        """Return count of rows (if DB enabled)."""
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

    def list_all(self) -> List[dict]:
        """Return all rows for display: id, input_hash, case_type, flight_type, description_preview, decision, created_at."""
        if not self._enabled:
            return []
        with _connection() as conn:
            if not conn:
                return []
            with conn.cursor() as cur:
                cur.execute(
                    f"""SELECT id, input_hash, case_type, flight_type, ticket_type,
                               payment_method, accepted_alternative, description_preview,
                               result, created_at
                        FROM {TABLE_NAME} ORDER BY id"""
                )
                rows = cur.fetchall()
        out = []
        for row in rows:
            res = row.get("result")
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    res = {}
            decision = (res or {}).get("decision", "?")
            out.append({
                "id": row.get("id"),
                "input_hash": (row.get("input_hash") or "")[:16],
                "case_type": row.get("case_type") or "",
                "flight_type": row.get("flight_type") or "",
                "description_preview": (row.get("description_preview") or "")[:120],
                "decision": decision,
                "created_at": str(row.get("created_at", "")),
            })
        return out
