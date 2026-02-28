"""Judge LLM — reviews the specialist's decision for errors."""

import json

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import LLM_MODEL, JUDGE_TEMPERATURE
from app.prompts.judge import JUDGE_PROMPT
from app.models.schemas import ClassifierOutput, JudgeVerdict


def run_judge(classifier_output: ClassifierOutput, specialist_decision: dict) -> JudgeVerdict:
    """Run the Judge LLM to review the specialist's decision."""

    case_facts = json.dumps({
        "case_category": classifier_output.case_category,
        "flight_type": classifier_output.flight_type,
        "flight_duration_hours": classifier_output.flight_duration_hours,
        "delay_hours": classifier_output.delay_hours,
        "bag_delay_hours": classifier_output.bag_delay_hours,
        "ticket_price": classifier_output.ticket_price,
        "ancillary_fee": classifier_output.ancillary_fee,
        "accepted_alternative": classifier_output.accepted_alternative,
        "passenger_traveled": classifier_output.passenger_traveled,
        "original_class": classifier_output.original_class,
        "downgraded_class": classifier_output.downgraded_class,
        "key_facts": classifier_output.key_facts,
    }, indent=2)

    decision_json = json.dumps(specialist_decision, indent=2, ensure_ascii=False)

    prompt = ChatPromptTemplate.from_messages([
        ("system", JUDGE_PROMPT),
        ("human", "Please review this decision and provide your verdict."),
    ])

    llm = ChatOpenAI(model=LLM_MODEL, temperature=JUDGE_TEMPERATURE)
    chain = prompt | llm | StrOutputParser()
    raw = chain.invoke({"case_facts": case_facts, "decision_json": decision_json})

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {"approved": True, "issues_found": [], "explanation": "Judge failed to parse."}

    return JudgeVerdict(
        approved=data.get("approved", True),
        issues_found=data.get("issues_found", []),
        override_decision=data.get("override_decision", ""),
        override_reasons=data.get("override_reasons", []),
        confidence_adjustment=data.get("confidence_adjustment", ""),
        explanation=data.get("explanation", ""),
    )
