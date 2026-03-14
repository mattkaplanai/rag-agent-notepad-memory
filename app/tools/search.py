"""RAG search tool — searches DOT regulation documents."""

import json
from langchain_core.tools import tool


def make_search_tool(index):
    """Create a document search tool bound to the given index."""

    @tool
    def search_regulations(query: str) -> str:
        """Search DOT regulations and documents for information relevant to the query.
        Use this to look up specific rules, thresholds, or policies.
        Always search before making a decision — do not rely on memory alone."""
        if index is None:
            return "No document index available."
        from app.rag.retriever import hybrid_search
        result = hybrid_search(index, query, top_k=8)
        if not result.chunks:
            return "No relevant regulations found for this query."
        chunks_text = "\n\n---\n\n".join(
            f"[Source: {c.source_file} | Relevance: {c.rerank_score:.3f}]\n{c.content}"
            for c in result.chunks
        )
        return chunks_text

    return search_regulations


def get_researcher_tools(index):
    """Return all tools for the Researcher agent."""
    from app.tools.lookup import make_lookup_tool
    from app.tools.cross_reference import make_cross_reference_tool
    from app.tools.past_decisions import search_past_decisions
    from app.tools.summarize import summarize_findings

    return [
        make_search_tool(index),
        make_lookup_tool(index),
        make_cross_reference_tool(index),
        search_past_decisions,
        summarize_findings,
    ]


def get_all_tools(index):
    """Return all tools for the refund decision agent."""
    from app.tools.check_delay import check_delay_threshold
    from app.tools.check_baggage import check_baggage_threshold
    from app.tools.refund_calculator import calculate_refund
    from app.tools.timeline_calculator import calculate_refund_timeline
    from app.tools.letter import generate_decision_letter
    from app.tools.currency import convert_currency

    return [
        check_delay_threshold,
        check_baggage_threshold,
        calculate_refund,
        calculate_refund_timeline,
        generate_decision_letter,
        convert_currency,
        make_search_tool(index),
    ]
