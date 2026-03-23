"""
Output guard — runs after Judge, before saving to DB and returning response.

- Enforce decision enum (APPROVED | DENIED | PARTIAL | ERROR)
- Required structure (decision key present)
- Citation validation (optional: validate_citations when available)
"""

from dataclasses import dataclass, field

VALID_DECISIONS = frozenset({"APPROVED", "DENIED", "PARTIAL", "ERROR"})


@dataclass
class OutputGuardResult:
    """Result of output guard check."""

    passed: bool = True
    """If False, caller may replace decision with ERROR or a safe fallback."""

    block_reason: str = ""
    """Human-readable reason when passed=False."""

    override_decision: dict | None = None
    """Suggested safe decision dict to return when passed=False (e.g. decision=ERROR)."""

    checks_performed: list[str] = field(default_factory=list)
    """List of check names that were run (for logging/audit)."""


def _safe_override(final_decision: dict, reason: str) -> dict:
    """Build a safe ERROR decision from existing structure."""
    override = dict(final_decision)
    override["decision"] = "ERROR"
    override["confidence"] = "LOW"
    reasons = list(override.get("reasons") or [])
    if reason and reason not in reasons:
        reasons.insert(0, reason)
    override["reasons"] = reasons
    override["output_guard_blocked"] = True
    return override


def _check_decision_enum(final_decision: dict) -> str | None:
    """Returns block reason if decision is invalid, else None."""
    decision = final_decision.get("decision")
    if decision is None:
        return "Output guard: missing 'decision' field."
    if not isinstance(decision, str):
        return "Output guard: 'decision' must be a string."
    if decision.strip().upper() not in VALID_DECISIONS:
        return f"Output guard: 'decision' must be one of {sorted(VALID_DECISIONS)}."
    return None


def _check_citations(final_decision: dict) -> str | None:
    """
    Run citation validator if available.
    Returns block reason when citations are invalid (e.g. not grounded), else None.
    """
    try:
        from app.guards.citation_validator import validate_citations
    except ImportError:
        return None

    regulations = final_decision.get("applicable_regulations") or []
    if not regulations:
        return None

    result = validate_citations(applicable_regulations=regulations)
    if result.is_ok:
        return None
    return f"Output guard: citation validation failed — {result.summary}"


def run_output_guard(final_decision: dict) -> OutputGuardResult:
    """
    Run all output guard checks on the final decision (after Judge).

    Called at: after Judge override applied, before RefundDecision.objects.create()
    and before Response(...).

    Args:
        final_decision: The decision dict that would be returned (includes
                        decision, confidence, reasons, applicable_regulations,
                        refund_details, passenger_action_items, decision_letter, etc.).

    Returns:
        OutputGuardResult. If passed=False, caller may use override_decision
        or build a safe ERROR response instead of returning final_decision as-is.
    """
    if not isinstance(final_decision, dict):
        return OutputGuardResult(
            passed=False,
            block_reason="Output guard: final_decision must be a dict.",
            override_decision={
                "decision": "ERROR",
                "confidence": "LOW",
                "reasons": ["Invalid decision structure."],
                "output_guard_blocked": True,
            },
            checks_performed=["structure", "decision_enum", "citations"],
        )

    checks: list[str] = []

    # 1. Decision enum and presence
    checks.append("decision_enum")
    reason = _check_decision_enum(final_decision)
    if reason:
        return OutputGuardResult(
            passed=False,
            block_reason=reason,
            override_decision=_safe_override(final_decision, reason),
            checks_performed=checks,
        )

    # 2. Citation validation (optional)
    checks.append("citations")
    reason = _check_citations(final_decision)
    if reason:
        return OutputGuardResult(
            passed=False,
            block_reason=reason,
            override_decision=_safe_override(final_decision, reason),
            checks_performed=checks,
        )

    return OutputGuardResult(passed=True, checks_performed=checks)
