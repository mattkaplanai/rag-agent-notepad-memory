"""Classifier agent — extracts structured facts from user input.

Anthropic path: native client.messages.create() with tool_choice forces
the model to populate every field in the schema. Enum constraints on
case_category, flight_type, and alternative_type prevent invalid values.
No JSON parsing — the SDK hands back a validated dict directly.

OpenAI fallback: preserves the existing LangChain + JSON parse path.
"""

import json
import logging
import time

import anthropic

logger = logging.getLogger(__name__)
from app.tracing import get_langfuse_anthropic_client
from app.agents.ansi_colors import C as _C, G as _G, X as _X
from app.agents.retry import invoke_with_retry

from app.config import (
    CLASSIFIER_MODEL,
    CLASSIFIER_TEMPERATURE,
    USE_OPENAI_FOR_AGENTS,
    OPENAI_AGENT_MODEL,
)
from app.prompts.classifier import CLASSIFIER_PROMPT
from app.models.schemas import ClassifierOutput
from app.nlp.sentiment import analyze_sentiment


# Every field maps 1-to-1 with ClassifierOutput.
# Enum constraints prevent invalid values for categorical fields.
# ["type", "null"] allows optional numeric/string fields to be omitted.
_EXTRACT_TOOL = {
    "name": "extract_case_facts",
    "description": (
        "Extract all structured facts from the passenger's refund case. "
        "You MUST call this tool — it is the only way to submit your extraction."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "case_category": {
                "type": "string",
                "enum": ["cancellation", "delay", "downgrade", "baggage", "ancillary", "24hour"],
                "description": "Primary category of the refund case.",
            },
            "flight_type": {
                "type": "string",
                "enum": ["domestic", "international"],
                "description": "domestic if both cities are in the US, international otherwise.",
            },
            "flight_duration_hours": {
                "type": ["number", "null"],
                "description": "Total flight duration in hours, if mentioned. Null if unknown.",
            },
            "delay_hours": {
                "type": ["number", "null"],
                "description": "Flight delay in hours. '5h 45m' = 5.75. Null if not a delay case.",
            },
            "bag_delay_hours": {
                "type": ["number", "null"],
                "description": "Hours between deplaning and bag delivery. Null if not a baggage case.",
            },
            "ticket_price": {
                "type": ["number", "null"],
                "description": "Ticket price in USD. Null if not mentioned.",
            },
            "ancillary_fee": {
                "type": ["number", "null"],
                "description": "Baggage or ancillary fee in USD. Null if not mentioned.",
            },
            "original_class": {
                "type": ["string", "null"],
                "description": "Original cabin class (e.g. Business). Null if not a downgrade case.",
            },
            "downgraded_class": {
                "type": ["string", "null"],
                "description": "Downgraded cabin class. Null if not a downgrade case.",
            },
            "original_class_price": {
                "type": ["number", "null"],
                "description": "Price paid for original class. Null if not mentioned.",
            },
            "downgraded_class_price": {
                "type": ["number", "null"],
                "description": "Price of downgraded class. Null if not mentioned.",
            },
            "payment_method": {
                "type": "string",
                "description": "Payment method used (e.g. Credit Card).",
            },
            "accepted_alternative": {
                "type": "boolean",
                "description": "True if passenger accepted rebooking, voucher, or compensation. False if they declined everything.",
            },
            "alternative_type": {
                "type": "string",
                "enum": ["rebooking", "voucher", "compensation", "none"],
                "description": "Type of alternative accepted or offered. Use 'none' if nothing was accepted.",
            },
            "passenger_traveled": {
                "type": "boolean",
                "description": "True if the passenger actually took the flight.",
            },
            "booking_date": {
                "type": ["string", "null"],
                "description": "Booking date in YYYY-MM-DD format. Null if not mentioned.",
            },
            "flight_date": {
                "type": ["string", "null"],
                "description": "Flight date in YYYY-MM-DD format. Null if not mentioned.",
            },
            "airline_name": {
                "type": ["string", "null"],
                "description": "Name of the airline. Null if not mentioned.",
            },
            "flight_number": {
                "type": ["string", "null"],
                "description": "Flight number (e.g. UA202). Null if not mentioned.",
            },
            "key_facts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Most important facts from the description that affect the refund decision.",
            },
        },
        "required": [
            "case_category",
            "flight_type",
            "flight_duration_hours",
            "delay_hours",
            "bag_delay_hours",
            "ticket_price",
            "ancillary_fee",
            "original_class",
            "downgraded_class",
            "original_class_price",
            "downgraded_class_price",
            "payment_method",
            "accepted_alternative",
            "alternative_type",
            "passenger_traveled",
            "booking_date",
            "flight_date",
            "airline_name",
            "flight_number",
            "key_facts",
        ],
        "additionalProperties": False,
    },
}


def run_classifier(
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> ClassifierOutput:
    """Extract structured facts from user input."""

    user_input = (
        f"Form fields:\n"
        f"  Case Type: {case_type}\n"
        f"  Flight Type: {flight_type}\n"
        f"  Ticket Type: {ticket_type}\n"
        f"  Payment Method: {payment_method}\n"
        f"  Accepted Alternative: {accepted_alternative}\n\n"
        f"Passenger description:\n{description}"
    )

    logger.info(f"{_C}[CLASSIFY] ▶ Extracting structured facts from case description...{_X}")
    t0 = time.time()

    if USE_OPENAI_FOR_AGENTS:
        data = _run_openai_fallback(user_input)
    else:
        data = _run_anthropic(user_input)

    elapsed = time.time() - t0
    frustration_level = analyze_sentiment(description)

    co = ClassifierOutput(
        case_category=data.get("case_category", ""),
        flight_type=data.get("flight_type", ""),
        flight_duration_hours=data.get("flight_duration_hours"),
        delay_hours=data.get("delay_hours"),
        bag_delay_hours=data.get("bag_delay_hours"),
        ticket_price=data.get("ticket_price"),
        ancillary_fee=data.get("ancillary_fee"),
        original_class=data.get("original_class", ""),
        downgraded_class=data.get("downgraded_class", ""),
        original_class_price=data.get("original_class_price"),
        downgraded_class_price=data.get("downgraded_class_price"),
        payment_method=data.get("payment_method", payment_method),
        accepted_alternative=data.get("accepted_alternative", False),
        alternative_type=data.get("alternative_type", "none"),
        passenger_traveled=data.get("passenger_traveled", False),
        booking_date=data.get("booking_date", ""),
        flight_date=data.get("flight_date", ""),
        airline_name=data.get("airline_name", ""),
        flight_number=data.get("flight_number", ""),
        key_facts=data.get("key_facts", []),
        raw_description=description,
        frustration_level=frustration_level,
    )
    logger.info(
        f"{_G}[CLASSIFY] ✓ Done in {elapsed:.1f}s — "
        f"Category: {co.case_category} | Delay: {co.delay_hours}h | "
        f"Price: ${co.ticket_price} | Airline: {co.airline_name} | "
        f"Frustration: {co.frustration_level}{_X}"
    )
    return co


def _run_anthropic(user_input: str) -> dict:
    """Native Anthropic SDK path — tool_use guarantees structured output."""
    client = get_langfuse_anthropic_client()

    response = invoke_with_retry(
        lambda: client.messages.create(
            model=CLASSIFIER_MODEL,
            max_tokens=1024,
            temperature=CLASSIFIER_TEMPERATURE,
            system=CLASSIFIER_PROMPT,
            messages=[{"role": "user", "content": user_input}],
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_case_facts"},
        ),
        label="Classifier",
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block:
        return tool_block.input
    logger.warning("[CLASSIFY] tool_use block missing in response — returning empty extraction")
    return {}


def _run_openai_fallback(user_input: str) -> dict:
    """OpenAI fallback — LangChain + JSON parse path.

    The main CLASSIFIER_PROMPT is written for tool_use. For OpenAI we append
    explicit JSON output instructions so the model knows what to return.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from app.utils import clean_llm_json

    openai_prompt = CLASSIFIER_PROMPT + """

You MUST respond with valid JSON matching this schema:
{{
  "case_category": "cancellation"|"delay"|"downgrade"|"baggage"|"ancillary"|"24hour",
  "flight_type": "domestic"|"international",
  "flight_duration_hours": number or null,
  "delay_hours": number or null,
  "bag_delay_hours": number or null,
  "ticket_price": number or null,
  "ancillary_fee": number or null,
  "original_class": string or null,
  "downgraded_class": string or null,
  "original_class_price": number or null,
  "downgraded_class_price": number or null,
  "payment_method": string,
  "accepted_alternative": true|false,
  "alternative_type": "rebooking"|"voucher"|"compensation"|"none",
  "passenger_traveled": true|false,
  "booking_date": "YYYY-MM-DD" or null,
  "flight_date": "YYYY-MM-DD" or null,
  "airline_name": string or null,
  "flight_number": string or null,
  "key_facts": ["fact 1", ...]
}}
Return ONLY the JSON. No other text."""

    llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=CLASSIFIER_TEMPERATURE)
    prompt = ChatPromptTemplate.from_messages([
        ("system", openai_prompt),
        ("human", "{input}"),
    ])
    chain = prompt | llm | StrOutputParser()

    raw = invoke_with_retry(
        lambda: chain.invoke({"input": user_input}),
        label="Classifier",
    )
    try:
        return clean_llm_json(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def build_case_summary(co: ClassifierOutput) -> str:
    """Convert ClassifierOutput into clean text for downstream agents."""
    lines = [
        f"Case Category: {co.case_category}",
        f"Flight Type: {co.flight_type}",
        f"Payment Method: {co.payment_method}",
        f"Accepted Alternative: {'Yes — ' + co.alternative_type if co.accepted_alternative else 'No'}",
        f"Passenger Traveled: {'Yes' if co.passenger_traveled else 'No'}",
        f"Passenger Frustration Level: {co.frustration_level}",
    ]
    if co.flight_duration_hours is not None:
        lines.append(f"Flight Duration: {co.flight_duration_hours} hours")
    if co.delay_hours is not None:
        lines.append(f"Flight Delay: {co.delay_hours} hours")
    if co.bag_delay_hours is not None:
        lines.append(f"Baggage Delay: {co.bag_delay_hours} hours")
    if co.ticket_price is not None:
        lines.append(f"Ticket Price: ${co.ticket_price}")
    if co.ancillary_fee is not None:
        lines.append(f"Baggage/Ancillary Fee: ${co.ancillary_fee}")
    if co.original_class:
        lines.append(f"Original Class: {co.original_class}")
    if co.downgraded_class:
        lines.append(f"Downgraded To: {co.downgraded_class}")
    if co.original_class_price is not None:
        lines.append(f"Original Class Price: ${co.original_class_price}")
    if co.downgraded_class_price is not None:
        lines.append(f"Downgraded Class Price: ${co.downgraded_class_price}")
    if co.airline_name:
        lines.append(f"Airline: {co.airline_name}")
    if co.flight_number:
        lines.append(f"Flight Number: {co.flight_number}")
    if co.flight_date:
        lines.append(f"Flight Date: {co.flight_date}")
    if co.key_facts:
        lines.append(f"Key Facts: {', '.join(co.key_facts)}")
    lines.append(f"Original Description: {co.raw_description}")
    return "\n".join(lines)
