"""
Advanced RAG: Hybrid Search + Re-Ranking + Source Citations

Step 2 of the learning roadmap.

Demonstrates:
  - Hybrid Search: BM25 keyword search + vector search combined via
    Reciprocal Rank Fusion (RRF) for better recall
  - Re-Ranking: Score each retrieved chunk against the query using
    embedding similarity for better precision
  - Source Citations: Track which document and section each chunk came from
  - Retrieval Dashboard: Show what context was retrieved with scores
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi


@dataclass
class RetrievedChunk:
    """A single retrieved chunk with metadata for citation tracking."""
    content: str
    source_file: str
    relevance_score: float = 0.0
    retrieval_method: str = ""    # "vector", "bm25", or "hybrid"
    vector_rank: int | None = None
    bm25_rank: int | None = None
    rerank_score: float = 0.0


@dataclass
class RetrievalResult:
    """Complete retrieval result with chunks and diagnostics."""
    chunks: list[RetrievedChunk] = field(default_factory=list)
    query: str = ""
    vector_count: int = 0
    bm25_count: int = 0
    hybrid_count: int = 0
    reranked: bool = False

    @property
    def context_text(self) -> str:
        return "\n\n".join(c.content for c in self.chunks)

    @property
    def citation_summary(self) -> list[dict]:
        seen = set()
        citations = []
        for c in self.chunks:
            if c.source_file not in seen:
                seen.add(c.source_file)
                citations.append({
                    "source": c.source_file,
                    "relevance": round(c.rerank_score or c.relevance_score, 3),
                    "method": c.retrieval_method,
                })
        return citations


def _extract_source(node) -> str:
    """Extract a readable source name from a LlamaIndex node."""
    meta = node.metadata if hasattr(node, "metadata") else {}
    source = meta.get("file_name", meta.get("source", "unknown"))
    return Path(source).name if source else "unknown"


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    return re.findall(r"\w+", text.lower())


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return float(dot / norm) if norm > 0 else 0.0


# ── Hybrid Search ────────────────────────────────────────────────────────────
#
# WHY HYBRID?
#
# Vector search is great at understanding meaning:
#   "flight was called off" → finds "cancelled flight" (semantically similar)
#
# But vector search can MISS exact terms:
#   "14 CFR Part 259" → might not match well semantically
#   "3 hours" → embedding doesn't understand numeric thresholds
#
# BM25 keyword search catches exact matches but misses synonyms:
#   "cancelled" finds "cancelled" but NOT "called off"
#
# HYBRID = both combined. Best of both worlds.
#
# We merge results using Reciprocal Rank Fusion (RRF):
#   score = sum( 1 / (k + rank) ) across both search methods
#   This gives high scores to chunks that rank well in EITHER method.
# ─────────────────────────────────────────────────────────────────────────────

def _reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, any]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """
    Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.

    Each list contains (id, item) tuples in ranked order.
    Returns (id, rrf_score) sorted by fused score descending.
    """
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked_list, 1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_search(
    index,
    query: str,
    top_k: int = 8,
    vector_k: int = 12,
    bm25_k: int = 12,
) -> RetrievalResult:
    """
    Perform hybrid search: vector + BM25, merged with RRF, then re-ranked.

    Steps:
      1. Vector search via LlamaIndex (semantic similarity)
      2. BM25 keyword search over all document chunks
      3. Reciprocal Rank Fusion to merge both result sets
      4. Re-rank top candidates using embedding cosine similarity
      5. Return top_k chunks with source citations
    """
    result = RetrievalResult(query=query)

    if index is None:
        return result

    # ── Step 1: Vector search ────────────────────────────────────────────
    retriever = index.as_retriever(similarity_top_k=vector_k)
    vector_nodes = retriever.retrieve(query)
    result.vector_count = len(vector_nodes)

    vector_chunks: dict[str, RetrievedChunk] = {}
    vector_ranked: list[tuple[str, any]] = []
    for rank, node in enumerate(vector_nodes):
        content = node.get_content()
        chunk_id = str(hash(content))
        source = _extract_source(node)
        chunk = RetrievedChunk(
            content=content,
            source_file=source,
            relevance_score=float(node.score) if hasattr(node, "score") and node.score else 0.0,
            retrieval_method="vector",
            vector_rank=rank + 1,
        )
        vector_chunks[chunk_id] = chunk
        vector_ranked.append((chunk_id, chunk))

    # ── Step 2: BM25 keyword search ─────────────────────────────────────
    all_nodes = _get_all_nodes(index)
    bm25_chunks: dict[str, RetrievedChunk] = {}
    bm25_ranked: list[tuple[str, any]] = []

    if all_nodes:
        corpus_tokens = [_tokenize(n["content"]) for n in all_nodes]
        bm25 = BM25Okapi(corpus_tokens)
        query_tokens = _tokenize(query)
        bm25_scores = bm25.get_scores(query_tokens)

        scored_indices = sorted(
            enumerate(bm25_scores), key=lambda x: x[1], reverse=True
        )[:bm25_k]

        for rank, (idx, score) in enumerate(scored_indices):
            if score <= 0:
                continue
            node_data = all_nodes[idx]
            content = node_data["content"]
            chunk_id = str(hash(content))
            chunk = RetrievedChunk(
                content=content,
                source_file=node_data["source"],
                relevance_score=float(score),
                retrieval_method="bm25",
                bm25_rank=rank + 1,
            )
            bm25_chunks[chunk_id] = chunk
            bm25_ranked.append((chunk_id, chunk))

    result.bm25_count = len(bm25_ranked)

    # ── Step 3: Reciprocal Rank Fusion ───────────────────────────────────
    fused = _reciprocal_rank_fusion([vector_ranked, bm25_ranked])

    all_chunks = {**vector_chunks, **bm25_chunks}
    merged: list[RetrievedChunk] = []
    for chunk_id, rrf_score in fused:
        chunk = all_chunks.get(chunk_id)
        if chunk is None:
            continue

        if chunk_id in vector_chunks and chunk_id in bm25_chunks:
            chunk.retrieval_method = "hybrid (vector + bm25)"
            chunk.bm25_rank = bm25_chunks[chunk_id].bm25_rank
        chunk.relevance_score = rrf_score
        merged.append(chunk)

    result.hybrid_count = len(merged)

    # ── Step 4: Re-rank using embedding similarity ───────────────────────
    reranked = _rerank_chunks(query, merged[:top_k * 2])
    result.reranked = True

    # ── Step 5: Return top_k with citations ──────────────────────────────
    result.chunks = reranked[:top_k]
    return result


def _get_all_nodes(index) -> list[dict]:
    """Extract all document chunks from the index for BM25 search."""
    try:
        docstore = index.storage_context.docstore
        nodes = []
        for node_id, node in docstore.docs.items():
            content = node.get_content() if hasattr(node, "get_content") else str(node)
            source = "unknown"
            if hasattr(node, "metadata") and node.metadata:
                source = Path(node.metadata.get("file_name", "unknown")).name
            nodes.append({"content": content, "source": source, "id": node_id})
        return nodes
    except Exception:
        return []


def _rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """
    Re-rank chunks using embedding cosine similarity.

    WHY RE-RANK?
    Initial retrieval (vector search, BM25) uses fast but approximate
    scoring. Re-ranking uses a more expensive but more accurate comparison:
    embed the query and each chunk, then compute cosine similarity.

    This catches cases where a chunk ranked #8 by vector search is actually
    the most relevant one when compared more carefully.
    """
    if not chunks:
        return chunks

    from openai import OpenAI
    client = OpenAI()

    texts_to_embed = [query] + [c.content[:500] for c in chunks]
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    response = client.embeddings.create(input=texts_to_embed, model=model)
    embeddings = [d.embedding for d in response.data]
    query_emb = embeddings[0]
    chunk_embs = embeddings[1:]

    for chunk, emb in zip(chunks, chunk_embs):
        chunk.rerank_score = _cosine_similarity(query_emb, emb)

    chunks.sort(key=lambda c: c.rerank_score, reverse=True)
    return chunks


# ── Formatting for UI ────────────────────────────────────────────────────────

def format_retrieval_dashboard(result: RetrievalResult) -> str:
    """Format retrieval results as a readable Markdown dashboard."""
    lines = [
        "## 📡 Retrieval Dashboard",
        "",
        f"**Query:** {result.query[:100]}{'...' if len(result.query) > 100 else ''}",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Vector search results | {result.vector_count} |",
        f"| BM25 keyword results | {result.bm25_count} |",
        f"| After fusion (RRF) | {result.hybrid_count} |",
        f"| Final (re-ranked) | {len(result.chunks)} |",
        f"| Re-ranking applied | {'Yes' if result.reranked else 'No'} |",
        "",
        "### 📚 Sources Used",
        "",
    ]

    for citation in result.citation_summary:
        lines.append(
            f"- **{citation['source']}** — relevance: {citation['relevance']:.3f} "
            f"({citation['method']})"
        )

    lines += ["", "### 📄 Retrieved Chunks (ranked by relevance)", ""]

    for i, chunk in enumerate(result.chunks, 1):
        preview = chunk.content[:200].replace("\n", " ")
        method_badge = {
            "vector": "🔵 Vector",
            "bm25": "🟡 BM25",
            "hybrid (vector + bm25)": "🟢 Hybrid",
        }.get(chunk.retrieval_method, chunk.retrieval_method)

        rank_info = []
        if chunk.vector_rank:
            rank_info.append(f"vec #{chunk.vector_rank}")
        if chunk.bm25_rank:
            rank_info.append(f"bm25 #{chunk.bm25_rank}")
        rank_str = f" ({', '.join(rank_info)})" if rank_info else ""

        lines.append(
            f"**{i}.** {method_badge}{rank_str} — "
            f"rerank: {chunk.rerank_score:.3f} — "
            f"from *{chunk.source_file}*"
        )
        lines.append(f"> {preview}...")
        lines.append("")

    return "\n".join(lines)
