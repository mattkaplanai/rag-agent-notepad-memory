"""Researcher agent — finds applicable DOT regulations."""

from langgraph.prebuilt import create_react_agent

from app.config import (
    RESEARCHER_MODEL,
    SPECIALIST_TEMPERATURE,
    USE_OPENAI_FOR_AGENTS,
    OPENAI_AGENT_MODEL,
)
from app.prompts.researcher import RESEARCHER_PROMPT
from app.tools.search import make_search_tool


def build_researcher(index):
    """Build the Researcher agent with the search_regulations tool."""
    if USE_OPENAI_FOR_AGENTS:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=SPECIALIST_TEMPERATURE)
    else:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=RESEARCHER_MODEL, temperature=SPECIALIST_TEMPERATURE)
    search_tool = make_search_tool(index)
    return create_react_agent(llm, [search_tool], prompt=RESEARCHER_PROMPT)


def run_researcher(agent, task: str) -> str:
    """Run the Researcher agent and return its output."""
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""
