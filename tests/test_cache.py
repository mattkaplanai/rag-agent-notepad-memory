"""Tests for DecisionCache — exact hash lookup, store, stats, clear.

OpenAI embeddings are mocked so these tests run without any API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.cache.decision_cache import DecisionCache


SAMPLE_RESULT = {
    "decision": "APPROVED",
    "confidence": "HIGH",
    "reasons": ["DOT requires refund"],
    "applicable_regulations": ["14 CFR 259.5"],
    "refund_details": {"refund_amount": "$450.00"},
    "passenger_action_items": [],
    "analysis_steps": [],
    "decision_letter": None,
}

CASE_ARGS = (
    "Flight Cancellation",
    "Domestic (within US)",
    "Non-refundable",
    "Credit Card",
    "No",
    "The airline cancelled my flight. I want a full refund.",
)

FAKE_EMBEDDING = [0.1] * 1536  # 1536-dim zero-ish vector


class TestDecisionCacheExactHit:
    def test_empty_cache_is_miss(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        result, status, _ = cache.lookup(*CASE_ARGS)
        assert result is None
        assert status == "miss"

    def test_store_then_exact_hit(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)
        result, status, _ = cache.lookup(*CASE_ARGS)
        assert result is not None
        assert status == "exact_hit"

    def test_stored_result_matches(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)
        result, _, _ = cache.lookup(*CASE_ARGS)
        assert result["decision"] == "APPROVED"

    def test_different_case_is_miss(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)

        different_args = (
            "Baggage Lost or Delayed",  # different case_type
            "Domestic (within US)",
            "Non-refundable",
            "Credit Card",
            "No",
            "My bag was delayed 15 hours.",
        )
        result, status, _ = cache.lookup(*different_args)
        assert result is None
        assert status == "miss"

    def test_hash_is_case_insensitive(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)

        upper_args = tuple(a.upper() if isinstance(a, str) else a for a in CASE_ARGS)
        result, status, _ = cache.lookup(*upper_args)
        assert status == "exact_hit"


class TestDecisionCacheStats:
    def test_empty_cache_stats(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        assert cache.stats["total_entries"] == 0

    def test_stats_after_store(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)
        assert cache.stats["total_entries"] == 1

    def test_stats_increments_per_store(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        for i in range(3):
            args = list(CASE_ARGS)
            args[5] = f"Unique description {i}"
            cache.store(*args, SAMPLE_RESULT)
        assert cache.stats["total_entries"] == 3


class TestDecisionCacheClear:
    def test_clear_removes_entries(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)
        cache.clear()
        assert cache.stats["total_entries"] == 0

    def test_clear_then_miss(self, tmp_cache_file):
        cache = DecisionCache(cache_path=tmp_cache_file)
        cache.store(*CASE_ARGS, SAMPLE_RESULT)
        cache.clear()
        result, status, _ = cache.lookup(*CASE_ARGS)
        assert result is None
        assert status == "miss"


class TestDecisionCacheSemanticHit:
    """Semantic lookup requires OpenAI — mock the embedding call."""

    def test_semantic_hit_with_similar_embedding(self, tmp_cache_file):
        with patch("app.cache.decision_cache._get_embedding", return_value=FAKE_EMBEDDING):
            cache = DecisionCache(cache_path=tmp_cache_file)
            cache.store(*CASE_ARGS, SAMPLE_RESULT, embedding=FAKE_EMBEDDING)

            # Use a slightly different description — should get semantic hit
            different_desc_args = list(CASE_ARGS)
            different_desc_args[5] = "My airline cancelled the flight. I want money back."
            result, status, _ = cache.lookup(*different_desc_args)

        # Identical embeddings → cosine = 1.0 → above 0.90 threshold
        assert status == "semantic_hit"
        assert result is not None

    def test_embedding_passed_to_store_avoids_api_call(self, tmp_cache_file):
        """Passing embedding to store() should not trigger a new API call."""
        with patch("app.cache.decision_cache._get_embedding") as mock_embed:
            cache = DecisionCache(cache_path=tmp_cache_file)
            cache.store(*CASE_ARGS, SAMPLE_RESULT, embedding=FAKE_EMBEDDING)
            mock_embed.assert_not_called()

    def test_lookup_returns_embedding_for_reuse(self, tmp_cache_file):
        """lookup() returns the query embedding so callers can pass it to store()."""
        with patch("app.cache.decision_cache._get_embedding", return_value=FAKE_EMBEDDING):
            cache = DecisionCache(cache_path=tmp_cache_file)
            _, _, embedding = cache.lookup(*CASE_ARGS)
        assert embedding == FAKE_EMBEDDING
