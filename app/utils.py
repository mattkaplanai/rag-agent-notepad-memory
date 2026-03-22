"""Shared utility functions."""

import hashlib
import json

import numpy as np


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    a_arr, b_arr = np.array(a), np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return float(dot / norm) if norm > 0 else 0.0


def hash_inputs(case_type, flight_type, ticket_type, payment_method, accepted_alternative, description):
    """Create a deterministic SHA-256 hash from case inputs."""
    raw = "|".join([s.strip().lower() for s in [case_type, flight_type, ticket_type, payment_method, accepted_alternative, description]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_llm_json(raw: str) -> dict:
    """Strip markdown fences and parse JSON from LLM output.

    Handles three cases:
    1. Bare JSON (no fences)
    2. Output starts with ```json fence
    3. Output contains reasoning text followed by a ```json fence (GPT-4o-mini style)
    """
    cleaned = raw.strip()

    # Look for any ```json ... ``` block anywhere in the output
    if "```" in cleaned:
        import re
        match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", cleaned)
        if match:
            cleaned = match.group(1).strip()

    return json.loads(cleaned)
