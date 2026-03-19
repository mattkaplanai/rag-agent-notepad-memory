"""Shared pytest fixtures."""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_case_data():
    """Valid flight cancellation case."""
    return {
        "case_type": "Flight Cancellation",
        "flight_type": "Domestic (within US)",
        "ticket_type": "Non-refundable",
        "payment_method": "Credit Card",
        "accepted_alternative": "No",
        "description": "The airline cancelled my flight 2 days before departure. I did not accept rebooking.",
    }


@pytest.fixture
def tmp_cache_file():
    """Temporary JSON file for cache tests (no real filesystem side effects)."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"[]")
        yield Path(f.name)
