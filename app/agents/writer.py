"""Writer agent — drafts the final decision and formal letter."""

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.config import LLM_MODEL, SPECIALIST_TEMPERATURE
from app.prompts.writer import WRITER_PROMPT
from app.tools.letter import generate_decision_letter


def build_writer():
    """Build the Writer agent with the letter generator tool."""
    llm = ChatOpenAI(model=LLM_MODEL, temperature=SPECIALIST_TEMPERATURE)
    return create_react_agent(llm, [generate_decision_letter], prompt=WRITER_PROMPT)


def run_writer(agent, task: str) -> str:
    """Run the Writer agent and return its output."""
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""
