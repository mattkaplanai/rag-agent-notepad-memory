"""Summarize findings tool — compress research into structured format."""

import logging

from langchain_core.tools import tool

from app.config import (
    CLASSIFIER_MODEL,
    USE_OPENAI_FOR_AGENTS,
    OPENAI_AGENT_MODEL,
)

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """Summarize these research findings into a structured format.
Be concise. Keep only information relevant to deciding a refund case.

RESEARCH FINDINGS:
{findings}

OUTPUT FORMAT — use this exact structure:

## Key Regulations
- [regulation ID or name]: [one-sentence summary of the rule]

## How They Apply to This Case
- [bullet points explaining how each regulation applies to the specific facts]

## Gaps in Research
- [anything the research didn't cover, was uncertain about, or needs further investigation]
- Write "None identified" if research appears complete

## Precedents
- [any past decisions found, or "No past decisions checked" if none]

## Research Confidence
- HIGH / MEDIUM / LOW — with a brief justification (e.g., "HIGH — found primary regulation and confirmed exceptions")
"""


@tool
def summarize_findings(findings: str) -> str:
    """Summarize and structure your research findings before finishing.
    Use this as your FINAL step after all searches, lookups, and
    cross-references are complete. Pass ALL the regulations, precedents,
    and context you've gathered as a single text block.

    This produces a clean, structured summary that the Analyst agent
    can work with efficiently."""
    if not findings or not findings.strip():
        return "No findings to summarize."

    try:
        if USE_OPENAI_FOR_AGENTS:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=OPENAI_AGENT_MODEL, temperature=0, max_tokens=1500)
        else:
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(
                model=CLASSIFIER_MODEL, temperature=0, max_tokens=1500
            )

        prompt = SUMMARIZE_PROMPT.format(findings=findings[:6000])
        response = llm.invoke(prompt)
        return response.content

    except Exception as e:
        logger.error("summarize_findings error: %s", e)
        # Graceful degradation — return a simple truncated version
        return (
            "## Research Summary (auto-generated — summarizer unavailable)\n\n"
            + findings[:2000]
        )
