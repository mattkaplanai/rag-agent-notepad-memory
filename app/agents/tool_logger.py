"""Shared tool-call logger for LangGraph agents."""

import logging

from langchain_core.callbacks import BaseCallbackHandler

from app.agents.ansi_colors import M, X

logger = logging.getLogger(__name__)


def make_tool_logger(label: str) -> BaseCallbackHandler:
    """Return a callback that logs each tool call with the given agent label."""
    class _ToolLogger(BaseCallbackHandler):
        def on_tool_start(self, serialized, input_str, **kwargs):
            name = serialized.get("name", "?")
            snippet = str(input_str)[:70].replace("\n", " ")
            logger.info(f"{M}[{label}]   🔧 Tool: {name}({snippet}){X}")
    return _ToolLogger()
