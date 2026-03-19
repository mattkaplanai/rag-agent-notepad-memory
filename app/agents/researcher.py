"""Researcher agent — finds applicable DOT regulations using multiple tools."""

import logging

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
from app.prompts.researcher import RESEARCHER_PROMPT
from app.tools.search import get_researcher_tools


def build_researcher(index):
    """Build the Researcher agent with the full research toolset.

    Tools:
      - search_regulations: broad semantic + keyword search across documents
      - lookup_regulation: precise lookup by regulation section ID (e.g., '14 CFR 260.5')
      - cross_reference: find related/referenced regulations from text
      - search_past_decisions: query past refund decisions from PostgreSQL
      - summarize_findings: compress research into structured output
    """
    if USE_OPENAI_FOR_AGENTS:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=SPECIALIST_TEMPERATURE)
    else:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=RESEARCHER_MODEL, temperature=SPECIALIST_TEMPERATURE)

    tools = get_researcher_tools(index)
    return create_react_agent(llm, tools, prompt=RESEARCHER_PROMPT)


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
