"""Cross-reference tool — given regulation text, find related/referenced regulations."""

import re

from langchain_core.tools import tool

# Pattern to extract CFR section references from regulation text
CFR_PATTERN = re.compile(
    r"(?:14\s*CFR\s*(?:Part\s*)?\d+(?:\.\d+)?)", re.IGNORECASE
)


def make_cross_reference_tool(index):
    """Create a cross-reference tool bound to the given index."""

    @tool
    def cross_reference(regulation_text: str) -> str:
        """Given regulation text you already found, discover related regulations
        that are referenced or connected. Pass the text of a regulation and this
        tool will extract CFR section references (e.g., '14 CFR 259.4') from it
        and look them up. Also finds semantically related regulations.
        Use this AFTER finding a primary regulation to ensure you haven't missed
        connected rules."""
        if index is None:
            return "No document index available."
        from app.rag.retriever import hybrid_search

        # Extract explicit CFR references from the text
        references = list(set(CFR_PATTERN.findall(regulation_text)))

        results = []

        # Look up each explicit reference
        if references:
            for ref in references[:5]:
                result = hybrid_search(index, ref, top_k=2)
                if result.chunks:
                    best = result.chunks[0]
                    if best.rerank_score >= 0.25:
                        results.append(
                            f"### Referenced: {ref}\n"
                            f"[Source: {best.source_file} | Relevance: {best.rerank_score:.3f}]\n"
                            f"{best.content[:500]}"
                        )

        # Also do a semantic search for related regulations
        snippet = regulation_text[:300].replace("\n", " ")
        semantic_result = hybrid_search(
            index, f"regulations related to: {snippet}", top_k=4
        )
        if semantic_result.chunks:
            for chunk in semantic_result.chunks:
                # Avoid duplicating content already found via explicit refs
                chunk_preview = chunk.content[:100]
                already_found = any(chunk_preview in r for r in results)
                if not already_found and chunk.rerank_score >= 0.30:
                    results.append(
                        f"### Related regulation\n"
                        f"[Source: {chunk.source_file} | Relevance: {chunk.rerank_score:.3f}]\n"
                        f"{chunk.content[:500]}"
                    )

        if not results:
            refs_note = f" (extracted references: {', '.join(references)})" if references else ""
            return f"No cross-references found{refs_note}."

        header = (
            f"Found {len(results)} cross-referenced/related regulations"
            + (f" (explicit refs: {', '.join(references)})" if references else "")
            + ":\n\n"
        )
        return header + "\n\n---\n\n".join(results)

    return cross_reference
