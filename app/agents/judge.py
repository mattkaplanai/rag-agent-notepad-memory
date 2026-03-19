"""Judge — reviews the specialist's decision via native Anthropic tool_use.

Uses client.messages.create() with tool_choice={"type": "tool", "name": "submit_verdict"}
so the model is forced to call the tool and fill every required field.
No JSON parsing, no fragile string extraction — the SDK validates the schema.
"""

import json
import logging
import time

import anthropic

logger = logging.getLogger(__name__)
from app.tracing import get_langfuse_anthropic_client
from app.agents.ansi_colors import C as _C, G as _G, Y as _Y, X as _X
from app.agents.retry import invoke_with_retry

from app.config import LLM_MODEL, JUDGE_TEMPERATURE, USE_OPENAI_FOR_AGENTS, OPENAI_AGENT_MODEL
from app.prompts.judge import JUDGE_PROMPT
from app.models.schemas import ClassifierOutput, JudgeVerdict


# Tool schema — enum constraints make override_decision impossible to leave empty
# when approved=false (validated by the model against the schema).
_VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": (
        "Submit your structured review verdict for the refund decision. "
        "You MUST call this tool — it is the only way to submit your review."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "approved": {
                "type": "boolean",
                "description": (
                    "True if the decision is correct and should stand. "
                    "False if it must be overridden."
                ),
            },
            "issues_found": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific issues found. Empty list if approved=true.",
            },
            "override_decision": {
                "type": "string",
                "enum": ["APPROVED", "DENIED", "PARTIAL", ""],
                "description": (
                    "The correct decision when approved=false. "
                    "Must be APPROVED, DENIED, or PARTIAL. "
                    "Only leave empty when approved=true."
                ),
            },
            "override_reasons": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Reasons for the override. Empty list if approved=true.",
            },
            "confidence_adjustment": {
                "type": "string",
                "enum": ["", "raise to HIGH", "lower to MEDIUM", "lower to LOW"],
                "description": "Whether to adjust the confidence level of the decision.",
            },
            "explanation": {
                "type": "string",
                "description": "One or two sentences summarising your review finding.",
            },
        },
        "required": [
            "approved",
            "issues_found",
            "override_decision",
            "override_reasons",
            "confidence_adjustment",
            "explanation",
        ],
        "additionalProperties": False,
    },
}


def run_judge(classifier_output: ClassifierOutput, specialist_decision: dict) -> JudgeVerdict:
    """Review the specialist's decision.

    Anthropic path: native client.messages.create() + tool_choice forces a
    structured tool_use block — no JSON parsing needed.

    OpenAI fallback: preserves the existing LangChain path.
    """
    case_facts = json.dumps(
        {
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
        },
        indent=2,
    )
    decision_json = json.dumps(specialist_decision, indent=2, ensure_ascii=False)

    logger.info(f"{_C}[JUDGE   ] ▶ Reviewing specialist decision...{_X}")
    t0 = time.time()

    if USE_OPENAI_FOR_AGENTS:
        data = _run_openai_fallback(case_facts, decision_json)
    else:
        data = _run_anthropic(case_facts, decision_json)

    elapsed = time.time() - t0
    approved = data.get("approved", True)
    explanation = data.get("explanation", "")[:80]

    if approved:
        logger.info(f"{_G}[JUDGE   ] ✓ APPROVED decision in {elapsed:.1f}s — {explanation}{_X}")
    else:
        override = data.get("override_decision", "?")
        logger.info(f"{_Y}[JUDGE   ] ✗ OVERRIDING → {override} in {elapsed:.1f}s — {explanation}{_X}")

    return JudgeVerdict(
        approved=approved,
        issues_found=data.get("issues_found", []),
        override_decision=data.get("override_decision", ""),
        override_reasons=data.get("override_reasons", []),
        confidence_adjustment=data.get("confidence_adjustment", ""),
        explanation=data.get("explanation", ""),
    )


def _run_anthropic(case_facts: str, decision_json: str) -> dict:
    """Native Anthropic SDK path — tool_use guarantees structured output."""
    system_prompt = JUDGE_PROMPT.format(case_facts=case_facts, decision_json=decision_json)
    client = get_langfuse_anthropic_client()

    response = invoke_with_retry(
        lambda: client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            temperature=JUDGE_TEMPERATURE,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Review this decision and submit your verdict using the submit_verdict tool.",
                }
            ],
            tools=[_VERDICT_TOOL],
            tool_choice={"type": "tool", "name": "submit_verdict"},
        ),
        label="Judge",
    )

    tool_block = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_block:
        return tool_block.input
    logger.warning("[JUDGE   ] tool_use block missing in response — defaulting to approved")
    return {"approved": True, "issues_found": [], "explanation": "Judge tool_use block not found."}


def _run_openai_fallback(case_facts: str, decision_json: str) -> dict:
    """OpenAI fallback — preserves existing LangChain + JSON parse path."""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from app.utils import clean_llm_json

    # OpenAI path: append a mechanical decision table so GPT-4o-mini doesn't
    # have to reason through the logic — it just matches the case to a row.
    openai_prompt = JUDGE_PROMPT + """

DECISION TABLE — use this to determine the correct decision before checking the Writer's output:
| accepted_alternative | delay/cancellation qualifies | correct_decision |
|---|---|---|
| false | YES (delay >= threshold OR cancellation with no alternative) | APPROVED |
| false | NO (delay below threshold, or ambiguous) | DENIED |
| true  | any | DENIED |

Steps:
1. Look up accepted_alternative and whether the case qualifies in the table above.
2. Compare correct_decision to the Writer's decision.
3. If they match → approved=true, override_decision="".
4. If they differ → approved=false, override_decision=<correct_decision from table>.

Return JSON with keys: approved, issues_found, override_decision, override_reasons, confidence_adjustment, explanation."""

    llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=JUDGE_TEMPERATURE)
    prompt = ChatPromptTemplate.from_messages([
        ("system", openai_prompt),
        ("human", "Please review this decision and provide your verdict."),
    ])
    chain = prompt | llm | StrOutputParser()

    raw = invoke_with_retry(
        lambda: chain.invoke({"case_facts": case_facts, "decision_json": decision_json}),
        label="Judge",
    )
    try:
        return clean_llm_json(raw)
    except (json.JSONDecodeError, ValueError):
        return {"approved": True, "issues_found": [], "explanation": "Judge JSON parse failed."}
