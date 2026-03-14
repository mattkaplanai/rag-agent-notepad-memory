"""Past decisions tool — search historical refund decisions from PostgreSQL."""

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def search_past_decisions(case_type: str, decision: str = "") -> str:
    """Search past refund decisions stored in the database by case type and
    optional decision outcome. Use this to check precedents — how similar
    cases were decided before.

    Args:
        case_type: Type of case to search for (e.g., 'Flight Cancellation',
                   'Baggage', 'Delay'). Partial matches work.
        decision: Optional filter by outcome: 'APPROVED', 'DENIED', or
                  'PARTIAL'. Leave empty to see all outcomes.

    Example: search_past_decisions('Flight Cancellation', 'APPROVED')
    """
    try:
        from app.db.decision_db import DecisionDB, _connection
    except ImportError:
        return "Decision database module not available."

    db = DecisionDB()
    if not db.enabled:
        return "Decision database not configured (no POSTGRES_HOST). No past decisions available."

    try:
        from app.db.decision_db import _connection, TABLE_NAME

        with _connection() as conn:
            if not conn:
                return "Could not connect to decision database."
            with conn.cursor() as cur:
                query = (
                    f"SELECT case_type, flight_type, ticket_type, "
                    f"description_preview, result, created_at "
                    f"FROM {TABLE_NAME} WHERE case_type ILIKE %s"
                )
                params = [f"%{case_type.strip()}%"]

                if decision and decision.strip():
                    query += " AND result->>'decision' = %s"
                    params.append(decision.strip().upper())

                query += " ORDER BY created_at DESC LIMIT 5"
                cur.execute(query, params)
                rows = cur.fetchall()

        if not rows:
            return f"No past decisions found for case type '{case_type}'."

        summaries = []
        for i, row in enumerate(rows, 1):
            res = row.get("result", {})
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    res = {}

            reasons = res.get("reasons", [])
            reasons_text = "; ".join(reasons[:2]) if reasons else "N/A"

            summaries.append(
                f"{i}. **{res.get('decision', '?')}** "
                f"(confidence: {res.get('confidence', '?')}) — "
                f"{row.get('case_type', '?')} | {row.get('flight_type', '?')} | "
                f"{row.get('ticket_type', '?')}\n"
                f"   Description: {(row.get('description_preview') or '')[:120]}\n"
                f"   Reasons: {reasons_text}\n"
                f"   Date: {row.get('created_at', '?')}"
            )

        return (
            f"Found {len(rows)} past decision(s) matching '{case_type}'"
            + (f" with outcome '{decision.upper()}'" if decision else "")
            + ":\n\n"
            + "\n\n".join(summaries)
        )

    except Exception as e:
        logger.error("search_past_decisions error: %s", e)
        return f"Error searching past decisions: {e}"
