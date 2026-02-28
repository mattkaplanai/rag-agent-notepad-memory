"""Few-shot examples embedded in prompts to teach the model correct patterns."""

FEW_SHOT_EXAMPLES = """
=== EXAMPLE 1 (APPROVED) ===
INPUT:
  Case Type: Flight Cancellation
  Flight Type: Domestic
  Ticket Type: Non-refundable
  Payment: Credit Card
  Accepted Alternative: No
  Description: My flight from Chicago to Miami on Jan 15 was cancelled by the airline due to a mechanical issue. I was offered a rebooking for the next day but I declined because I had a time-sensitive meeting.

OUTPUT:
{{
  "decision": "APPROVED",
  "confidence": "HIGH",
  "analysis_steps": [
    "Step 1 — Identify the case type: The airline cancelled the flight. This falls under 'Cancelled Flight' per DOT regulations.",
    "Step 2 — Check entitlement rule: Under DOT rules, a consumer is entitled to a refund if the airline cancelled a flight, regardless of the reason, and the consumer chooses not to travel or accept alternatives.",
    "Step 3 — Check if passenger accepted alternatives: The passenger declined the rebooking offer and did not accept any voucher or compensation.",
    "Step 4 — Check ticket type impact: For cancelled flights, even non-refundable ticket holders are entitled to a refund under DOT rules.",
    "Step 5 — Determine refund timeline: Payment was by credit card, so the refund must be issued within 7 business days."
  ],
  "reasons": [
    "The airline cancelled the flight (regardless of reason, this triggers refund entitlement).",
    "The passenger did not accept the rebooking or any alternative compensation.",
    "DOT's Automatic Refund Rule requires airlines to issue refunds automatically for cancelled flights when the passenger chooses not to travel."
  ],
  "applicable_regulations": [
    "DOT Automatic Refund Rule (April 2024) — Cancelled flights entitle passengers to a refund.",
    "14 CFR Part 259 — Airlines must provide automatic refunds without requiring passengers to request them."
  ],
  "refund_details": {{
    "refund_type": "Full refund of ticket price plus all taxes and fees",
    "payment_method": "Original form of payment (credit card)",
    "timeline": "Within 7 business days (credit card purchase)"
  }},
  "passenger_action_items": [
    "No action required — the airline must issue the refund automatically.",
    "If the refund is not received within 7 business days, file a complaint with DOT at https://airconsumer.dot.gov."
  ]
}}

=== EXAMPLE 2 (DENIED) ===
INPUT:
  Case Type: Schedule Change / Significant Delay
  Flight Type: Domestic
  Ticket Type: Non-refundable
  Payment: Credit Card
  Accepted Alternative: Yes — I traveled on the flight anyway
  Description: My flight from New York to Los Angeles was delayed by 1 hour and 30 minutes. I still took the flight but I was unhappy with the delay and want a refund.

OUTPUT:
{{
  "decision": "DENIED",
  "confidence": "HIGH",
  "analysis_steps": [
    "Step 1 — Identify the case type: The flight was delayed by 1 hour 30 minutes. This falls under 'Schedule Change / Significant Delay'.",
    "Step 2 — Check significance threshold: For domestic flights, a 'significant delay' means departure 3+ hours early or arrival 3+ hours late. A 1.5-hour delay does NOT meet the threshold.",
    "Step 3 — Check if passenger traveled: The passenger chose to travel on the delayed flight.",
    "Step 4 — Apply the rule: Even if the delay had been significant, the passenger traveled on the flight and is therefore not entitled to a refund under DOT rules."
  ],
  "reasons": [
    "The 1.5-hour delay does not meet the DOT 'significant delay' threshold of 3+ hours for domestic flights.",
    "The passenger chose to travel on the delayed flight, which waives refund entitlement.",
    "Unsatisfactory service experience alone does not entitle a consumer to a refund."
  ],
  "applicable_regulations": [
    "DOT Automatic Refund Rule — Domestic significant delay threshold is 3+ hours.",
    "DOT Refund Policy — Consumers who chose to travel on a delayed flight are not entitled to a refund."
  ],
  "refund_details": null,
  "passenger_action_items": [
    "You are not entitled to a refund in this situation.",
    "You may check flightrights.gov for airline commitments regarding amenities for delays caused by the airline."
  ]
}}

=== EXAMPLE 3 (DENIED — baggage threshold) ===
INPUT:
  Case Type: Baggage Lost or Delayed
  Flight Type: International
  Ticket Type: Refundable
  Payment: Credit Card
  Accepted Alternative: No
  Description: I flew on a 16-hour flight from Singapore to New York. I paid $100 for checked baggage. My bag was delivered to my hotel 25 hours after I deplaned. I want my baggage fee refunded.

OUTPUT:
{{
  "decision": "DENIED",
  "confidence": "HIGH",
  "analysis_steps": [
    "Step 1 — Identify the case type: The passenger's checked bag was delayed on an international flight. This falls under 'Baggage Lost or Delayed'.",
    "Step 2 — Determine the flight duration: The flight was 16 hours, which is MORE than 12 hours.",
    "Step 3 — Select the correct baggage delay threshold: For international flights MORE than 12 hours in duration, a bag is considered 'significantly delayed' ONLY if it is not delivered within 30 hours after arrival. This is NOT the 15-hour threshold — the 15-hour threshold applies ONLY to international flights of 12 hours or LESS.",
    "Step 4 — Compare delivery time to threshold: The bag was delivered 25 hours after deplaning. 25 hours < 30 hours. The bag was NOT significantly delayed under DOT rules.",
    "Step 5 — Conclusion: Since the bag was delivered within the 30-hour window, the passenger is not entitled to a refund of the baggage fee."
  ],
  "reasons": [
    "The flight was 16 hours (more than 12 hours), so the applicable baggage delay threshold is 30 hours — NOT 15 hours.",
    "The bag was delivered 25 hours after deplaning, which is within the 30-hour threshold.",
    "The bag is NOT considered 'significantly delayed' under DOT regulations."
  ],
  "applicable_regulations": [
    "DOT Baggage Delay Rule — International flights over 12 hours: bag must be delivered within 30 hours to NOT be significantly delayed.",
    "DOT Baggage Delay Rule — The 15-hour threshold applies ONLY to international flights of 12 hours or less in duration."
  ],
  "refund_details": null,
  "passenger_action_items": [
    "You are not entitled to a refund of the baggage fee because the bag was delivered within the 30-hour threshold.",
    "If the bag had been delivered after 30 hours, you would have been entitled to a refund."
  ]
}}
"""
