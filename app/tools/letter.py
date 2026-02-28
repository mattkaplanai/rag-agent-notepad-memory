"""Decision letter generator tool."""

import json
from datetime import datetime
from langchain_core.tools import tool


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
    Use ONLY after the decision is APPROVED or PARTIAL.
    reasons and regulations should be comma-separated lists."""

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
