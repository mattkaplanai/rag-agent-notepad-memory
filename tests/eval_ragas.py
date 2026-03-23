"""RAGAS offline evaluation for the Researcher agent's RAG pipeline.

Usage (inside Docker):
    docker exec refund-gradio python tests/eval_ragas.py

Usage (local, with PYTHONPATH set):
    PYTHONPATH=. python tests/eval_ragas.py

Loads the 20-case golden dataset, runs the hybrid-search RAG pipeline on
each question, then scores with RAGAS faithfulness / answer_relevancy /
context_precision / context_recall.

Results are stored in:
  - PostgreSQL table `ragas_scores` (one row per run, JSON column with
    per-question details)
  - Langfuse dataset run (one score item per question, if LANGFUSE_* vars
    are set)

CREATE TABLE (run once, or let the script create it automatically):
    CREATE TABLE IF NOT EXISTS ragas_scores (
        id          SERIAL PRIMARY KEY,
        run_id      TEXT        NOT NULL,
        run_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        model_tag   TEXT,
        prompt_tag  TEXT,
        retrieval_tag TEXT,
        faithfulness      FLOAT,
        answer_relevancy  FLOAT,
        context_precision FLOAT,
        context_recall    FLOAT,
        details     JSONB
    );
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("eval_ragas")

# ---------------------------------------------------------------------------
# RAGAS imports
# ---------------------------------------------------------------------------
try:
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from datasets import Dataset
except ImportError as exc:
    sys.exit(
        f"Missing dependency: {exc}\n"
        "Run: pip install 'ragas>=0.1.0,<0.2.0' datasets"
    )

# ---------------------------------------------------------------------------
# LLM / embeddings for RAGAS judges
# ---------------------------------------------------------------------------
def _build_ragas_llm():
    """Return a RAGAS-wrapped LLM for the judge calls."""
    use_openai = os.getenv("USE_OPENAI_FOR_AGENTS", "false").lower() == "true"
    if use_openai:
        from langchain_openai import ChatOpenAI
        return LangchainLLMWrapper(
            ChatOpenAI(model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"), temperature=0)
        )
    from langchain_anthropic import ChatAnthropic
    return LangchainLLMWrapper(
        ChatAnthropic(
            model=os.getenv("RESEARCHER_MODEL", "claude-3-5-haiku-20241022"),
            temperature=0,
        )
    )


def _build_ragas_embeddings():
    from langchain_openai import OpenAIEmbeddings
    return LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
    )


# ---------------------------------------------------------------------------
# Golden dataset loader
# ---------------------------------------------------------------------------
GOLDEN_DATASET_PATH = Path(__file__).parent / "fixtures" / "golden_dataset.json"


def load_golden_dataset() -> list[dict]:
    with GOLDEN_DATASET_PATH.open() as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# RAG pipeline runner (Researcher only — isolated retrieval evaluation)
# ---------------------------------------------------------------------------
def run_rag_for_case(index, question: str, top_k: int = 5) -> tuple[list[str], str]:
    """Return (contexts, answer) for a single question using hybrid search.

    The answer is the concatenation of the top-2 chunks (≤1 000 chars) so
    that faithfulness measures whether the answer is grounded in retrieved
    context rather than measuring the full pipeline Writer output.
    """
    from app.rag.retriever import hybrid_search

    result = hybrid_search(index, question, top_k=top_k)
    contexts = [chunk.content for chunk in result.chunks]
    answer = " ".join(contexts[:2])[:1_000].strip()
    return contexts, answer


# ---------------------------------------------------------------------------
# PostgreSQL storage
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ragas_scores (
    id               SERIAL PRIMARY KEY,
    run_id           TEXT        NOT NULL,
    run_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_tag        TEXT,
    prompt_tag       TEXT,
    retrieval_tag    TEXT,
    faithfulness     FLOAT,
    answer_relevancy FLOAT,
    context_precision FLOAT,
    context_recall   FLOAT,
    details          JSONB
);
"""

_INSERT_SQL = """
INSERT INTO ragas_scores
    (run_id, run_at, model_tag, prompt_tag, retrieval_tag,
     faithfulness, answer_relevancy, context_precision, context_recall, details)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _store_postgres(run_id: str, aggregated: dict, per_question: list[dict]) -> None:
    db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not db_url:
        logger.warning("No DATABASE_URL/POSTGRES_DSN set — skipping PostgreSQL storage.")
        return

    try:
        import psycopg2

        conn = psycopg2.connect(db_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
                cur.execute(
                    _INSERT_SQL,
                    (
                        run_id,
                        datetime.now(timezone.utc),
                        os.getenv("MODEL_TAG", "default"),
                        os.getenv("PROMPT_TAG", "default"),
                        os.getenv("RETRIEVAL_TAG", "default"),
                        aggregated.get("faithfulness"),
                        aggregated.get("answer_relevancy"),
                        aggregated.get("context_precision"),
                        aggregated.get("context_recall"),
                        json.dumps(per_question),
                    ),
                )
        conn.close()
        logger.info("Scores stored in PostgreSQL (run_id=%s).", run_id)
    except Exception as exc:
        logger.warning("PostgreSQL storage failed: %s", exc)


# ---------------------------------------------------------------------------
# Langfuse storage
# ---------------------------------------------------------------------------
def _store_langfuse(run_id: str, aggregated: dict, per_question: list[dict]) -> None:
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not (pk and sk):
        logger.info("LANGFUSE_PUBLIC_KEY/SECRET_KEY not set — skipping Langfuse storage.")
        return

    try:
        from langfuse import Langfuse

        lf = Langfuse(public_key=pk, secret_key=sk, host=host)

        # Create a dataset run trace for this evaluation
        trace = lf.trace(
            name="ragas-eval",
            id=run_id,
            metadata={
                "model_tag": os.getenv("MODEL_TAG", "default"),
                "prompt_tag": os.getenv("PROMPT_TAG", "default"),
                "retrieval_tag": os.getenv("RETRIEVAL_TAG", "default"),
                "aggregated": aggregated,
            },
        )

        # Log aggregate scores as observations
        for metric_name, score in aggregated.items():
            if score is not None:
                lf.score(
                    trace_id=run_id,
                    name=f"ragas_{metric_name}",
                    value=score,
                    comment=f"RAGAS {metric_name} — run {run_id}",
                )

        # Log per-question details as individual spans
        for item in per_question:
            lf.span(
                trace_id=run_id,
                name=f"case_{item['id']}",
                metadata=item,
            )

        lf.flush()
        logger.info("Scores stored in Langfuse (run_id=%s).", run_id)
    except Exception as exc:
        logger.warning("Langfuse storage failed: %s", exc)


# ---------------------------------------------------------------------------
# Pretty-print results
# ---------------------------------------------------------------------------
def _print_results(run_id: str, aggregated: dict, per_question: list[dict]) -> None:
    print("\n" + "=" * 62)
    print(f"  RAGAS Evaluation Results  |  run_id: {run_id[:8]}...")
    print("=" * 62)
    print(f"  {'Metric':<22} {'Score':>8}  {'Meaning'}")
    print("  " + "-" * 58)

    metric_info = {
        "faithfulness":       "Answer grounded in retrieved docs?",
        "answer_relevancy":   "Retrieved content addresses the question?",
        "context_precision":  "Retrieved chunks are relevant (no noise)?",
        "context_recall":     "Ground truth covered by retrieved chunks?",
    }
    for metric, meaning in metric_info.items():
        score = aggregated.get(metric)
        score_str = f"{score:.3f}" if score is not None else "  N/A"
        flag = ""
        if score is not None:
            if score >= 0.8:
                flag = "✓"
            elif score >= 0.6:
                flag = "~"
            else:
                flag = "✗"
        print(f"  {metric:<22} {score_str:>8}  {flag}  {meaning}")

    print("=" * 62)

    # Verdict
    scores = [v for v in aggregated.values() if v is not None]
    if not scores:
        print("\n  No scores computed.")
        return

    if all(s >= 0.8 for s in scores):
        print("\n  VERDICT: RAG pipeline is performing well.")
    else:
        verdicts = []
        if aggregated.get("faithfulness", 1) < 0.8:
            verdicts.append(
                "  Faithfulness < 0.8 — model may be hallucinating beyond retrieved context."
            )
        if aggregated.get("answer_relevancy", 1) < 0.5:
            verdicts.append(
                "  Answer Relevancy < 0.5 — chunks are too verbose/noisy."
                " Consider reducing chunk size or TOP_K."
            )
        if aggregated.get("context_precision", 1) < 0.7:
            verdicts.append(
                "  Context Precision < 0.7 — retriever is pulling irrelevant chunks."
                " Tune BM25 weight or reduce RETRIEVAL_TOP_K."
            )
        if aggregated.get("context_recall", 1) < 0.7:
            verdicts.append(
                "  Context Recall < 0.7 — retriever is missing relevant chunks."
                " Consider expanding TOP_K or adding more documents."
            )
        print("\n  VERDICT:")
        for v in verdicts:
            print(v)

    print()


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------
def run_evaluation(top_k: int = 5) -> dict:
    """Run RAGAS evaluation over the 20-case golden dataset.

    Returns the aggregated score dict.
    """
    run_id = str(uuid.uuid4())
    logger.info("Starting RAGAS evaluation | run_id=%s | top_k=%d", run_id, top_k)

    # Build RAG index
    logger.info("Building / loading RAG index...")
    from app.rag.indexer import build_or_load_index
    index = build_or_load_index()

    # Configure RAGAS judges
    logger.info("Configuring RAGAS judge LLM and embeddings...")
    ragas_llm = _build_ragas_llm()
    ragas_emb = _build_ragas_embeddings()
    faithfulness.llm = ragas_llm
    answer_relevancy.llm = ragas_llm
    answer_relevancy.embeddings = ragas_emb
    context_precision.llm = ragas_llm
    context_recall.llm = ragas_llm

    # Load golden dataset
    cases = load_golden_dataset()
    logger.info("Loaded %d golden cases from %s", len(cases), GOLDEN_DATASET_PATH)

    questions, answers, contexts_list, ground_truths = [], [], [], []
    per_question: list[dict] = []

    for case in cases:
        qid = case["id"]
        question = case["question"]
        ground_truth = case["ground_truth"]

        logger.info("[%02d/%02d] Retrieving: %s...", qid, len(cases), question[:60])
        try:
            contexts, answer = run_rag_for_case(index, question, top_k=top_k)
        except Exception as exc:
            logger.warning("Case %d retrieval failed: %s", qid, exc)
            contexts, answer = [], ""

        questions.append(question)
        answers.append(answer)
        contexts_list.append(contexts)
        ground_truths.append(ground_truth)

        per_question.append(
            {
                "id": qid,
                "category": case.get("category", ""),
                "question": question,
                "answer": answer[:500],
                "context_count": len(contexts),
                "ground_truth": ground_truth,
            }
        )

    # Build HuggingFace Dataset
    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts_list,
            "ground_truth": ground_truths,
        }
    )

    logger.info("Running RAGAS evaluation on %d cases...", len(cases))
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )

    # Aggregate scores
    scores_list = result.scores  # list of dicts, one per row
    def _avg(metric_key: str) -> float | None:
        vals = [s[metric_key] for s in scores_list if s.get(metric_key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    aggregated = {
        "faithfulness":       _avg("faithfulness"),
        "answer_relevancy":   _avg("answer_relevancy"),
        "context_precision":  _avg("context_precision"),
        "context_recall":     _avg("context_recall"),
    }

    # Enrich per_question with individual scores
    for i, item in enumerate(per_question):
        row_scores = scores_list[i] if i < len(scores_list) else {}
        item["scores"] = {
            k: round(v, 4) for k, v in row_scores.items() if v is not None
        }

    # Print
    _print_results(run_id, aggregated, per_question)

    # Store
    _store_postgres(run_id, aggregated, per_question)
    _store_langfuse(run_id, aggregated, per_question)

    return aggregated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAGAS offline evaluation")
    parser.add_argument(
        "--top-k", type=int, default=5,
        help="Number of chunks to retrieve per question (default: 5)"
    )
    args = parser.parse_args()
    run_evaluation(top_k=args.top_k)
