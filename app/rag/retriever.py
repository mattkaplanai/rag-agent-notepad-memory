"""
Advanced retriever: hybrid search (BM25 + vector) + re-ranking + citations.
"""

import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import EMBEDDING_MODEL, EMBEDDING_TIMEOUT, VECTOR_SEARCH_K, BM25_SEARCH_K
from app.models.schemas import RetrievedChunk, RetrievalResult
from app.utils import cosine_similarity


def _extract_source(node) -> str:
    meta = node.metadata if hasattr(node, "metadata") else {}
    source = meta.get("file_name", meta.get("source", "unknown"))
    return Path(source).name if source else "unknown"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _reciprocal_rank_fusion(ranked_lists, k=60):
    scores = {}
    for ranked_list in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked_list, 1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# Cache the docstore nodes so we don't rescan on every query (#7)
_bm25_cache: dict = {}


def _get_all_nodes_cached(index):
    """Get all nodes from docstore, cached by index id to avoid repeated scans."""
    index_id = id(index)
    if index_id in _bm25_cache:
        return _bm25_cache[index_id]

    try:
        docstore = index.storage_context.docstore
        nodes = []
        for node_id, node in docstore.docs.items():
            content = node.get_content() if hasattr(node, "get_content") else str(node)
            source = "unknown"
            if hasattr(node, "metadata") and node.metadata:
                source = Path(node.metadata.get("file_name", "unknown")).name
            nodes.append({"content": content, "source": source, "id": node_id})
        _bm25_cache[index_id] = nodes
        return nodes
    except Exception:
        return []


def _rerank_chunks(query, chunks):
    if not chunks:
        return chunks

    from openai import OpenAI
    client = OpenAI(timeout=EMBEDDING_TIMEOUT)
    texts_to_embed = [query] + [c.content[:500] for c in chunks]
    response = client.embeddings.create(input=texts_to_embed, model=EMBEDDING_MODEL)
    embeddings = [d.embedding for d in response.data]
    query_emb = embeddings[0]

    for chunk, emb in zip(chunks, embeddings[1:]):
        chunk.rerank_score = cosine_similarity(query_emb, emb)

    chunks.sort(key=lambda c: c.rerank_score, reverse=True)
    return chunks


def hybrid_search(index, query, top_k=8, vector_k=None, bm25_k=None):
    """Hybrid search: vector + BM25, merged with RRF, then re-ranked."""
    vector_k = vector_k or VECTOR_SEARCH_K
    bm25_k = bm25_k or BM25_SEARCH_K
    result = RetrievalResult(query=query)

    if index is None:
        return result

    # Vector search
    retriever = index.as_retriever(similarity_top_k=vector_k)
    vector_nodes = retriever.retrieve(query)
    result.vector_count = len(vector_nodes)

    vector_chunks = {}
    vector_ranked = []
    for rank, node in enumerate(vector_nodes):
        content = node.get_content()
        chunk_id = str(hash(content))
        chunk = RetrievedChunk(
            content=content, source_file=_extract_source(node),
            relevance_score=float(node.score) if hasattr(node, "score") and node.score else 0.0,
            retrieval_method="vector", vector_rank=rank + 1,
        )
        vector_chunks[chunk_id] = chunk
        vector_ranked.append((chunk_id, chunk))

    # BM25 search (uses cached nodes)
    all_nodes = _get_all_nodes_cached(index)
    bm25_chunks = {}
    bm25_ranked = []

    if all_nodes:
        corpus_tokens = [_tokenize(n["content"]) for n in all_nodes]
        bm25 = BM25Okapi(corpus_tokens)
        bm25_scores = bm25.get_scores(_tokenize(query))
        scored_indices = sorted(enumerate(bm25_scores), key=lambda x: x[1], reverse=True)[:bm25_k]

        for rank, (idx, score) in enumerate(scored_indices):
            if score <= 0:
                continue
            node_data = all_nodes[idx]
            content = node_data["content"]
            chunk_id = str(hash(content))
            chunk = RetrievedChunk(
                content=content, source_file=node_data["source"],
                relevance_score=float(score), retrieval_method="bm25", bm25_rank=rank + 1,
            )
            bm25_chunks[chunk_id] = chunk
            bm25_ranked.append((chunk_id, chunk))

    result.bm25_count = len(bm25_ranked)

    # RRF merge
    fused = _reciprocal_rank_fusion([vector_ranked, bm25_ranked])
    all_chunks = {**vector_chunks, **bm25_chunks}
    merged = []
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

    # Re-rank
    reranked = _rerank_chunks(query, merged[:top_k * 2])
    result.reranked = True
    result.chunks = reranked[:top_k]
    return result


def format_retrieval_dashboard(result):
    lines = [
        "## Retrieval Dashboard", "",
        f"**Query:** {result.query[:100]}{'...' if len(result.query) > 100 else ''}",
        "", "| Metric | Count |", "|--------|-------|",
        f"| Vector search results | {result.vector_count} |",
        f"| BM25 keyword results | {result.bm25_count} |",
        f"| After fusion (RRF) | {result.hybrid_count} |",
        f"| Final (re-ranked) | {len(result.chunks)} |",
        f"| Re-ranking applied | {'Yes' if result.reranked else 'No'} |",
        "", "### Sources Used", "",
    ]
    for citation in result.citation_summary:
        lines.append(f"- **{citation['source']}** -- relevance: {citation['relevance']:.3f} ({citation['method']})")

    lines += ["", "### Retrieved Chunks", ""]
    for i, chunk in enumerate(result.chunks, 1):
        preview = chunk.content[:200].replace("\n", " ")
        badge = {"vector": "[V]", "bm25": "[B]", "hybrid (vector + bm25)": "[H]"}.get(chunk.retrieval_method, "[?]")
        lines.append(f"**{i}.** {badge} rerank: {chunk.rerank_score:.3f} -- *{chunk.source_file}*")
        lines.append(f"> {preview}...")
        lines.append("")

    return "\n".join(lines)
