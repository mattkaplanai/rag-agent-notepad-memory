"""RAG search tool — searches DOT regulation documents."""

import json
from langchain_core.tools import tool

# Source file keywords for filtering by document type
_FEDERAL_KEYWORDS = ("14 cfr", "2024-07177", "usdot_automatic", "usdot_aviation")
_COMMITMENT_KEYWORDS = ("commitment", "customer_service", "customer service")


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


def make_federal_regs_tool(index):
    """Create a search tool filtered to DOT federal regulation documents only."""

    @tool
    def search_federal_regulations(query: str) -> str:
        """Search DOT federal regulations only (14 CFR Part 259, USDOT Automatic Refund Rule).
        Use this to find statutory thresholds, federal rules, and legal requirements."""
        if index is None:
            return "No document index available."
        from app.rag.retriever import hybrid_search
        result = hybrid_search(index, query, top_k=12)
        chunks = [
            c for c in result.chunks
            if any(kw in c.source_file.lower() for kw in _FEDERAL_KEYWORDS)
        ]
        if not chunks:
            return "No federal regulation documents found for this query."
        return "\n\n---\n\n".join(
            f"[Source: {c.source_file} | Relevance: {c.rerank_score:.3f}]\n{c.content}"
            for c in chunks[:6]
        )

    return search_federal_regulations


def make_commitments_tool(index):
    """Create a search tool filtered to airline customer service commitments only."""

    @tool
    def search_airline_commitments(query: str) -> str:
        """Search airline customer service commitments and voluntary policies.
        Use this to find what airlines have committed to beyond federal requirements."""
        if index is None:
            return "No document index available."
        from app.rag.retriever import hybrid_search
        result = hybrid_search(index, query, top_k=12)
        chunks = [
            c for c in result.chunks
            if any(kw in c.source_file.lower() for kw in _COMMITMENT_KEYWORDS)
        ]
        if not chunks:
            return "No airline commitment documents found for this query."
        return "\n\n---\n\n".join(
            f"[Source: {c.source_file} | Relevance: {c.rerank_score:.3f}]\n{c.content}"
            for c in chunks[:6]
        )

    return search_airline_commitments


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
