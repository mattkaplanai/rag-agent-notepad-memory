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


def get_all_tools(index):
    """Return all tools for the refund decision agent."""
    from app.tools.threshold import check_delay_threshold, check_baggage_threshold
    from app.tools.calculator import calculate_refund, calculate_refund_timeline
    from app.tools.letter import generate_decision_letter

    return [
        check_delay_threshold,
        check_baggage_threshold,
        calculate_refund,
        calculate_refund_timeline,
        generate_decision_letter,
        make_search_tool(index),
    ]
