"""Tool: calculate refund deadline dates."""

import json
from datetime import datetime, timedelta
from langchain_core.tools import tool


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
