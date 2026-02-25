"""
Decision Cache: Two-level caching to minimize LLM costs.

Level 1 — Exact match:  Hash all form inputs. If identical case was seen
                         before, return the cached decision instantly ($0).

Level 2 — Semantic match: Embed the description text and compare cosine
                          similarity to cached descriptions. If similarity
                          exceeds the threshold, reuse the cached decision
                          (costs only 1 embedding call instead of full LLM).

Cache is persisted to disk as JSON so it survives restarts.
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_FILE = PROJECT_ROOT / "decision_cache.json"

SEMANTIC_THRESHOLD = 0.90


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def _hash_inputs(
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> str:
    raw = "|".join([
        case_type.strip().lower(),
        flight_type.strip().lower(),
        ticket_type.strip().lower(),
        payment_method.strip().lower(),
        accepted_alternative.strip().lower(),
        description.strip().lower(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_embedding(text: str) -> list[float]:
    from openai import OpenAI
    client = OpenAI()
    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
    )
    return response.data[0].embedding


class DecisionCache:
    """Two-level cache: exact hash match → semantic similarity → LLM."""

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.cache_path = cache_path
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self.entries = data if isinstance(data, list) else []
                print(f"[CACHE] Loaded {len(self.entries)} cached decisions.")
            except Exception:
                self.entries = []
        else:
            self.entries = []

    def _save(self):
        self.cache_path.write_text(
            json.dumps(self.entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def lookup(
        self,
        case_type: str,
        flight_type: str,
        ticket_type: str,
        payment_method: str,
        accepted_alternative: str,
        description: str,
    ) -> tuple[Optional[dict], str]:
        """
        Look up a cached decision.

        Returns:
            (result_dict, cache_status)
            cache_status is one of: "exact_hit", "semantic_hit", "miss"
        """
        input_hash = _hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        # Level 1: exact match
        for entry in self.entries:
            if entry.get("hash") == input_hash:
                print(f"[CACHE] ✅ Exact hit — returning cached decision (saved full LLM call)")
                return entry["result"], "exact_hit"

        # Level 2: semantic similarity on description
        if not description.strip():
            return None, "miss"

        query_embedding = _get_embedding(description)

        best_sim = 0.0
        best_entry = None
        for entry in self.entries:
            emb = entry.get("embedding")
            if not emb:
                continue
            sim = _cosine_similarity(query_embedding, emb)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry and best_sim >= SEMANTIC_THRESHOLD:
            print(f"[CACHE] 🔍 Semantic hit — similarity {best_sim:.3f} ≥ {SEMANTIC_THRESHOLD} (saved LLM call)")
            return best_entry["result"], "semantic_hit"

        print(f"[CACHE] ❌ Miss — best similarity {best_sim:.3f} < {SEMANTIC_THRESHOLD}")
        return None, "miss"

    def store(
        self,
        case_type: str,
        flight_type: str,
        ticket_type: str,
        payment_method: str,
        accepted_alternative: str,
        description: str,
        result: dict,
    ):
        """Store a new decision in the cache."""
        input_hash = _hash_inputs(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        embedding = _get_embedding(description) if description.strip() else []

        entry = {
            "hash": input_hash,
            "case_type": case_type,
            "flight_type": flight_type,
            "ticket_type": ticket_type,
            "description_preview": description[:100],
            "embedding": embedding,
            "result": result,
            "timestamp": time.time(),
        }
        self.entries.append(entry)
        self._save()
        print(f"[CACHE] 💾 Stored decision — cache now has {len(self.entries)} entries.")

    @property
    def stats(self) -> dict:
        return {
            "total_entries": len(self.entries),
            "cache_file": str(self.cache_path),
        }

    def clear(self):
        self.entries = []
        self._save()
        print("[CACHE] 🗑️ Cache cleared.")
