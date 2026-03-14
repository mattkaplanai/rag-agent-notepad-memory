"""Tool: calculate refund amounts (full refund or fare difference)."""

import json
from langchain_core.tools import tool


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
    For full refunds: provide ticket_price, taxes_and_fees, ancillary_fees, used_segments_value.
    For downgrade refunds: also provide downgrade fields."""

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
