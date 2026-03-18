"""Writer agent — drafts the final decision and formal letter."""

from langgraph.prebuilt import create_react_agent

from app.agents.tool_logger import make_tool_logger
from app.agents.retry import invoke_with_retry
from app.config import (
    LLM_MODEL,
    SPECIALIST_TEMPERATURE,
    USE_OPENAI_FOR_AGENTS,
    OPENAI_AGENT_MODEL,
)
from app.prompts.writer import WRITER_PROMPT
from app.tools.letter import generate_decision_letter


def build_writer():
    """Build the Writer agent with the letter generator tool."""
    if USE_OPENAI_FOR_AGENTS:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=SPECIALIST_TEMPERATURE)
    else:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=LLM_MODEL, temperature=SPECIALIST_TEMPERATURE)
    return create_react_agent(llm, [generate_decision_letter], prompt=WRITER_PROMPT)


def run_writer(agent, task: str) -> str:
    """Run the Writer agent and return its output."""
    result = invoke_with_retry(
        lambda: agent.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"callbacks": [make_tool_logger("WRITER  ")]},
        ),
        label="Writer",
    )
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""
