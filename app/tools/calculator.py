"""Deterministic calculator tools — refund amounts and timelines."""

import json
from datetime import datetime, timedelta
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


@tool
def calculate_refund_timeline(payment_method: str, event_date: str = "") -> str:
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
        rule = "Non-credit-card purchases: refund within 20 calendar days"

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
