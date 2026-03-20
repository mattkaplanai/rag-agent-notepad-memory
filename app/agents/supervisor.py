"""Supervisor — coordinates Researcher, Analyst, and Writer agents."""

import json
import logging
import time

from app.models.schemas import MultiAgentResult, WorkerOutput
from app.agents.researcher import run_researcher, run_researcher_parallel
from app.agents.analyst import run_analyst
from app.agents.writer import run_writer

logger = logging.getLogger(__name__)
from app.agents.ansi_colors import C as _C, G as _G, W as _W, X as _X


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

    # Step 1: Researcher (parallel subagents if tuple, single agent otherwise)
    task = f"Find all DOT regulations that apply to this case:\n\n{case_summary}"
    if isinstance(researcher_agent, tuple):
        result.agent_log.append(
            "📚 **Researcher** — Running 3 parallel subagents "
            "(Federal Regs / Past Decisions / Airline Commitments)..."
        )
        logger.info(f"{_C}[RESEARCH] ▶ Starting 3 parallel researcher subagents...{_X}")
        t0 = time.time()
        researcher_output = run_researcher_parallel(researcher_agent, task)
    else:
        result.agent_log.append("📚 **Researcher** — Finding applicable regulations...")
        logger.info(f"{_C}[RESEARCH] ▶ Starting Researcher agent...{_X}")
        t0 = time.time()
        researcher_output = run_researcher(researcher_agent, task)
    elapsed = time.time() - t0
    result.researcher_output = WorkerOutput(
        agent_name="Researcher", result=researcher_output, tools_used=["search_regulations"],
    )
    preview = researcher_output[:120].replace("\n", " ")
    result.agent_log.append(f"   ✓ Found regulations: {preview}...")
    logger.info(f"{_G}[RESEARCH] ✓ Done in {elapsed:.1f}s — {preview[:80]}...{_X}")

    # Step 2: Analyst
    result.agent_log.append("\n🔢 **Analyst** — Checking thresholds and calculating...")
    logger.info(f"{_C}[ANALYST ] ▶ Starting Analyst agent...{_X}")
    t0 = time.time()
    analyst_output = run_analyst(
        analyst_agent,
        f"Analyze this case using your tools.\n\nCASE:\n{case_summary}\n\nREGULATIONS FOUND BY RESEARCHER:\n{researcher_output}",
    )
    elapsed = time.time() - t0
    result.analyst_output = WorkerOutput(
        agent_name="Analyst", result=analyst_output,
        tools_used=["check_delay_threshold", "check_baggage_threshold", "calculate_refund", "calculate_refund_timeline"],
    )
    preview = analyst_output[:120].replace("\n", " ")
    result.agent_log.append(f"   ✓ Analysis complete: {preview}...")
    logger.info(f"{_G}[ANALYST ] ✓ Done in {elapsed:.1f}s — {preview[:80]}...{_X}")

    # Step 3: Writer
    result.agent_log.append("\n✍️ **Writer** — Drafting decision and letter...")
    logger.info(f"{_C}[WRITER  ] ▶ Drafting decision and formal letter...{_X}")
    t0 = time.time()
    writer_output = run_writer(
        writer_agent,
        f"Write the final decision based on the Analyst's recommendation.\n\n"
        f"CASE:\n{case_summary}\n\nREGULATIONS (from Researcher):\n{researcher_output}\n\n"
        f"ANALYSIS (from Analyst):\n{analyst_output}\n\n"
        f"Write the decision as JSON. If APPROVED or PARTIAL, also generate a formal letter.",
    )
    elapsed = time.time() - t0
    result.writer_output = WorkerOutput(
        agent_name="Writer", result=writer_output, tools_used=["generate_decision_letter"],
    )
    logger.info(f"{_G}[WRITER  ] ✓ Done in {elapsed:.1f}s{_X}")

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
    d = decision.get("decision", "?")
    result.agent_log.append(f"\n🟣 **Supervisor** — Final decision: {d}")
    logger.info(f"{_W}[SUPERVIS] ══ Decision: {d} | Confidence: {decision.get('confidence', '?')} ══{_X}")

    return result
