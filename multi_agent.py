"""
Multi-Agent System: Supervisor + Researcher + Analyst + Writer

Step 5 of the learning roadmap: Agent-to-Agent communication.

Demonstrates:
  - Agent delegation: Supervisor routes work to specialist workers
  - Separation of concerns: each agent has its own tools and focus
  - Multi-agent coordination: agents share information via the Supervisor
  - Scalability: adding a new capability = adding a new worker agent
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
class WorkerOutput:
    agent_name: str
    result: str
    tools_used: list[str] = field(default_factory=list)


@dataclass
class MultiAgentResult:
    researcher_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Researcher", ""))
    analyst_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Analyst", ""))
    writer_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Writer", ""))
    supervisor_decision: dict = field(default_factory=dict)
    agent_log: list[str] = field(default_factory=list)


# ── Worker Agent Builder ─────────────────────────────────────────────────────

def _build_worker(system_prompt: str, tools: list):
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent


def _run_worker(agent, task: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""


# ── RESEARCHER Agent ─────────────────────────────────────────────────────────

RESEARCHER_PROMPT = """You are a Regulation Researcher for airline refund cases.

YOUR ONLY JOB: Search the DOT regulation documents and find ALL rules that apply to this case.

INSTRUCTIONS:
1. Use the search_regulations tool to find relevant DOT rules.
2. Search multiple times with different queries if needed to cover all aspects.
3. For each regulation you find, provide:
   - The exact rule text (quote it)
   - Which document it came from
   - How it applies to this specific case

OUTPUT FORMAT: Return a clear, organized summary of all applicable regulations.
Do NOT make a refund decision — that's the Analyst's job. Just find the rules."""


def build_researcher(index):
    from refund_tools import make_search_tool
    search_tool = make_search_tool(index)
    return _build_worker(RESEARCHER_PROMPT, [search_tool])


# ── ANALYST Agent ────────────────────────────────────────────────────────────

ANALYST_PROMPT = """You are a Refund Analyst for airline refund cases.

YOUR ONLY JOB: Use your tools to check thresholds, calculate amounts, and determine timelines. Do NOT write letters or search documents — other agents handle those.

INSTRUCTIONS:
1. Based on the case type, call the appropriate threshold checker tool.
2. ALWAYS trust the tool results — do NOT override them with your own reasoning.
3. If the case involves a refund amount, use calculate_refund.
4. Always use calculate_refund_timeline to determine the deadline.
5. State your recommendation clearly: APPROVED, DENIED, or PARTIAL.

OUTPUT FORMAT: Return a structured analysis with:
- Threshold check results (quote the tool output)
- Refund amount (if applicable)
- Refund deadline
- Your recommendation: APPROVED, DENIED, or PARTIAL
- Clear reasoning for your recommendation

CRITICAL: If a tool says "NOT significantly delayed" or "does NOT meet threshold", your recommendation MUST be DENIED. Never override tool results."""


def build_analyst():
    from refund_tools import (
        check_delay_threshold,
        check_baggage_threshold,
        calculate_refund,
        calculate_refund_timeline,
    )
    tools = [check_delay_threshold, check_baggage_threshold, calculate_refund, calculate_refund_timeline]
    return _build_worker(ANALYST_PROMPT, tools)


# ── WRITER Agent ─────────────────────────────────────────────────────────────

WRITER_PROMPT = """You are a Decision Writer for airline refund cases.

YOUR ONLY JOB: Take the Analyst's recommendation and the Researcher's regulations, and write a clear, passenger-friendly decision with a formal letter (if approved).

INSTRUCTIONS:
1. Write the final decision based on the Analyst's recommendation — do NOT change the APPROVED/DENIED/PARTIAL outcome.
2. If the decision is APPROVED or PARTIAL, use generate_decision_letter to create a formal letter.
3. Write clear action items for the passenger.
4. Cite the specific regulations the Researcher found.

OUTPUT FORMAT: Return valid JSON with this schema:
{
  "decision": "APPROVED" | "DENIED" | "PARTIAL",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "analysis_steps": ["Step 1 — ...", ...],
  "reasons": ["reason 1", ...],
  "applicable_regulations": ["regulation 1", ...],
  "refund_details": {"refund_type": "...", "refund_amount": "...", "payment_method": "...", "timeline": "..."} or null,
  "passenger_action_items": ["action 1", ...],
  "decision_letter": "..." or null
}

Return ONLY the JSON."""


def build_writer():
    from refund_tools import generate_decision_letter
    return _build_worker(WRITER_PROMPT, [generate_decision_letter])


# ── SUPERVISOR ───────────────────────────────────────────────────────────────

def run_multi_agent(
    index,
    researcher_agent,
    analyst_agent,
    writer_agent,
    case_summary: str,
) -> MultiAgentResult:
    """
    Supervisor coordinates three workers:
      1. Researcher finds regulations
      2. Analyst checks thresholds and calculates (with Researcher's findings)
      3. Writer produces final decision (with both previous outputs)
    """
    result = MultiAgentResult()

    # ── Step 1: Researcher ───────────────────────────────────────────────
    result.agent_log.append("📚 **Researcher** — Finding applicable regulations...")
    researcher_task = (
        f"Find all DOT regulations that apply to this case:\n\n{case_summary}"
    )
    researcher_output = _run_worker(researcher_agent, researcher_task)
    result.researcher_output = WorkerOutput(
        agent_name="Researcher",
        result=researcher_output,
        tools_used=["search_regulations"],
    )
    preview = researcher_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Found regulations: {preview}...")

    # ── Step 2: Analyst ──────────────────────────────────────────────────
    result.agent_log.append("\n🔢 **Analyst** — Checking thresholds and calculating...")
    analyst_task = (
        f"Analyze this case using your tools.\n\n"
        f"CASE:\n{case_summary}\n\n"
        f"REGULATIONS FOUND BY RESEARCHER:\n{researcher_output}"
    )
    analyst_output = _run_worker(analyst_agent, analyst_task)
    result.analyst_output = WorkerOutput(
        agent_name="Analyst",
        result=analyst_output,
        tools_used=["check_delay_threshold", "check_baggage_threshold", "calculate_refund", "calculate_refund_timeline"],
    )
    preview = analyst_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Analysis complete: {preview}...")

    # ── Step 3: Writer ───────────────────────────────────────────────────
    result.agent_log.append("\n✍️ **Writer** — Drafting decision and letter...")
    writer_task = (
        f"Write the final decision based on the Analyst's recommendation.\n\n"
        f"CASE:\n{case_summary}\n\n"
        f"REGULATIONS (from Researcher):\n{researcher_output}\n\n"
        f"ANALYSIS (from Analyst):\n{analyst_output}\n\n"
        f"Write the decision as JSON. If APPROVED or PARTIAL, also generate a formal letter."
    )
    writer_output = _run_worker(writer_agent, writer_task)
    result.writer_output = WorkerOutput(
        agent_name="Writer",
        result=writer_output,
        tools_used=["generate_decision_letter"],
    )

    # Parse the Writer's JSON output
    cleaned = writer_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        decision = json.loads(cleaned)
    except json.JSONDecodeError:
        decision = {
            "decision": "ERROR",
            "confidence": "LOW",
            "analysis_steps": ["Writer failed to produce valid JSON."],
            "reasons": [writer_output[:300]],
            "applicable_regulations": [],
            "refund_details": None,
            "passenger_action_items": ["Please try again."],
            "decision_letter": None,
        }

    decision["agents_used"] = ["Researcher", "Analyst", "Writer"]
    result.supervisor_decision = decision
    result.agent_log.append(f"\n🟣 **Supervisor** — Final decision: {decision.get('decision', '?')}")

    return result


# ── Formatting ───────────────────────────────────────────────────────────────

def format_multi_agent_decision(result: MultiAgentResult) -> str:
    d = result.supervisor_decision
    decision = d.get("decision", "UNKNOWN")
    emoji = {"APPROVED": "✅", "DENIED": "❌", "PARTIAL": "⚠️"}.get(decision, "❓")

    lines = [
        f"# {emoji} Decision: {decision}",
        f"**Confidence:** {d.get('confidence', '?')}",
        "",
        f"**Agents Used:** 📚 Researcher → 🔢 Analyst → ✍️ Writer",
        "",
    ]

    if d.get("judge_override"):
        lines.append("🔴 **Judge Override Applied**")
        lines.append(f"*{d.get('judge_explanation', '')}*")
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

    return "\n".join(lines)


def format_agent_log(result: MultiAgentResult) -> str:
    lines = ["## 🤖 Multi-Agent Execution Log", ""]
    lines.extend(result.agent_log)

    lines += [
        "", "---",
        "## 📚 Researcher's Full Output",
        "", result.researcher_output.result,
        "", "---",
        "## 🔢 Analyst's Full Output",
        "", result.analyst_output.result,
    ]

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
    from refund_agent import build_or_load_index
    from llm_pipeline import run_classifier, run_judge, format_pipeline_log, PipelineResult
    from decision_cache import DecisionCache

    print("[MULTI-AGENT] Building index...")
    index = build_or_load_index()

    print("[MULTI-AGENT] Building worker agents...")
    researcher_agent = build_researcher(index)
    analyst_agent = build_analyst()
    writer_agent = build_writer()

    cache = DecisionCache()
    print(f"[MULTI-AGENT] Ready. 3 workers + supervisor. Cache: {cache.stats['total_entries']} entries.")

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
                format_multi_agent_decision(MultiAgentResult(supervisor_decision=cached_result)),
                f"📊 Cache: {label} | {cache.stats['total_entries']} entries",
                "*Served from cache.*",
            )

        # Stage 1: Classifier
        classifier_output = run_classifier(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        case_summary = (
            f"Case Category: {classifier_output.case_category}\n"
            f"Flight Type: {classifier_output.flight_type}\n"
            f"Payment Method: {classifier_output.payment_method}\n"
            f"Accepted Alternative: {'Yes — ' + classifier_output.alternative_type if classifier_output.accepted_alternative else 'No'}\n"
            f"Passenger Traveled: {'Yes' if classifier_output.passenger_traveled else 'No'}\n"
        )
        if classifier_output.flight_duration_hours is not None:
            case_summary += f"Flight Duration: {classifier_output.flight_duration_hours} hours\n"
        if classifier_output.delay_hours is not None:
            case_summary += f"Flight Delay: {classifier_output.delay_hours} hours\n"
        if classifier_output.bag_delay_hours is not None:
            case_summary += f"Baggage Delay: {classifier_output.bag_delay_hours} hours\n"
        if classifier_output.ticket_price is not None:
            case_summary += f"Ticket Price: ${classifier_output.ticket_price}\n"
        if classifier_output.ancillary_fee is not None:
            case_summary += f"Baggage/Ancillary Fee: ${classifier_output.ancillary_fee}\n"
        if classifier_output.original_class:
            case_summary += f"Original Class: {classifier_output.original_class}\n"
        if classifier_output.downgraded_class:
            case_summary += f"Downgraded To: {classifier_output.downgraded_class}\n"
        if classifier_output.original_class_price is not None:
            case_summary += f"Original Class Price: ${classifier_output.original_class_price}\n"
        if classifier_output.downgraded_class_price is not None:
            case_summary += f"Downgraded Class Price: ${classifier_output.downgraded_class_price}\n"
        if classifier_output.airline_name:
            case_summary += f"Airline: {classifier_output.airline_name}\n"
        if classifier_output.flight_number:
            case_summary += f"Flight Number: {classifier_output.flight_number}\n"
        if classifier_output.flight_date:
            case_summary += f"Flight Date: {classifier_output.flight_date}\n"
        case_summary += f"\nKey Facts: {', '.join(classifier_output.key_facts)}"
        case_summary += f"\nOriginal Description: {description}"

        # Stage 2: Multi-Agent (Researcher → Analyst → Writer)
        ma_result = run_multi_agent(
            index, researcher_agent, analyst_agent, writer_agent, case_summary,
        )

        # Stage 3: Judge reviews
        judge_verdict = run_judge(classifier_output, ma_result.supervisor_decision)
        if not judge_verdict.approved and judge_verdict.override_decision:
            final = ma_result.supervisor_decision.copy()
            final["decision"] = judge_verdict.override_decision
            if judge_verdict.override_reasons:
                final["reasons"] = judge_verdict.override_reasons
            final["judge_override"] = True
            final["judge_issues"] = judge_verdict.issues_found
            final["judge_explanation"] = judge_verdict.explanation
            ma_result.supervisor_decision = final
            ma_result.agent_log.append(f"\n🔴 **Judge** — OVERRIDDEN: {judge_verdict.explanation}")
        else:
            ma_result.agent_log.append(f"\n🔴 **Judge** — Approved ✓")

        final = ma_result.supervisor_decision
        if final.get("decision") != "ERROR":
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, final,
            )

        return (
            format_multi_agent_decision(ma_result),
            f"📊 Cache: {cache.stats['total_entries']} entries",
            format_agent_log(ma_result),
        )

    def clear_cache():
        cache.clear()
        return "📊 Cache: 0 entries"

    with gr.Blocks(title="Airlines Refund Multi-Agent", theme=gr.themes.Soft()) as app:
        gr.Markdown("# ✈️ Airlines Refund — Multi-Agent System")
        gr.Markdown(
            "**Step 5: Agent-to-Agent** — A Supervisor coordinates three worker agents: "
            "📚 **Researcher** (finds regulations) → 🔢 **Analyst** (checks thresholds) → "
            "✍️ **Writer** (drafts decision). Then 🔴 **Judge** reviews."
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
                submit_btn = gr.Button("🤖 Run Multi-Agent Analysis", variant="primary", size="lg")

            with gr.Column(scale=1):
                with gr.Tabs():
                    with gr.Tab("📄 Decision"):
                        output = gr.Markdown(value="*Submit a case to run the multi-agent system.*")
                    with gr.Tab("🤖 Agent Log"):
                        agent_log = gr.Markdown(value="*Agent execution details will appear here.*")
                gr.Markdown("---")
                cache_display = gr.Textbox(label="Status", value=f"📊 Cache: {cache.stats['total_entries']} entries", interactive=False)
                clear_btn = gr.Button("🗑️ Clear Cache", size="sm")

        submit_btn.click(
            fn=analyze,
            inputs=[case_type, flight_type, ticket_type, payment_method, accepted_alternative, description],
            outputs=[output, cache_display, agent_log],
        )
        clear_btn.click(fn=clear_cache, outputs=cache_display)

        gr.Markdown("---")
        gr.Markdown(
            "**Agents:** 🔵 Classifier → 🟣 Supervisor → 📚 Researcher → 🔢 Analyst → ✍️ Writer → 🔴 Judge  \n"
            "**Tools:** `search_regulations` · `check_delay_threshold` · `check_baggage_threshold` · "
            "`calculate_refund` · `calculate_refund_timeline` · `generate_decision_letter`"
        )

    return app


if __name__ == "__main__":
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=7861)
