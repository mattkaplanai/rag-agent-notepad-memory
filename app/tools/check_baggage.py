"""Tool: check if a baggage delay is 'significantly delayed' under DOT rules."""

import json
from langchain_core.tools import tool
from app.config import (
    BAGGAGE_THRESHOLD_DOMESTIC_HOURS,
    BAGGAGE_THRESHOLD_INTL_SHORT_HOURS,
    BAGGAGE_THRESHOLD_INTL_LONG_HOURS,
    BAGGAGE_INTL_FLIGHT_DURATION_CUTOFF,
)


@tool
def check_baggage_threshold(flight_type: str, flight_duration_hours: float, bag_delay_hours: float) -> str:
    """Check if a baggage delay qualifies as 'significantly delayed' under DOT rules.
    You MUST provide the flight duration.
    flight_type: 'domestic' or 'international'.
    flight_duration_hours: total flight duration in hours.
    bag_delay_hours: hours between deplaning and bag delivery."""

    flight_type = flight_type.strip().lower()

    if "domestic" in flight_type:
        threshold = BAGGAGE_THRESHOLD_DOMESTIC_HOURS
        rule = f"Domestic flights: bag must arrive within {threshold} hours"
    elif "international" in flight_type:
        if flight_duration_hours <= BAGGAGE_INTL_FLIGHT_DURATION_CUTOFF:
            threshold = BAGGAGE_THRESHOLD_INTL_SHORT_HOURS
            rule = f"International flight ≤{BAGGAGE_INTL_FLIGHT_DURATION_CUTOFF}h (actual: {flight_duration_hours}h): bag must arrive within {threshold} hours"
        else:
            threshold = BAGGAGE_THRESHOLD_INTL_LONG_HOURS
            rule = f"International flight >{BAGGAGE_INTL_FLIGHT_DURATION_CUTOFF}h (actual: {flight_duration_hours}h): bag must arrive within {threshold} hours"
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
