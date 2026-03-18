"""Tests for app/utils.py — cosine_similarity, hash_inputs, clean_llm_json."""

import json

import pytest

from app.utils import clean_llm_json, cosine_similarity, hash_inputs


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0

    def test_both_zero_vectors(self):
        assert cosine_similarity([0, 0], [0, 0]) == 0.0

    def test_similar_vectors_high_score(self):
        score = cosine_similarity([1, 1, 0], [1, 1, 0.01])
        assert score > 0.99

    def test_returns_float(self):
        result = cosine_similarity([1, 2, 3], [4, 5, 6])
        assert isinstance(result, float)


class TestHashInputs:
    def test_returns_string(self):
        h = hash_inputs("Flight Cancellation", "Domestic", "Non-refundable", "Credit Card", "No", "desc")
        assert isinstance(h, str)

    def test_deterministic(self):
        args = ("Flight Cancellation", "Domestic", "Non-refundable", "Credit Card", "No", "desc")
        assert hash_inputs(*args) == hash_inputs(*args)

    def test_different_inputs_different_hashes(self):
        h1 = hash_inputs("Flight Cancellation", "Domestic", "Non-refundable", "Credit Card", "No", "desc")
        h2 = hash_inputs("Baggage Lost or Delayed", "Domestic", "Non-refundable", "Credit Card", "No", "desc")
        assert h1 != h2

    def test_case_insensitive(self):
        h1 = hash_inputs("FLIGHT CANCELLATION", "DOMESTIC", "NON-REFUNDABLE", "CREDIT CARD", "NO", "DESC")
        h2 = hash_inputs("flight cancellation", "domestic", "non-refundable", "credit card", "no", "desc")
        assert h1 == h2

    def test_strips_whitespace(self):
        h1 = hash_inputs("Flight Cancellation", "Domestic", "Non-refundable", "Credit Card", "No", "desc")
        h2 = hash_inputs("  Flight Cancellation  ", "  Domestic  ", "Non-refundable", "Credit Card", "No", "desc")
        assert h1 == h2

    def test_sha256_length(self):
        h = hash_inputs("a", "b", "c", "d", "e", "f")
        assert len(h) == 64


class TestCleanLlmJson:
    def test_plain_json(self):
        raw = '{"decision": "APPROVED"}'
        assert clean_llm_json(raw) == {"decision": "APPROVED"}

    def test_strips_markdown_fences(self):
        raw = '```json\n{"decision": "DENIED"}\n```'
        assert clean_llm_json(raw) == {"decision": "DENIED"}

    def test_strips_plain_code_fences(self):
        raw = '```\n{"decision": "PARTIAL"}\n```'
        assert clean_llm_json(raw) == {"decision": "PARTIAL"}

    def test_nested_json(self):
        raw = '{"decision": "APPROVED", "refund_details": {"amount": 450}}'
        result = clean_llm_json(raw)
        assert result["refund_details"]["amount"] == 450

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            clean_llm_json("this is not json")

    def test_empty_string_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            clean_llm_json("")
