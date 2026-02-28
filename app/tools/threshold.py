"""Deterministic threshold checker tools — code, not LLM."""

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


@tool
def check_baggage_threshold(flight_type: str, flight_duration_hours: float, bag_delay_hours: float) -> str:
    """Check if a baggage delay qualifies as 'significantly delayed' under DOT rules.
    You MUST provide the flight duration.
    flight_type: 'domestic' or 'international'.
    flight_duration_hours: total flight duration in hours.
    bag_delay_hours: hours between deplaning and bag delivery."""

    flight_type = flight_type.strip().lower()

    if "domestic" in flight_type:
        threshold = 12.0
        rule = f"Domestic flights: bag must arrive within 12 hours"
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
