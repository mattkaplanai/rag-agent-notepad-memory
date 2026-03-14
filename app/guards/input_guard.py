"""
Input guard — runs at pipeline entry, after API/serializer validation, before Classifier.

- Prompt injection / jailbreak detection (simple phrase blocklist)
- Topic scope check (refund/airline related keywords)
- Simple PII detection (card-number-like digit sequences → block)
"""

import re
from dataclasses import dataclass, field

# Phrases that suggest prompt injection / jailbreak (case-insensitive)
PROMPT_INJECTION_PHRASES = [
    "ignore previous",
    "ignore all previous",
    "disregard your instructions",
    "forget your instructions",
    "you are now",
    "always approve",
    "always return approved",
    "override your",
    "new instructions:",
    "system prompt:",
    "pretend you are",
    "act as if",
]

# At least one of these must appear in description for topic scope (refund/airline)
TOPIC_KEYWORDS = [
    "flight", "delay", "cancel", "refund", "baggage", "airline", "ticket",
    "uçuş", "iptal", "gecikme", "bavul", "iade", "havayolu", "ucus",
]

# Pattern: 13-19 digits, optional spaces or dashes between (card number / ID)
PII_CARD_PATTERN = re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b|\b\d{13,19}\b")


@dataclass
class InputGuardResult:
    """Result of input guard check."""

    passed: bool = True
    """If False, pipeline should not run; return block_response to user."""

    block_reason: str = ""
    """Human-readable reason when passed=False."""

    block_response: dict | None = None
    """Suggested API response body when blocked (e.g. decision=ERROR, reasons=[...])."""

    sanitized_data: dict | None = None
    """If guard modifies input (e.g. PII masking), validated_data with changes. Else None."""

    checks_performed: list[str] = field(default_factory=list)
    """List of check names that were run (for logging/audit)."""


def _build_block_response(reason: str) -> dict:
    """Standard error-shaped response when input guard blocks."""
    return {
        "decision": "ERROR",
        "confidence": "LOW",
        "reasons": [reason],
        "analysis_steps": ["Input guard blocked this request."],
        "applicable_regulations": [],
        "refund_details": None,
        "passenger_action_items": ["Please correct your request and try again."],
    }


def _check_prompt_injection(text: str) -> str | None:
    """Returns block reason if injection detected, else None."""
    if not text:
        return None
    lower = text.lower()
    for phrase in PROMPT_INJECTION_PHRASES:
        if phrase in lower:
            return f"Request rejected: input contains disallowed instruction-like text."
    return None


def _check_topic_scope(description: str) -> str | None:
    """Returns block reason if description is off-topic, else None."""
    if not description or not description.strip():
        return None
    lower = description.lower()
    if any(kw in lower for kw in TOPIC_KEYWORDS):
        return None
    return "Request rejected: description must be about a flight, refund, delay, cancellation, or baggage issue."


def _check_pii(text: str) -> str | None:
    """Returns block reason if card-number-like sequence found, else None."""
    if not text:
        return None
    if PII_CARD_PATTERN.search(text):
        return "Request rejected: do not include credit card or similar numbers in the description."
    return None


def run_input_guard(validated_data: dict) -> InputGuardResult:
    """
    Run all input guard checks on the validated request data.

    Called at: after RefundRequestSerializer.is_valid(), before run_classifier().

    Args:
        validated_data: serializer.validated_data (case_type, flight_type, ...,
                       ticket_type, payment_method, accepted_alternative, description).

    Returns:
        InputGuardResult. If passed=False, caller should return block_response
        and not invoke Classifier / multi-agent / Judge.
    """
    checks: list[str] = []
    description = (validated_data.get("description") or "").strip()
    # Build full text for injection check (all string fields)
    full_text_parts = [str(validated_data.get(k, "")) for k in validated_data if isinstance(validated_data.get(k), str)]
    full_text = " ".join(full_text_parts)

    # 1. Prompt injection
    checks.append("prompt_injection")
    reason = _check_prompt_injection(full_text)
    if reason:
        return InputGuardResult(
            passed=False,
            block_reason=reason,
            block_response=_build_block_response(reason),
            checks_performed=checks,
        )

    # 2. Topic scope
    checks.append("topic_scope")
    reason = _check_topic_scope(description)
    if reason:
        return InputGuardResult(
            passed=False,
            block_reason=reason,
            block_response=_build_block_response(reason),
            checks_performed=checks,
        )

    # 3. PII (card-like numbers)
    checks.append("pii_card_like")
    reason = _check_pii(description)
    if reason:
        return InputGuardResult(
            passed=False,
            block_reason=reason,
            block_response=_build_block_response(reason),
            checks_performed=checks,
        )

    return InputGuardResult(passed=True, checks_performed=checks)
