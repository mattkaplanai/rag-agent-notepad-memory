"""Classifier agent — extracts structured facts from user input."""

import json
import logging
import time

logger = logging.getLogger(__name__)
from app.agents.ansi_colors import C as _C, G as _G, X as _X

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import (
    CLASSIFIER_MODEL,
    CLASSIFIER_TEMPERATURE,
    USE_OPENAI_FOR_AGENTS,
    OPENAI_AGENT_MODEL,
)
from app.prompts.classifier import CLASSIFIER_PROMPT
from app.models.schemas import ClassifierOutput


def run_classifier(
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> ClassifierOutput:
    """Run the Classifier LLM to extract structured facts."""

    user_input = (
        f"Form fields:\n"
        f"  Case Type: {case_type}\n"
        f"  Flight Type: {flight_type}\n"
        f"  Ticket Type: {ticket_type}\n"
        f"  Payment Method: {payment_method}\n"
        f"  Accepted Alternative: {accepted_alternative}\n\n"
        f"Passenger description:\n{description}"
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", CLASSIFIER_PROMPT),
        ("human", "{input}"),
    ])

    if USE_OPENAI_FOR_AGENTS:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=CLASSIFIER_TEMPERATURE)
    else:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=CLASSIFIER_MODEL, temperature=CLASSIFIER_TEMPERATURE)
    chain = prompt | llm | StrOutputParser()
    logger.info(f"{_C}[CLASSIFY] ▶ Extracting structured facts from case description...{_X}")
    t0 = time.time()
    raw = chain.invoke({"input": user_input})
    elapsed = time.time() - t0

    from app.utils import clean_llm_json
    try:
        data = clean_llm_json(raw)
    except (json.JSONDecodeError, ValueError):
        data = {}

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
    )
    logger.info(
        f"{_G}[CLASSIFY] ✓ Done in {elapsed:.1f}s — "
        f"Category: {co.case_category} | Delay: {co.delay_hours}h | "
        f"Price: ${co.ticket_price} | Airline: {co.airline_name}{_X}"
    )
    return co


def build_case_summary(co: ClassifierOutput) -> str:
    """Convert ClassifierOutput into clean text for downstream agents."""
    lines = [
        f"Case Category: {co.case_category}",
        f"Flight Type: {co.flight_type}",
        f"Payment Method: {co.payment_method}",
        f"Accepted Alternative: {'Yes — ' + co.alternative_type if co.accepted_alternative else 'No'}",
        f"Passenger Traveled: {'Yes' if co.passenger_traveled else 'No'}",
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
