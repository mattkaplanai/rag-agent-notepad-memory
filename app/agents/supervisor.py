"""Supervisor — coordinates Researcher, Analyst, and Writer agents."""

import json

from app.models.schemas import MultiAgentResult, WorkerOutput
from app.agents.researcher import run_researcher
from app.agents.analyst import run_analyst
from app.agents.writer import run_writer


def run_multi_agent(
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

    # Step 1: Researcher
    result.agent_log.append("📚 **Researcher** — Finding applicable regulations...")
    researcher_output = run_researcher(
        researcher_agent,
        f"Find all DOT regulations that apply to this case:\n\n{case_summary}",
    )
    result.researcher_output = WorkerOutput(
        agent_name="Researcher", result=researcher_output, tools_used=["search_regulations"],
    )
    preview = researcher_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Found regulations: {preview}...")

    # Step 2: Analyst
    result.agent_log.append("\n🔢 **Analyst** — Checking thresholds and calculating...")
    analyst_output = run_analyst(
        analyst_agent,
        f"Analyze this case using your tools.\n\nCASE:\n{case_summary}\n\nREGULATIONS FOUND BY RESEARCHER:\n{researcher_output}",
    )
    result.analyst_output = WorkerOutput(
        agent_name="Analyst", result=analyst_output,
        tools_used=["check_delay_threshold", "check_baggage_threshold", "calculate_refund", "calculate_refund_timeline"],
    )
    preview = analyst_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Analysis complete: {preview}...")

    # Step 3: Writer
    result.agent_log.append("\n✍️ **Writer** — Drafting decision and letter...")
    writer_output = run_writer(
        writer_agent,
        f"Write the final decision based on the Analyst's recommendation.\n\n"
        f"CASE:\n{case_summary}\n\nREGULATIONS (from Researcher):\n{researcher_output}\n\n"
        f"ANALYSIS (from Analyst):\n{analyst_output}\n\n"
        f"Write the decision as JSON. If APPROVED or PARTIAL, also generate a formal letter.",
    )
    result.writer_output = WorkerOutput(
        agent_name="Writer", result=writer_output, tools_used=["generate_decision_letter"],
    )

    # Parse Writer's JSON
    from app.utils import clean_llm_json
    try:
        decision = clean_llm_json(writer_output)
    except (json.JSONDecodeError, ValueError):
        decision = {
            "decision": "ERROR", "confidence": "LOW",
            "analysis_steps": ["Writer failed to produce valid JSON."],
            "reasons": [writer_output[:300]], "applicable_regulations": [],
            "refund_details": None, "passenger_action_items": ["Please try again."],
            "decision_letter": None,
        }

    decision["agents_used"] = ["Researcher", "Analyst", "Writer"]
    result.supervisor_decision = decision
    result.agent_log.append(f"\n🟣 **Supervisor** — Final decision: {decision.get('decision', '?')}")

    return result
