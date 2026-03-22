# CLAUDE.md — Airlines Refund Multi-Agent System

## What this project does

An AI-powered airline refund decision system. A passenger describes their situation, and a multi-agent pipeline (Classifier → Researcher → Analyst → Writer → Judge) decides whether they're entitled to a refund under DOT regulations, calculates the amount, and generates a formal request letter.

Outputs: **APPROVED / DENIED / PARTIAL** + reasons + formal letter + applicable regulations.

---

## How to run

```bash
docker compose up --build        # first time (builds images, ~2 min index build)
docker compose up -d             # subsequent runs
```

| Service | URL |
|---|---|
| Gradio UI | http://localhost:7861 |
| Django REST API | http://localhost:8000/api/v1/ |
| PostgreSQL | localhost:5432 / db: refund_db |

Run a test case end-to-end: `/run-case`

---

## Architecture

```
Input
  │
  ├─ Input Guard (prompt injection, PII, topic scope)
  │
  ├─ Tier 1: JSON Cache (exact hash match)
  ├─ Tier 2: PostgreSQL (hash + semantic similarity)
  │
  ▼ (on miss)
Classifier         — extracts structured facts from description
Supervisor
  ├─ Researcher    — finds DOT regulations via hybrid RAG (5 tools)
  ├─ Analyst       — applies thresholds, calculates refund (4 tools)
  └─ Writer        — drafts decision JSON + formal letter (1 tool)
Judge              — validates decision, overrides if wrong
  │
  ├─ Output Guard (decision enum, citations)
  │
  └─ Store → JSON cache + PostgreSQL
```

---

## Tech stack

| Layer | Technology |
|---|---|
| LLM | Anthropic Claude (Haiku for Classifier, Sonnet for others) |
| LLM fallback | OpenAI (gpt-4o-mini) when Anthropic unavailable |
| Embeddings | OpenAI text-embedding-3-small (1536 dims) |
| Agent framework | LangGraph (ReAct) + LangChain |
| RAG | LlamaIndex + Chroma (vector + BM25 + RRF + reranking) |
| Web UI | Gradio 4.x |
| REST API | Django REST Framework |
| Database | PostgreSQL 16 |
| Infra | Docker Compose |

---

## Key files

| File | Purpose |
|---|---|
| `app/config.py` | All config: models, thresholds, paths, env vars |
| `app/agents/supervisor.py` | Orchestrates Researcher → Analyst → Writer |
| `app/agents/retry.py` | Exponential backoff for all LLM calls (max 3 attempts) |
| `app/agents/ansi_colors.py` | Shared ANSI color constants for docker logs |
| `app/agents/tool_logger.py` | Shared tool-call logging callback |
| `app/cache/decision_cache.py` | Two-level cache (exact hash + semantic cosine ≥ 0.90) |
| `app/db/decision_db.py` | PostgreSQL persistence layer |
| `app/guards/input_guard.py` | Blocks prompt injection, PII, off-topic requests |
| `app/guards/output_guard.py` | Validates decision enum, enforces ERROR on bad output |
| `app/rag/retriever.py` | Hybrid search: vector + BM25 + rerank |
| `api/decisions/views.py` | Django REST endpoints (`_get_cache()`, `_get_db()` are lazy singletons — initialized on first request) |

---

## DOT refund thresholds (hardcoded in tools)

| Case | Domestic | International |
|---|---|---|
| Flight delay (significant) | ≥ 3 hours | ≥ 6 hours |
| Baggage delay (significant) | > 12 hours | > 15h (short-haul) / > 30h (long-haul) |
| Refund timeline (credit card) | 7 business days | 7 business days |
| Refund timeline (other) | 20 calendar days | 20 calendar days |

---

## Running tests

```bash
docker exec refund-gradio python -m pytest tests/ -v
```

114 tests across: `test_tools.py`, `test_guards.py`, `test_cache.py`, `test_utils.py`, `test_retry.py`

Tests use mocked OpenAI embeddings — no API calls needed.

---

## Conventions

- **ANSI colors**: always import from `app/agents/ansi_colors.py` — never define inline
- **Tool logging**: use `make_tool_logger(label)` from `app/agents/tool_logger.py`
- **LLM calls**: always wrap with `invoke_with_retry(lambda: ..., label="...")` from `app/agents/retry.py`
- **Cache/DB**: use `_get_cache()` and `_get_db()` in `views.py` — lazy singletons, initialized on first request (not at import time, to avoid build-time failures)
- **Hashing**: use `hash_inputs()` from `app/utils.py` — never write SHA256 inline
- **JSON parsing**: use `clean_llm_json()` from `app/utils.py` — handles markdown fences

---

## Things NOT to do

- Don't define ANSI color codes inline — use `ansi_colors.py`
- Don't instantiate `DecisionCache()` or `DecisionDB()` at module level or inside request handlers — use `_get_cache()` / `_get_db()`
- Don't call `agent.invoke()` or `chain.invoke()` directly — wrap with `invoke_with_retry()`
- Don't delete `storage/` (Chroma index) without also clearing the cache — causes dimension mismatch
- Don't change `OPENAI_EMBEDDING_MODEL` without running `scripts/clear_decision_data.py` first
- Don't commit `.env` — use `.env.example` as the template

---

## MCP servers

```bash
claude mcp list   # refund-db → PostgreSQL (read-only SQL)
```

Query decisions directly: `mcp__refund-db__query` with SQL against `refund_decisions` table.

---

## Claude Code setup

- **Hooks**: `settings.local.json` has flake8 (PostToolUse on Edit/Write) and tool-log (PreToolUse)
- **Skill**: `/run-case` submits a test case to Gradio and shows the decision
- **Agent**: `code-simplifier` — runs 3 parallel review agents (reuse, quality, efficiency)
- **Worktree**: currently on branch `claude/sad-colden` at `.claude/worktrees/sad-colden`
