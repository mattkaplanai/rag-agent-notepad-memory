"""
Refund Decision Tools: Deterministic tools the agent can call.

Step 3 of the learning roadmap: Multi-Tool Agent.

These tools use CODE (not LLM reasoning) for math and rule lookups,
so they always produce correct results. The agent decides WHICH tools
to call and WHEN, but the tools do the actual computation.
"""

import json
from datetime import datetime, timedelta
from langchain_core.tools import tool


# ── Tool 1: Threshold Checker ────────────────────────────────────────────────

@tool
def check_delay_threshold(
    flight_type: str,
    delay_hours: float,
) -> str:
    """Check if a flight delay qualifies as 'significant' under DOT rules.
    Use this whenever a passenger reports a schedule change or delay.
    flight_type must be 'domestic' or 'international'.
    delay_hours is how many hours the flight was delayed (departure or arrival)."""

    flight_type = flight_type.strip().lower()

    if "domestic" in flight_type:
        threshold = 3.0
        rule = "Domestic flights: 3+ hours = significant delay"
    elif "international" in flight_type:
        threshold = 6.0
        rule = "International flights: 6+ hours = significant delay"
    else:
        return json.dumps({"error": f"Unknown flight type: {flight_type}. Use 'domestic' or 'international'."})

    is_significant = delay_hours >= threshold

    return json.dumps({
        "is_significant_delay": is_significant,
        "threshold_hours": threshold,
        "actual_delay_hours": delay_hours,
        "flight_type": flight_type,
        "rule": rule,
        "explanation": (
            f"The delay of {delay_hours} hours {'MEETS' if is_significant else 'does NOT meet'} "
            f"the {threshold}-hour threshold for {flight_type} flights. "
            f"{'The passenger IS entitled to a refund (if they did not accept alternatives).' if is_significant else 'The delay is NOT considered significant — no refund entitlement based on delay alone.'}"
        ),
    })


@tool
def check_baggage_threshold(
    flight_type: str,
    flight_duration_hours: float,
    bag_delay_hours: float,
) -> str:
    """Check if a baggage delay qualifies as 'significantly delayed' under DOT rules.
    Use this for any baggage delay case. You MUST provide the flight duration.
    flight_type: 'domestic' or 'international'.
    flight_duration_hours: total flight duration in hours.
    bag_delay_hours: hours between deplaning and bag delivery."""

    flight_type = flight_type.strip().lower()

    if "domestic" in flight_type:
        threshold = 12.0
        rule = "Domestic flights: bag must arrive within 12 hours"
    elif "international" in flight_type:
        if flight_duration_hours <= 12:
            threshold = 15.0
            rule = f"International flight ≤12 hours (actual: {flight_duration_hours}h): bag must arrive within 15 hours"
        else:
            threshold = 30.0
            rule = f"International flight >12 hours (actual: {flight_duration_hours}h): bag must arrive within 30 hours"
    else:
        return json.dumps({"error": f"Unknown flight type: {flight_type}. Use 'domestic' or 'international'."})

    is_significantly_delayed = bag_delay_hours > threshold

    return json.dumps({
        "is_significantly_delayed": is_significantly_delayed,
        "threshold_hours": threshold,
        "actual_delay_hours": bag_delay_hours,
        "flight_type": flight_type,
        "flight_duration_hours": flight_duration_hours,
        "rule": rule,
        "explanation": (
            f"Bag was delivered {bag_delay_hours} hours after deplaning. "
            f"The threshold for this flight is {threshold} hours. "
            f"{bag_delay_hours} {'>' if is_significantly_delayed else '<='} {threshold}. "
            f"{'The bag IS significantly delayed — passenger IS entitled to a baggage fee refund.' if is_significantly_delayed else 'The bag is NOT significantly delayed — passenger is NOT entitled to a baggage fee refund.'}"
        ),
    })


# ── Tool 2: Refund Calculator ────────────────────────────────────────────────

@tool
def calculate_refund(
    ticket_price: float,
    taxes_and_fees: float = 0.0,
    ancillary_fees: float = 0.0,
    used_segments_value: float = 0.0,
    downgrade_from_class: str = "",
    downgrade_to_class: str = "",
    downgrade_original_price: float = 0.0,
    downgrade_lower_price: float = 0.0,
) -> str:
    """Calculate the refund amount for a passenger.
    For full refunds: provide ticket_price, taxes_and_fees, ancillary_fees, and used_segments_value.
    For downgrade refunds: also provide downgrade fields (original and lower class prices).
    The tool subtracts the value of any used segments automatically."""

    if downgrade_from_class and downgrade_to_class:
        fare_difference = downgrade_original_price - downgrade_lower_price
        return json.dumps({
            "refund_type": "fare_difference",
            "refund_amount": round(max(fare_difference, 0), 2),
            "downgrade_from": downgrade_from_class,
            "downgrade_to": downgrade_to_class,
            "original_fare": downgrade_original_price,
            "lower_fare": downgrade_lower_price,
            "explanation": (
                f"Downgrade from {downgrade_from_class} (${downgrade_original_price:,.2f}) "
                f"to {downgrade_to_class} (${downgrade_lower_price:,.2f}). "
                f"Fare difference refund: ${fare_difference:,.2f}."
            ),
        })

    total_paid = ticket_price + taxes_and_fees + ancillary_fees
    refund_amount = total_paid - used_segments_value

    return json.dumps({
        "refund_type": "full_refund",
        "refund_amount": round(max(refund_amount, 0), 2),
        "ticket_price": ticket_price,
        "taxes_and_fees": taxes_and_fees,
        "ancillary_fees": ancillary_fees,
        "used_segments_value": used_segments_value,
        "total_paid": round(total_paid, 2),
        "explanation": (
            f"Total paid: ${total_paid:,.2f} (ticket ${ticket_price:,.2f} + "
            f"taxes/fees ${taxes_and_fees:,.2f} + ancillary ${ancillary_fees:,.2f}). "
            f"Used segments value: ${used_segments_value:,.2f}. "
            f"Refund amount: ${refund_amount:,.2f}."
        ),
    })


# ── Tool 3: Timeline Calculator ──────────────────────────────────────────────

@tool
def calculate_refund_timeline(
    payment_method: str,
    event_date: str = "",
) -> str:
    """Calculate the deadline for when the airline must issue the refund.
    payment_method: 'credit_card', 'debit_card', 'cash', 'check', or 'other'.
    event_date: the date the refund became due (e.g., '2026-03-10'). Optional."""

    pm = payment_method.strip().lower().replace(" ", "_")

    if "credit" in pm:
        calendar_days = None
        business_days = 7
        rule = "Credit card purchases: refund within 7 business days"
    else:
        calendar_days = 20
        business_days = None
        rule = "Non-credit-card purchases (cash, check, debit, other): refund within 20 calendar days"

    result = {
        "payment_method": payment_method,
        "business_days": business_days,
        "calendar_days": calendar_days,
        "rule": rule,
    }

    if event_date:
        try:
            start = datetime.strptime(event_date, "%Y-%m-%d")
            if business_days:
                deadline = start
                days_added = 0
                while days_added < business_days:
                    deadline += timedelta(days=1)
                    if deadline.weekday() < 5:
                        days_added += 1
                result["event_date"] = event_date
                result["deadline_date"] = deadline.strftime("%Y-%m-%d")
                result["explanation"] = (
                    f"Refund due by {deadline.strftime('%B %d, %Y')} "
                    f"({business_days} business days after {event_date})."
                )
            else:
                deadline = start + timedelta(days=calendar_days)
                result["event_date"] = event_date
                result["deadline_date"] = deadline.strftime("%Y-%m-%d")
                result["explanation"] = (
                    f"Refund due by {deadline.strftime('%B %d, %Y')} "
                    f"({calendar_days} calendar days after {event_date})."
                )
        except ValueError:
            result["explanation"] = (
                f"Could not parse date '{event_date}'. "
                f"Refund must be issued within {business_days or calendar_days} "
                f"{'business' if business_days else 'calendar'} days."
            )
    else:
        result["explanation"] = (
            f"Refund must be issued within {business_days or calendar_days} "
            f"{'business' if business_days else 'calendar'} days after the refund becomes due."
        )

    return json.dumps(result)


# ── Tool 4: Decision Letter Generator ────────────────────────────────────────

@tool
def generate_decision_letter(
    passenger_name: str,
    airline_name: str,
    flight_number: str,
    flight_date: str,
    decision: str,
    refund_amount: str,
    reasons: str,
    regulations: str,
) -> str:
    """Generate a formal refund request letter the passenger can send to the airline.
    Use this ONLY after the decision is APPROVED or PARTIAL.
    All parameters are strings. reasons and regulations should be comma-separated lists."""

    today = datetime.now().strftime("%B %d, %Y")

    letter = f"""
FORMAL REFUND REQUEST

Date: {today}
From: {passenger_name}
To: {airline_name} — Customer Relations

RE: Refund Request for Flight {flight_number} on {flight_date}

Dear {airline_name} Customer Relations,

I am writing to formally request a refund in the amount of {refund_amount} for my flight {flight_number} scheduled for {flight_date}.

Under the U.S. Department of Transportation's regulations, I am entitled to this refund for the following reasons:

{chr(10).join(f"  • {r.strip()}" for r in reasons.split(","))}

This request is supported by the following DOT regulations:

{chr(10).join(f"  • {r.strip()}" for r in regulations.split(","))}

Per DOT regulations, this refund must be issued automatically and promptly in the original form of payment. I expect to receive confirmation of this refund within the timeframe mandated by federal regulations.

If I do not receive this refund within the required timeframe, I will file a formal complaint with the U.S. Department of Transportation at https://airconsumer.dot.gov.

Sincerely,
{passenger_name}
"""

    return json.dumps({
        "letter": letter.strip(),
        "explanation": f"Formal refund request letter generated for {passenger_name} regarding {airline_name} flight {flight_number}.",
    })


# ── Tool 5: Search Documents (RAG) ──────────────────────────────────────────

def make_search_tool(index):
    """Create a document search tool bound to the given index."""

    @tool
    def search_regulations(query: str) -> str:
        """Search DOT regulations and documents for information relevant to the query.
        Use this to look up specific rules, thresholds, or policies.
        Always search before making a decision — do not rely on memory alone."""
        if index is None:
            return "No document index available."
        from advanced_rag import hybrid_search
        result = hybrid_search(index, query, top_k=8)
        if not result.chunks:
            return "No relevant regulations found for this query."
        chunks_text = "\n\n---\n\n".join(
            f"[Source: {c.source_file} | Relevance: {c.rerank_score:.3f}]\n{c.content}"
            for c in result.chunks
        )
        return chunks_text

    return search_regulations


def get_all_tools(index):
    """Return all tools for the refund decision agent."""
    return [
        check_delay_threshold,
        check_baggage_threshold,
        calculate_refund,
        calculate_refund_timeline,
        generate_decision_letter,
        make_search_tool(index),
    ]
