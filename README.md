# ✈️ Airlines Refund — Multi-Agent Decision System

An AI-powered airline refund decision system using a multi-agent pipeline, RAG over DOT regulations, a Django REST API, and a Gradio web UI — all running in Docker.

## Architecture

```
User Input
    │
    ▼
🔵 Classifier        — Extracts structured case metadata from the description
    │
    ▼
🟣 Supervisor
    ├── 📚 Researcher  — Hybrid RAG search over DOT regulations (vector + BM25)
    ├── 🔢 Analyst     — Applies rules, calculates refund amounts & timelines
    └── ✍️ Writer      — Drafts formal refund request letter
    │
    ▼
🔴 Judge             — Validates decision, overrides if regulations are violated
    │
    ▼
✅ Final Decision     — APPROVED / DENIED / PARTIAL + formal letter
```

**Cache layer:** Exact-match → Semantic similarity (cosine ≥ 0.90) → Full pipeline

## Tech Stack

| Layer | Technology |
|---|---|
| Agents | LangGraph + LangChain |
| RAG | LlamaIndex (hybrid: vector + BM25) |
| LLM | OpenAI (`gpt-4.1-mini`, `gpt-5-mini`, `gpt-5-nano`) |
| Embeddings | `text-embedding-3-large` (3072 dims) |
| Web UI | Gradio |
| REST API | Django REST Framework |
| Database | PostgreSQL 16 |
| Flight Data | AviationStack API |
| Infra | Docker Compose |

## Agent Tools

| Tool | Description |
|---|---|
| `search_regulations` | Hybrid RAG search over DOT regulation documents |
| `check_delay_threshold` | Checks if a delay meets DOT refund thresholds |
| `check_baggage_threshold` | Checks baggage delay/loss refund thresholds |
| `calculate_refund` | Calculates refund amount based on case type |
| `calculate_refund_timeline` | Determines required refund timeline by payment method |
| `generate_decision_letter` | Drafts a formal refund request letter |

## Knowledge Base

Documents in `data/bilgiler/` (auto-indexed on first run):

- `14 CFR Part 259` — US airline consumer protection regulations
- `2024-07177.pdf` — USDOT Automatic Refund Rule (2024)
- `Airline_Customer_Service_Commitments` — Airline commitments doc
- `USDOT_automatic_refund_rule.txt` — Refund rule summary
- `USDOT_aviation_refunds.txt` — Aviation consumer protection refunds

## Quick Start

### Prerequisites
- Docker Desktop
- OpenAI API key
- (Optional) AviationStack API key

### 1. Clone & configure

```bash
git clone https://github.com/mattkaplanai/rag-agent-notepad-memory.git
cd rag-agent-notepad-memory
cp .env.example .env   # then fill in your keys
```

`.env` variables:

```env
OPENAI_API_KEY=sk-proj-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_LLM_MODEL=gpt-4.1-mini
OPENAI_CLASSIFIER_MODEL=gpt-5-nano
OPENAI_RESEARCHER_MODEL=gpt-5-mini

AVIATIONSTACK_ACCESS_KEY=your_key_here

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=refund_db
```

### 2. Run with Docker

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Gradio UI | http://localhost:7861 |
| Django REST API | http://localhost:8000 |
| PostgreSQL | localhost:5432 |

The vector index builds automatically on first start (takes ~1-2 min while calling OpenAI embeddings API).

> **Note:** If you change `OPENAI_EMBEDDING_MODEL`, you must clear the old index or you'll get a dimension mismatch error:
> ```bash
> docker compose run --rm gradio python scripts/clear_decision_data.py
> # then remove storage volume and restart
> docker compose down -v && docker compose up --build
> ```

## Project Structure

```
.
├── app/                        # Main Gradio application
│   ├── agents/                 # Agent definitions
│   │   ├── classifier.py       # Case metadata extractor
│   │   ├── researcher.py       # RAG-powered regulation searcher
│   │   ├── analyst.py          # Refund rule applier
│   │   ├── writer.py           # Formal letter drafter
│   │   ├── supervisor.py       # Orchestrates researcher→analyst→writer
│   │   └── judge.py            # Final decision validator
│   ├── tools/                  # LangChain tools
│   │   ├── search.py           # search_regulations
│   │   ├── check_delay.py      # check_delay_threshold
│   │   ├── check_baggage.py    # check_baggage_threshold
│   │   ├── refund_calculator.py# calculate_refund
│   │   ├── timeline_calculator.py # calculate_refund_timeline
│   │   └── letter.py           # generate_decision_letter
│   ├── rag/
│   │   ├── indexer.py          # Builds/loads LlamaIndex vector store
│   │   └── retriever.py        # Hybrid search (vector + BM25)
│   ├── cache/
│   │   └── decision_cache.py   # Exact + semantic cache (JSON)
│   ├── models/schemas.py       # Pydantic models
│   ├── config.py               # Central configuration
│   ├── ui/gradio_app.py        # Gradio interface
│   └── main.py                 # Entry point
├── api/                        # Django REST API
│   ├── api_project/            # Django project settings
│   └── decisions/              # Decisions app (endpoints)
├── data/bilgiler/              # DOT regulation documents (PDF, TXT)
├── storage/                    # Vector index (auto-generated, gitignored)
├── scripts/
│   ├── clear_decision_data.py  # Clears cache + DB (use after model change)
│   └── download_baggage_docs.py
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## REST API

Base URL: `http://localhost:8000`

```
GET  /decisions/          — List all decisions
POST /decisions/          — Submit a new case
GET  /decisions/<id>/     — Get decision by ID
```

## Case Types Supported

- Flight Cancellation
- Schedule Change / Significant Delay
- Downgrade to Lower Class
- Baggage Lost or Delayed
- Ancillary Service Not Provided
- 24-Hour Cancellation (within 24h of booking)
