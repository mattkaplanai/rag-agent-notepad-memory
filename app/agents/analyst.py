"""Analyst agent — checks thresholds and calculates refunds."""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.config import LLM_MODEL, SPECIALIST_TEMPERATURE
from app.prompts.analyst import ANALYST_PROMPT
from app.tools.check_delay import check_delay_threshold
from app.tools.check_baggage import check_baggage_threshold
from app.tools.refund_calculator import calculate_refund
from app.tools.timeline_calculator import calculate_refund_timeline


def build_analyst():
    """Build the Analyst agent with threshold + calculator tools."""
    llm = ChatOpenAI(model=LLM_MODEL, temperature=SPECIALIST_TEMPERATURE)
    tools = [check_delay_threshold, check_baggage_threshold, calculate_refund, calculate_refund_timeline]
    return create_react_agent(llm, tools, prompt=ANALYST_PROMPT)


def run_analyst(agent, task: str) -> str:
    """Run the Analyst agent and return its output."""
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""
