"""
LLM-to-LLM Pipeline: Classifier → Specialist → Judge

Step 4 of the learning roadmap.

Demonstrates:
  - LLM Chaining: output of one LLM becomes input to the next
  - Separation of Concerns: each LLM has one focused job
  - LLM-as-Judge: one LLM evaluates another's work
  - Self-correction: the system catches and fixes its own mistakes
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Add it to .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ClassifierOutput:
    case_category: str = ""
    flight_type: str = ""
    flight_duration_hours: float | None = None
    delay_hours: float | None = None
    bag_delay_hours: float | None = None
    ticket_price: float | None = None
    ancillary_fee: float | None = None
    original_class: str = ""
    downgraded_class: str = ""
    original_class_price: float | None = None
    downgraded_class_price: float | None = None
    payment_method: str = ""
    accepted_alternative: bool = False
    alternative_type: str = ""
    passenger_traveled: bool = False
    booking_date: str = ""
    flight_date: str = ""
    airline_name: str = ""
    flight_number: str = ""
    key_facts: list[str] = field(default_factory=list)
    raw_description: str = ""


@dataclass
class JudgeVerdict:
    approved: bool = True
    issues_found: list[str] = field(default_factory=list)
    corrections: dict = field(default_factory=dict)
    override_decision: str = ""
    override_reasons: list[str] = field(default_factory=list)
    confidence_adjustment: str = ""
    explanation: str = ""


@dataclass
class PipelineResult:
    classifier_output: ClassifierOutput = field(default_factory=ClassifierOutput)
    specialist_decision: dict = field(default_factory=dict)
    judge_verdict: JudgeVerdict = field(default_factory=JudgeVerdict)
    final_decision: dict = field(default_factory=dict)
    pipeline_log: list[str] = field(default_factory=list)


# ── LLM 1: CLASSIFIER ───────────────────────────────────────────────────────
#
# Job: Read messy user text and extract structured facts.
# This gives the specialist clean, unambiguous input.
# ─────────────────────────────────────────────────────────────────────────────

CLASSIFIER_PROMPT = """You are a case intake classifier for airline refund requests.

Your ONLY job is to read the passenger's description and extract structured facts. Do NOT make any refund decision. Just extract the data.

Extract ALL of the following fields from the user's input. If a field cannot be determined, use null.

You MUST respond with valid JSON matching this schema:
{{
  "case_category": "cancellation" | "delay" | "downgrade" | "baggage" | "ancillary" | "24hour",
  "flight_type": "domestic" | "international",
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
  "accepted_alternative": true | false,
  "alternative_type": "rebooking" | "voucher" | "compensation" | "none",
  "passenger_traveled": true | false,
  "booking_date": "YYYY-MM-DD" or null,
  "flight_date": "YYYY-MM-DD" or null,
  "airline_name": string or null,
  "flight_number": string or null,
  "key_facts": ["fact 1", "fact 2", ...]
}}

IMPORTANT RULES:
- For flight_type: if the flight is between a US city and a foreign city, it is "international". If both cities are in the US, it is "domestic".
- For delay_hours: extract the EXACT number from the description. "5 hours and 45 minutes" = 5.75 hours.
- For bag_delay_hours: extract the EXACT hours between deplaning and bag delivery.
- For flight_duration_hours: extract the total flight time if mentioned.
- For passenger_traveled: true if they took the flight, false if they didn't fly.
- For accepted_alternative: true if they accepted rebooking, voucher, or compensation. False if they declined everything.
- key_facts: list the most important facts from the description that affect the refund decision.

Return ONLY the JSON. No other text."""


def run_classifier(
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> ClassifierOutput:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

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

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    chain = prompt | llm | StrOutputParser()
    raw = chain.invoke({"input": user_input})

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = {}

    output = ClassifierOutput(
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
    return output


# ── LLM 2: SPECIALIST (reuse Step 3 agent) ──────────────────────────────────

def run_specialist(executor, classifier_output: ClassifierOutput) -> dict:
    """Run the Step 3 agent with structured input from the classifier."""
    from refund_agent import run_agent

    case_text = (
        f"Case Category: {classifier_output.case_category}\n"
        f"Flight Type: {classifier_output.flight_type}\n"
        f"Payment Method: {classifier_output.payment_method}\n"
        f"Accepted Alternative: {'Yes — ' + classifier_output.alternative_type if classifier_output.accepted_alternative else 'No'}\n"
        f"Passenger Traveled: {'Yes' if classifier_output.passenger_traveled else 'No'}\n"
    )

    if classifier_output.flight_duration_hours is not None:
        case_text += f"Flight Duration: {classifier_output.flight_duration_hours} hours\n"
    if classifier_output.delay_hours is not None:
        case_text += f"Flight Delay: {classifier_output.delay_hours} hours\n"
    if classifier_output.bag_delay_hours is not None:
        case_text += f"Baggage Delay: {classifier_output.bag_delay_hours} hours after deplaning\n"
    if classifier_output.ticket_price is not None:
        case_text += f"Ticket Price: ${classifier_output.ticket_price}\n"
    if classifier_output.ancillary_fee is not None:
        case_text += f"Ancillary/Baggage Fee: ${classifier_output.ancillary_fee}\n"
    if classifier_output.original_class:
        case_text += f"Original Class: {classifier_output.original_class}\n"
    if classifier_output.downgraded_class:
        case_text += f"Downgraded To: {classifier_output.downgraded_class}\n"
    if classifier_output.original_class_price is not None:
        case_text += f"Original Class Price: ${classifier_output.original_class_price}\n"
    if classifier_output.downgraded_class_price is not None:
        case_text += f"Downgraded Class Price: ${classifier_output.downgraded_class_price}\n"
    if classifier_output.airline_name:
        case_text += f"Airline: {classifier_output.airline_name}\n"
    if classifier_output.flight_number:
        case_text += f"Flight Number: {classifier_output.flight_number}\n"
    if classifier_output.flight_date:
        case_text += f"Flight Date: {classifier_output.flight_date}\n"

    case_text += f"\nKey Facts:\n"
    for fact in classifier_output.key_facts:
        case_text += f"  - {fact}\n"

    case_text += f"\nOriginal Description: {classifier_output.raw_description}"

    return run_agent(executor, case_text)


# ── LLM 3: JUDGE ────────────────────────────────────────────────────────────
#
# Job: Review the specialist's decision for errors and contradictions.
# The judge can APPROVE or OVERRIDE the decision.
# ─────────────────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are a senior legal reviewer for airline refund decisions. Your job is to review a decision made by a junior analyst and check for errors.

CASE FACTS (extracted by classifier):
{case_facts}

ANALYST'S DECISION:
{decision_json}

YOUR REVIEW CHECKLIST:
1. CONTRADICTION CHECK: Does the decision (APPROVED/DENIED/PARTIAL) match the analysis steps? If the analysis says "NOT significantly delayed" but the decision is "APPROVED", that is a contradiction — OVERRIDE to DENIED.
2. THRESHOLD CHECK: Were the correct thresholds applied?
   - Domestic flight delay: 3+ hours = significant
   - International flight delay: 6+ hours = significant
   - Domestic baggage: 12 hours
   - International baggage (flight ≤12h): 15 hours
   - International baggage (flight >12h): 30 hours
3. ALTERNATIVE CHECK: If the passenger accepted a rebooking, voucher, or traveled on the flight, they generally should NOT get a refund (decision should be DENIED unless it's a downgrade fare difference).
4. COMPLETENESS CHECK: Are all relevant regulations cited? Is the reasoning complete?
5. LOGIC CHECK: Does each reasoning step logically follow from the previous one?

You MUST respond with valid JSON:
{{
  "approved": true | false,
  "issues_found": ["issue 1", ...] or [],
  "override_decision": "" (if approved) or "APPROVED" | "DENIED" | "PARTIAL" (if overriding),
  "override_reasons": ["reason 1", ...] or [],
  "confidence_adjustment": "" | "raise to HIGH" | "lower to MEDIUM" | "lower to LOW",
  "explanation": "Brief explanation of your review"
}}

If the decision is correct, set approved=true and issues_found=[].
If you find errors, set approved=false and provide the override.
Return ONLY the JSON."""


def run_judge(classifier_output: ClassifierOutput, specialist_decision: dict) -> JudgeVerdict:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

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

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
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
        data = {"approved": True, "issues_found": [], "explanation": "Judge failed to parse response."}

    return JudgeVerdict(
        approved=data.get("approved", True),
        issues_found=data.get("issues_found", []),
        override_decision=data.get("override_decision", ""),
        override_reasons=data.get("override_reasons", []),
        confidence_adjustment=data.get("confidence_adjustment", ""),
        explanation=data.get("explanation", ""),
    )


# ── Full Pipeline ────────────────────────────────────────────────────────────

def run_pipeline(
    executor,
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> PipelineResult:
    result = PipelineResult()

    # Stage 1: Classifier
    result.pipeline_log.append("🔵 Stage 1: Classifier — extracting structured facts...")
    classifier_output = run_classifier(
        case_type, flight_type, ticket_type,
        payment_method, accepted_alternative, description,
    )
    result.classifier_output = classifier_output
    result.pipeline_log.append(
        f"   ✓ Category: {classifier_output.case_category}, "
        f"Flight: {classifier_output.flight_type}, "
        f"Airline: {classifier_output.airline_name or 'unknown'}, "
        f"Flight#: {classifier_output.flight_number or 'unknown'}"
    )
    if classifier_output.delay_hours is not None:
        result.pipeline_log.append(f"   ✓ Delay: {classifier_output.delay_hours} hours")
    if classifier_output.bag_delay_hours is not None:
        result.pipeline_log.append(f"   ✓ Bag delay: {classifier_output.bag_delay_hours} hours")
    if classifier_output.flight_duration_hours is not None:
        result.pipeline_log.append(f"   ✓ Flight duration: {classifier_output.flight_duration_hours} hours")

    # Stage 2: Specialist (agent with tools)
    result.pipeline_log.append("\n🟡 Stage 2: Specialist — analyzing with tools...")
    specialist_decision = run_specialist(executor, classifier_output)
    result.specialist_decision = specialist_decision
    result.pipeline_log.append(
        f"   ✓ Decision: {specialist_decision.get('decision', '?')} "
        f"(confidence: {specialist_decision.get('confidence', '?')})"
    )
    tools_used = specialist_decision.get("tools_used", [])
    if tools_used:
        result.pipeline_log.append(f"   ✓ Tools used: {', '.join(tools_used)}")

    # Stage 3: Judge
    result.pipeline_log.append("\n🔴 Stage 3: Judge — reviewing decision...")
    judge_verdict = run_judge(classifier_output, specialist_decision)
    result.judge_verdict = judge_verdict

    if judge_verdict.approved:
        result.pipeline_log.append("   ✓ Judge APPROVED the decision — no issues found.")
        result.final_decision = specialist_decision
    else:
        result.pipeline_log.append(f"   ⚠️ Judge OVERRIDDEN — issues found:")
        for issue in judge_verdict.issues_found:
            result.pipeline_log.append(f"     - {issue}")
        result.pipeline_log.append(f"   → Override: {judge_verdict.override_decision}")

        final = specialist_decision.copy()
        final["decision"] = judge_verdict.override_decision
        if judge_verdict.override_reasons:
            final["reasons"] = judge_verdict.override_reasons
        if judge_verdict.confidence_adjustment:
            final["confidence"] = judge_verdict.confidence_adjustment.replace("raise to ", "").replace("lower to ", "")
        final["judge_override"] = True
        final["judge_issues"] = judge_verdict.issues_found
        final["judge_explanation"] = judge_verdict.explanation
        result.final_decision = final

    return result


# ── Formatting ───────────────────────────────────────────────────────────────

def format_pipeline_decision(result: PipelineResult) -> str:
    d = result.final_decision
    decision = d.get("decision", "UNKNOWN")
    emoji = {"APPROVED": "✅", "DENIED": "❌", "PARTIAL": "⚠️"}.get(decision, "❓")
    confidence = d.get("confidence", "?")

    lines = [f"# {emoji} Decision: {decision}", f"**Confidence:** {confidence}", ""]

    if d.get("judge_override"):
        lines.append("🔴 **Judge Override Applied** — The specialist's original decision was corrected.")
        lines.append(f"*Judge: {d.get('judge_explanation', '')}*")
        lines.append("")

    tools_used = d.get("tools_used", [])
    if tools_used:
        lines.append(f"**Tools Used:** {', '.join(f'`{t}`' for t in tools_used)}")
        lines.append("")

    lines += ["---", "## 🔍 Analysis"]
    for step in d.get("analysis_steps", []):
        lines.append(f"- {step}")

    lines += ["", "---", "## 📋 Reasons"]
    for reason in d.get("reasons", []):
        lines.append(f"- {reason}")

    lines += ["", "---", "## 📜 Regulations"]
    for reg in d.get("applicable_regulations", []):
        lines.append(f"- {reg}")

    refund = d.get("refund_details")
    if refund:
        lines += ["", "---", "## 💰 Refund Details"]
        for k, v in refund.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")

    lines += ["", "---", "## 📝 What You Should Do"]
    for action in d.get("passenger_action_items", []):
        lines.append(f"- {action}")

    letter = d.get("decision_letter")
    if letter:
        lines += ["", "---", "## ✉️ Formal Letter", "", "```", letter, "```"]

    if d.get("judge_issues"):
        lines += ["", "---", "## 🔴 Judge Issues Found"]
        for issue in d["judge_issues"]:
            lines.append(f"- {issue}")

    return "\n".join(lines)


def format_pipeline_log(result: PipelineResult) -> str:
    lines = ["## 🔄 Pipeline Execution Log", ""]
    lines.extend(result.pipeline_log)

    co = result.classifier_output
    lines += [
        "", "---", "## 📊 Classifier Extracted Facts", "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Category | {co.case_category} |",
        f"| Flight Type | {co.flight_type} |",
        f"| Airline | {co.airline_name or 'N/A'} |",
        f"| Flight # | {co.flight_number or 'N/A'} |",
        f"| Flight Date | {co.flight_date or 'N/A'} |",
        f"| Flight Duration | {co.flight_duration_hours or 'N/A'} hours |",
        f"| Delay Hours | {co.delay_hours or 'N/A'} |",
        f"| Bag Delay Hours | {co.bag_delay_hours or 'N/A'} |",
        f"| Ticket Price | ${co.ticket_price or 'N/A'} |",
        f"| Fee Paid | ${co.ancillary_fee or 'N/A'} |",
        f"| Payment | {co.payment_method} |",
        f"| Accepted Alt. | {co.accepted_alternative} |",
        f"| Traveled | {co.passenger_traveled} |",
    ]

    if co.key_facts:
        lines += ["", "**Key Facts:**"]
        for fact in co.key_facts:
            lines.append(f"- {fact}")

    jv = result.judge_verdict
    lines += [
        "", "---", "## ⚖️ Judge Review", "",
        f"**Verdict:** {'✅ Approved' if jv.approved else '🔴 Overridden'}",
        f"**Explanation:** {jv.explanation}",
    ]
    if jv.issues_found:
        lines.append("**Issues:**")
        for issue in jv.issues_found:
            lines.append(f"- {issue}")

    return "\n".join(lines)


# ── Gradio UI ────────────────────────────────────────────────────────────────

CASE_TYPES = [
    "Flight Cancellation",
    "Schedule Change / Significant Delay",
    "Downgrade to Lower Class",
    "Baggage Lost or Delayed",
    "Ancillary Service Not Provided",
    "24-Hour Cancellation (within 24h of booking)",
]
FLIGHT_TYPES = ["Domestic (within US)", "International"]
TICKET_TYPES = ["Refundable", "Non-refundable"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Cash", "Check", "Airline Miles", "Other"]
ACCEPTED_ALTERNATIVES = [
    "No — I did not accept any alternative",
    "Yes — I accepted a rebooked flight",
    "Yes — I accepted a travel voucher / credit",
    "Yes — I accepted other compensation (miles, etc.)",
    "Yes — I traveled on the flight anyway",
]


def create_gradio_app():
    import gradio as gr
    from refund_agent import build_or_load_index, build_agent
    from decision_cache import DecisionCache

    print("[PIPELINE] Building index...")
    index = build_or_load_index()
    executor = build_agent(index)
    cache = DecisionCache()
    print(f"[PIPELINE] Ready. Cache: {cache.stats['total_entries']} entries.")

    def analyze(case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description):
        if not description or not description.strip():
            return "⚠️ Please describe what happened.", "", ""

        cached_result, cache_status = cache.lookup(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        if cached_result:
            label = {"exact_hit": "⚡ EXACT HIT", "semantic_hit": "🔍 SIMILAR"}.get(cache_status, "")
            return (
                format_pipeline_decision(PipelineResult(final_decision=cached_result)),
                f"📊 Cache: {label} | {cache.stats['total_entries']} entries",
                "*Served from cache.*",
            )

        pipeline_result = run_pipeline(
            executor, case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        final = pipeline_result.final_decision
        if final.get("decision") != "ERROR":
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, final,
            )

        return (
            format_pipeline_decision(pipeline_result),
            f"📊 Cache: {cache.stats['total_entries']} entries",
            format_pipeline_log(pipeline_result),
        )

    def clear_cache():
        cache.clear()
        return "📊 Cache: 0 entries"

    with gr.Blocks(title="Airlines Refund Pipeline", theme=gr.themes.Soft()) as app:
        gr.Markdown("# ✈️ Airlines Refund Decision Pipeline")
        gr.Markdown(
            "**Step 4: LLM-to-LLM** — Three LLMs work together: "
            "**Classifier** extracts facts → **Specialist** analyzes with tools → "
            "**Judge** reviews for errors."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📋 Case Details")
                case_type = gr.Dropdown(choices=CASE_TYPES, value=CASE_TYPES[0], label="Case Type")
                flight_type = gr.Dropdown(choices=FLIGHT_TYPES, value=FLIGHT_TYPES[0], label="Flight Type")
                ticket_type = gr.Dropdown(choices=TICKET_TYPES, value=TICKET_TYPES[1], label="Ticket Type")
                payment_method = gr.Dropdown(choices=PAYMENT_METHODS, value=PAYMENT_METHODS[0], label="Payment Method")
                accepted_alternative = gr.Dropdown(choices=ACCEPTED_ALTERNATIVES, value=ACCEPTED_ALTERNATIVES[0], label="Did you accept any alternative?")
                description = gr.Textbox(label="Describe what happened", placeholder="Example: My flight was cancelled...", lines=5)
                submit_btn = gr.Button("🔄 Run Pipeline", variant="primary", size="lg")

            with gr.Column(scale=1):
                with gr.Tabs():
                    with gr.Tab("📄 Decision"):
                        output = gr.Markdown(value="*Submit a case to run the 3-LLM pipeline.*")
                    with gr.Tab("🔄 Pipeline Log"):
                        pipeline_log = gr.Markdown(value="*Pipeline execution details will appear here.*")
                gr.Markdown("---")
                cache_display = gr.Textbox(label="Status", value=f"📊 Cache: {cache.stats['total_entries']} entries", interactive=False)
                clear_btn = gr.Button("🗑️ Clear Cache", size="sm")

        submit_btn.click(
            fn=analyze,
            inputs=[case_type, flight_type, ticket_type, payment_method, accepted_alternative, description],
            outputs=[output, cache_display, pipeline_log],
        )
        clear_btn.click(fn=clear_cache, outputs=cache_display)

        gr.Markdown("---")
        gr.Markdown(
            "**Pipeline:** 🔵 Classifier → 🟡 Specialist (with tools) → 🔴 Judge  \n"
            "**Tools:** `search_regulations` · `check_delay_threshold` · `check_baggage_threshold` · "
            "`calculate_refund` · `calculate_refund_timeline` · `generate_decision_letter`"
        )

    return app


if __name__ == "__main__":
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=7861)
