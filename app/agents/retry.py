"""Exponential backoff retry for LLM/agent invocations."""

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_ATTEMPTS = 3
BASE_DELAY = 2.0  # seconds — actual waits: 2s, 4s, 8s


def _is_retryable(exc: Exception) -> bool:
    """Return True for transient API errors worth retrying."""
    signals = [
        "timeout", "timed out", "rate limit", "rate_limit",
        "overloaded", "529", "503", "502", "connection",
    ]
    return any(s in str(exc).lower() for s in signals)


def invoke_with_retry(fn: Callable[[], T], label: str = "LLM") -> T:
    """
    Call fn() up to MAX_ATTEMPTS times with exponential backoff.

    Retries only on transient errors (timeout, rate limit, overloaded).
    Re-raises immediately on non-retryable errors (auth, bad request, etc.).

    Usage:
        result = invoke_with_retry(
            lambda: agent.invoke({...}),
            label="Researcher",
        )
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            if not _is_retryable(exc) or attempt == MAX_ATTEMPTS:
                raise
            delay = BASE_DELAY ** attempt
            logger.warning(
                "[RETRY] %s — attempt %d/%d failed (%s: %s). Retrying in %.0fs...",
                label, attempt, MAX_ATTEMPTS, type(exc).__name__, exc, delay,
            )
            time.sleep(delay)
