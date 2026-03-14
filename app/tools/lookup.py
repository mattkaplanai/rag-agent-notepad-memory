"""Direct regulation lookup tool — fetch a specific regulation by section ID."""

from langchain_core.tools import tool


def make_lookup_tool(index):
    """Create a regulation lookup tool bound to the given index."""

    @tool
    def lookup_regulation(section_id: str) -> str:
        """Look up a specific regulation by its exact section ID or number.
        Examples: '14 CFR 260.5', 'CFR 259.4', 'Part 260'.
        Use this when you already know the regulation number — it is faster and
        more precise than search_regulations. Use search_regulations for broad
        topic searches when you don't know the exact section."""
        if index is None:
            return "No document index available."
        from app.rag.retriever import hybrid_search

        # Use a small top_k — we want precision, not recall
        result = hybrid_search(index, section_id, top_k=3)
        if not result.chunks:
            return f"No regulation found matching '{section_id}'."

        best = result.chunks[0]
        if best.rerank_score < 0.25:
            return (
                f"No exact match for '{section_id}'. "
                f"Closest result (low confidence):\n"
                f"[Source: {best.source_file} | Relevance: {best.rerank_score:.3f}]\n"
                f"{best.content[:500]}"
            )

        return "\n\n---\n\n".join(
            f"[Source: {c.source_file} | Relevance: {c.rerank_score:.3f}]\n{c.content}"
            for c in result.chunks
        )

    return lookup_regulation
