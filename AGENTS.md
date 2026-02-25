# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Python RAG (Retrieval-Augmented Generation) application with two entry points:

| Entry point | Description | Default address |
|---|---|---|
| `python rag_app.py` | Simple question-answer Gradio UI | `0.0.0.0:7860` |
| `python rag_agent.py` | Agent with tools (notepad, memory, document search) | `127.0.0.1:7860` |
| `python refund_decision.py` | Airlines Refund Decision Maker (Step 1: Prompt Engineering) | `0.0.0.0:7860` |

See `README.md` for full architecture details.

### Prerequisites

- **`OPENAI_API_KEY`** must be set in `.env` (copy from `.env.example`). The app crashes at startup without a valid key — it attempts to build the vector index using OpenAI embeddings immediately.
- The `bilgiler/` directory must contain at least one `.pdf`, `.docx`, `.doc`, `.txt`, or `.md` file. Sample documents are already committed.

### Running

```bash
source /workspace/venv/bin/activate
python rag_app.py            # simple RAG
python rag_agent.py          # agent mode
python refund_decision.py    # airlines refund decision maker
```

Both serve a Gradio UI on port 7860. `rag_app.py` binds `0.0.0.0`; `rag_agent.py` binds `127.0.0.1`.

### Linting

```bash
source /workspace/venv/bin/activate
ruff check .
```

The existing codebase has 5 unused-import warnings (F401) in `rag_app.py` and `rag_agent.py` — these are pre-existing and intentional (kept for potential future use).

### Gotchas

- `rag_app.py` **always rebuilds** the vector index on startup (deletes `storage/` each time). This means every restart calls the OpenAI Embeddings API and incurs cost/latency. `rag_agent.py` and `refund_decision.py` load from cache in `storage/` if available.
- `python3.12-venv` must be installed system-wide (`sudo apt-get install python3.12-venv`) before creating the virtualenv. The update script handles dependency installation only; the venv and system package are set up once.
- No automated test suite exists in this codebase; validation is manual via the Gradio UI.
