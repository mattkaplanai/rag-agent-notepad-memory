"""Researcher agent — finds applicable DOT regulations using multiple tools.

Supports two modes:
  - Single agent (build_researcher): original single-pass agent with all tools.
  - Parallel subagents (build_researcher_parallel): three specialized agents that
    run concurrently and whose results are merged before being passed to the Analyst.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.prebuilt import create_react_agent

from app.agents.tool_logger import make_tool_logger
from app.agents.retry import invoke_with_retry
from app.tracing import get_langfuse_callback

logger = logging.getLogger(__name__)

from app.config import (
    RESEARCHER_MODEL,
    SPECIALIST_TEMPERATURE,
    USE_OPENAI_FOR_AGENTS,
    OPENAI_AGENT_MODEL,
)
from app.prompts.researcher import (
    RESEARCHER_PROMPT,
    FEDERAL_RESEARCHER_PROMPT,
    PRECEDENT_RESEARCHER_PROMPT,
    COMMITMENTS_RESEARCHER_PROMPT,
)
from app.tools.search import get_researcher_tools


def _make_llm():
    if USE_OPENAI_FOR_AGENTS:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=SPECIALIST_TEMPERATURE)
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=RESEARCHER_MODEL, temperature=SPECIALIST_TEMPERATURE)


# ── Single agent (original) ───────────────────────────────────────────────────

def build_researcher(index):
    """Build the original single-pass Researcher agent with all tools."""
    tools = get_researcher_tools(index)
    return create_react_agent(_make_llm(), tools, prompt=RESEARCHER_PROMPT)


def run_researcher(agent, task: str) -> str:
    """Run the Researcher agent and return its output."""
    callbacks = [make_tool_logger("RESEARCH")]
    lf = get_langfuse_callback()
    if lf:
        callbacks.append(lf)
    result = invoke_with_retry(
        lambda: agent.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"callbacks": callbacks},
        ),
        label="Researcher",
    )
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""


# ── Parallel subagents ────────────────────────────────────────────────────────

def build_researcher_parallel(index):
    """Build three specialized researcher subagents that run in parallel.

    Returns a tuple of (federal_agent, precedent_agent, commitments_agent).

    Subagent A — Federal Regulations:
        Searches 14 CFR Part 259 and USDOT Automatic Refund Rule documents only.
        Tools: search_federal_regulations, lookup_regulation, cross_reference

    Subagent B — Past Decisions:
        Queries PostgreSQL for historical refund decision precedents.
        Tools: search_past_decisions

    Subagent C — Airline Commitments:
        Searches Airline Customer Service Commitments document only.
        Tools: search_airline_commitments
    """
    from app.tools.search import make_federal_regs_tool, make_commitments_tool
    from app.tools.lookup import make_lookup_tool
    from app.tools.cross_reference import make_cross_reference_tool
    from app.tools.past_decisions import search_past_decisions

    federal_agent = create_react_agent(
        _make_llm(),
        [make_federal_regs_tool(index), make_lookup_tool(index), make_cross_reference_tool(index)],
        prompt=FEDERAL_RESEARCHER_PROMPT,
    )
    precedent_agent = create_react_agent(
        _make_llm(),
        [search_past_decisions],
        prompt=PRECEDENT_RESEARCHER_PROMPT,
    )
    commitments_agent = create_react_agent(
        _make_llm(),
        [make_commitments_tool(index)],
        prompt=COMMITMENTS_RESEARCHER_PROMPT,
    )
    return federal_agent, precedent_agent, commitments_agent


def _run_subagent(agent, task: str, label: str) -> str:
    """Run a single subagent and return its last message content."""
    callbacks = [make_tool_logger(label)]
    lf = get_langfuse_callback()
    if lf:
        callbacks.append(lf)
    try:
        result = invoke_with_retry(
            lambda: agent.invoke(
                {"messages": [{"role": "user", "content": task}]},
                config={"callbacks": callbacks},
            ),
            label=label,
        )
        messages = result.get("messages", [])
        return messages[-1].content if messages else ""
    except Exception as e:
        logger.warning("[%s] subagent failed: %s", label, e)
        return f"[{label}] No results (error: {e})"


def run_researcher_parallel(agents_tuple, task: str) -> str:
    """Run three researcher subagents in parallel and merge their outputs.

    Each subagent searches a different source concurrently:
      - Federal agent  → DOT federal regulations
      - Precedent agent → past decisions in PostgreSQL
      - Commitments agent → airline customer service commitments

    Returns a single merged string with clearly labelled sections.
    """
    federal_agent, precedent_agent, commitments_agent = agents_tuple

    # Extract case context for targeted subagent tasks
    federal_task = (
        f"Search DOT federal regulations (14 CFR Part 259, USDOT Automatic Refund Rule) "
        f"for rules that apply to this case:\n\n{task}"
    )
    precedent_task = (
        f"Search the past decisions database for historical precedents matching this case type. "
        f"Extract the case type from the case below and query past decisions for it:\n\n{task}"
    )
    commitments_task = (
        f"Search airline customer service commitments for policies that apply to this case:\n\n{task}"
    )

    subagents = [
        (federal_agent,     federal_task,     "FEDERAL-REGS"),
        (precedent_agent,   precedent_task,   "PRECEDENTS"),
        (commitments_agent, commitments_task, "COMMITMENTS"),
    ]

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_subagent, agent, t, label): label
            for agent, t, label in subagents
        }
        for future in as_completed(futures):
            label = futures[future]
            results[label] = future.result()

    logger.info("[RESEARCH] All 3 subagents completed.")

    merged = (
        "═══ FEDERAL REGULATIONS (14 CFR Part 259 / USDOT Rules) ═══\n\n"
        + results.get("FEDERAL-REGS", "No federal regulations found.")
        + "\n\n"
        "═══ PAST DECISIONS (PostgreSQL Precedents) ═══\n\n"
        + results.get("PRECEDENTS", "No past decisions found.")
        + "\n\n"
        "═══ AIRLINE CUSTOMER SERVICE COMMITMENTS ═══\n\n"
        + results.get("COMMITMENTS", "No airline commitments found.")
    )
    return merged
