"""Gradio UI -- the web interface for the multi-agent refund decision system."""

import logging
import gradio as gr

logger = logging.getLogger(__name__)
from app.agents.ansi_colors import G as _G, R as _R, Y as _Y, W as _W, B as _B, X as _X

from app.config import CASE_TYPES, FLIGHT_TYPES, TICKET_TYPES, PAYMENT_METHODS, ACCEPTED_ALTERNATIVES
from app.models.schemas import MultiAgentResult
from app.agents.classifier import run_classifier, build_case_summary
from app.agents.judge import run_judge
from app.agents.supervisor import run_multi_agent
from app.guards import run_input_guard, run_output_guard
from app.cache.decision_cache import DecisionCache
from app.db.decision_db import DecisionDB


def format_decision(result: MultiAgentResult) -> str:
    d = result.supervisor_decision
    decision = d.get("decision", "UNKNOWN")
    emoji = {"APPROVED": "ok", "DENIED": "x", "PARTIAL": "!"}.get(decision, "?")

    lines = [
        f"# [{emoji}] Decision: {decision}",
        f"**Confidence:** {d.get('confidence', '?')}",
        "",
        f"**Agents Used:** Researcher > Analyst > Writer",
        "",
    ]

    if d.get("judge_override"):
        lines.append("**[OVERRIDE] Judge Override Applied**")
        lines.append(f"*{d.get('judge_explanation', '')}*")
        lines.append("")

    lines += ["---", "## Analysis"]
    for step in d.get("analysis_steps", []):
        lines.append(f"- {step}")

    lines += ["", "---", "## Reasons"]
    for reason in d.get("reasons", []):
        lines.append(f"- {reason}")

    lines += ["", "---", "## Regulations"]
    for reg in d.get("applicable_regulations", []):
        lines.append(f"- {reg}")

    refund = d.get("refund_details")
    if refund:
        lines += ["", "---", "## Refund Details"]
        for k, v in refund.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")

    lines += ["", "---", "## What You Should Do"]
    for action in d.get("passenger_action_items", []):
        lines.append(f"- {action}")

    letter = d.get("decision_letter")
    if letter:
        lines += ["", "---", "## Formal Letter", "", "```", letter, "```"]

    return "\n".join(lines)


def format_agent_log(result: MultiAgentResult) -> str:
    lines = ["## Multi-Agent Execution Log", ""]
    lines.extend(result.agent_log)
    lines += [
        "", "---", "## Researcher's Full Output", "",
        result.researcher_output.result[:800] + "..." if len(result.researcher_output.result) > 800 else result.researcher_output.result,
        "", "---", "## Analyst's Full Output", "",
        result.analyst_output.result[:800] + "..." if len(result.analyst_output.result) > 800 else result.analyst_output.result,
    ]
    return "\n".join(lines)


def create_app(index, researcher_agent, analyst_agent, writer_agent):
    """Create and return the Gradio app."""

    cache = DecisionCache()
    db = DecisionDB()

    def analyze(case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description, progress=gr.Progress()):
        if not description or not description.strip():
            return "Please describe what happened.", "", ""

        logger.info(f"{_W}[PIPELINE] ══════════ NEW CASE ══════════════════════════{_X}")
        logger.info(f"{_B}[PIPELINE] Type: {case_type} | Flight: {flight_type} | Payment: {payment_method}{_X}")

        # Input guard: block before cache/pipeline if request is unsafe or off-topic
        data = {
            "case_type": case_type, "flight_type": flight_type, "ticket_type": ticket_type,
            "payment_method": payment_method, "accepted_alternative": accepted_alternative,
            "description": (description or "").strip(),
        }
        input_result = run_input_guard(data)
        if not input_result.passed:
            logger.info(f"{_R}[GUARD   ] ✗ Blocked — {input_result.block_reason}{_X}")
            err_result = MultiAgentResult(supervisor_decision=input_result.block_response or {})
            return (
                format_decision(err_result),
                f"Cache: {cache.stats['total_entries']} entries",
                f"**Input guard blocked:** {input_result.block_reason}\n\nChecks: {', '.join(input_result.checks_performed)}",
            )
        logger.info(f"{_G}[GUARD   ] ✓ Input guard passed{_X}")
        data = input_result.sanitized_data or data
        case_type, flight_type, ticket_type = data["case_type"], data["flight_type"], data["ticket_type"]
        payment_method, accepted_alternative, description = data["payment_method"], data["accepted_alternative"], data["description"]

        progress(0.1, desc="Checking cache...")
        cached_result, cache_status, query_embedding = cache.lookup(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        if cached_result:
            label = {"exact_hit": "EXACT HIT", "semantic_hit": "SIMILAR"}.get(cache_status, "")
            logger.info(f"{_G}[CACHE   ] ✓ {label} — returning cached decision{_X}")
            return (
                format_decision(MultiAgentResult(supervisor_decision=cached_result)),
                f"Cache: {label} | {cache.stats['total_entries']} entries",
                "*Served from cache.*",
            )
        logger.info(f"{_Y}[CACHE   ] ✗ Miss — proceeding to pipeline{_X}")

        # DB lookup: check PostgreSQL for past decisions (tier 2)
        if db.enabled:
            progress(0.15, desc="Checking decision database...")
            db_result = db.get_by_hash(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description,
            )
            if not db_result and query_embedding:
                db_result = db.get_by_semantic(query_embedding)
            if db_result:
                logger.info(f"{_G}[DB      ] ✓ Hit — returning stored decision{_X}")
                # Store in cache for faster future hits
                cache.store(
                    case_type, flight_type, ticket_type,
                    payment_method, accepted_alternative, description, db_result,
                    embedding=query_embedding,
                )
                return (
                    format_decision(MultiAgentResult(supervisor_decision=db_result)),
                    f"DB HIT | Cache: {cache.stats['total_entries']} entries",
                    "*Served from database (PostgreSQL).*",
                )
            logger.info(f"{_Y}[DB      ] ✗ Miss — running full pipeline{_X}")

        progress(0.2, desc="Classifying case...")
        classifier_output = run_classifier(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        case_summary = build_case_summary(classifier_output)

        progress(0.4, desc="Running multi-agent pipeline (Researcher > Analyst > Writer)...")
        ma_result = run_multi_agent(
            researcher_agent, analyst_agent, writer_agent, case_summary,
        )

        progress(0.8, desc="Judge reviewing decision...")
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
            ma_result.agent_log.append(f"\n**Judge** -- OVERRIDDEN: {judge_verdict.explanation}")
        else:
            ma_result.agent_log.append(f"\n**Judge** -- Approved")

        # Output guard: enforce decision shape and citations
        final = ma_result.supervisor_decision
        output_result = run_output_guard(final)
        if not output_result.passed:
            ma_result.agent_log.append(f"\n**Output guard** -- Blocked: {output_result.block_reason}")
            ma_result.supervisor_decision = output_result.override_decision or final
            final = ma_result.supervisor_decision

        progress(0.9, desc="Caching result...")
        decision_val = final.get("decision", "?")
        color = {"APPROVED": _G, "DENIED": _R, "PARTIAL": _Y}.get(decision_val, _W)
        logger.info(f"{color}[DECISION] ══ {decision_val} | Confidence: {final.get('confidence','?')} ══{_X}")
        if final.get("decision") != "ERROR":
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, final,
                embedding=query_embedding,
            )
            db.insert(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, final,
                embedding=query_embedding,
            )

            logger.info(f"{_G}[STORE   ] ✓ Saved to cache + PostgreSQL (cache: {cache.stats['total_entries']} entries){_X}")
        progress(1.0, desc="Done!")
        return (
            format_decision(ma_result),
            f"Cache: {cache.stats['total_entries']} entries",
            format_agent_log(ma_result),
        )

    def clear_cache():
        cache.clear()
        return "Cache: 0 entries"

    with gr.Blocks(title="Airlines Refund Multi-Agent", theme=gr.themes.Soft()) as app:
        gr.Markdown("# Airlines Refund -- Multi-Agent System")
        gr.Markdown(
            "**Agent Pipeline:** Classifier > Supervisor "
            "(Researcher > Analyst > Writer) > Judge"
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### Case Details")
                case_type = gr.Dropdown(choices=CASE_TYPES, value=CASE_TYPES[0], label="Case Type")
                flight_type = gr.Dropdown(choices=FLIGHT_TYPES, value=FLIGHT_TYPES[0], label="Flight Type")
                ticket_type = gr.Dropdown(choices=TICKET_TYPES, value=TICKET_TYPES[1], label="Ticket Type")
                payment_method = gr.Dropdown(choices=PAYMENT_METHODS, value=PAYMENT_METHODS[0], label="Payment Method")
                accepted_alternative = gr.Dropdown(choices=ACCEPTED_ALTERNATIVES, value=ACCEPTED_ALTERNATIVES[0], label="Did you accept any alternative?")
                description = gr.Textbox(label="Describe what happened", placeholder="Example: My flight was cancelled...", lines=5)
                submit_btn = gr.Button("Run Multi-Agent Analysis", variant="primary", size="lg")

            with gr.Column(scale=1):
                with gr.Tabs():
                    with gr.Tab("Decision"):
                        output = gr.Markdown(value="*Submit a case to run the multi-agent system.*")
                    with gr.Tab("Agent Log"):
                        agent_log = gr.Markdown(value="*Agent execution details will appear here.*")
                gr.Markdown("---")
                cache_display = gr.Textbox(label="Status", value=f"Cache: {cache.stats['total_entries']} entries", interactive=False)
                clear_btn = gr.Button("Clear Cache", size="sm")

        submit_btn.click(
            fn=analyze,
            inputs=[case_type, flight_type, ticket_type, payment_method, accepted_alternative, description],
            outputs=[output, cache_display, agent_log],
        )
        clear_btn.click(fn=clear_cache, outputs=cache_display)

        gr.Markdown("---")
        gr.Markdown(
            "**Researcher Tools:** `search_regulations` | `lookup_regulation` | "
            "`cross_reference` | `search_past_decisions` | `summarize_findings`\n\n"
            "**Analyst Tools:** `check_delay_threshold` | `check_baggage_threshold` | "
            "`calculate_refund` | `calculate_refund_timeline`\n\n"
            "**Writer Tools:** `generate_decision_letter`"
        )

    return app
