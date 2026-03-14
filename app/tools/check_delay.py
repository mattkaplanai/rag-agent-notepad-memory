"""Tool: check if a flight delay is 'significant' under DOT rules."""

import json
from langchain_core.tools import tool


@tool
def check_delay_threshold(flight_type: str, delay_hours: float) -> str:
    """Check if a flight delay qualifies as 'significant' under DOT rules.
    flight_type must be 'domestic' or 'international'.
    delay_hours is how many hours the flight was delayed."""

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
