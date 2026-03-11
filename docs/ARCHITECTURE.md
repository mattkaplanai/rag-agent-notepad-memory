# Airlines Refund Multi-Agent — Architecture & Flow

This document describes what we have built: the flow from user question to decision, where data lives, and how it is logged.

---

## 1. High-level picture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER (Browser)                                       │
│  Case type, flight type, description, etc.  →  [Run Multi-Agent Analysis]        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         GRADIO APP (multi_agent.py)                              │
│  • Serves UI on port 7862                                                        │
│  • Receives form submit → calls analyze_streaming(...)                            │
│  • No Django API in this path                                                    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                          │
          ┌──────────────────────────────┼──────────────────────────────┐
          ▼                              ▼                              ▼
┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
│  JSON CACHE      │          │  POSTGRESQL      │          │  RAG INDEX       │
│  decision_cache  │          │  refund_db       │          │  (LlamaIndex     │
│  .json           │          │  refund_         │          │   storage/)      │
│  + Excel export  │          │  decisions       │          │  PDFs in         │
│  decision_log    │          │  (exact +        │          │  bilgiler/       │
│  .xlsx           │          │   semantic)      │          │                  │
└──────────────────┘          └──────────────────┘          └──────────────────┘
          │                              │                              │
          └──────────────────────────────┼──────────────────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         PIPELINE (if cache/DB miss)                              │
│  Classifier (LLM) → Researcher (LLM + search_regulations) → Analyst (LLM +       │
│  threshold/refund tools) → Writer (LLM + letter tool) → Judge (LLM)               │
│  Then: save to cache + Excel + PostgreSQL                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Request flow (step by step)

```
                    ┌─────────────────────┐
                    │   USER QUESTION     │
                    │   (form submitted)  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Log: USER QUESTION │
                    │  block + DETAIL     │
                    │  Django API: not    │
                    │  used (this flow)   │
                    └──────────┬──────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │  STEP 1 — CACHE LOOKUP         │
              │  • Exact match (input hash)     │
              │  • If miss: semantic (embedding│
              │    + cosine similarity ≥ 0.9)  │
              └────────────┬───────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
         CACHE HIT                 CACHE MISS
              │                         │
              ▼                         ▼
    ┌─────────────────┐    ┌─────────────────────────┐
    │ Return cached    │    │ STEP 2 — DB LOOKUP       │
    │ decision         │    │ (PostgreSQL)             │
    │ Summary +        │    │ • Exact (by hash)        │
    │ Flow diagram     │    │ • If miss: semantic      │
    │ END OF FLOW      │    │   (embedding, ≥ 0.9)    │
    └─────────────────┘    └───────────┬─────────────┘
                                        │
                           ┌────────────┴────────────┐
                           │                         │
                      DB HIT                    DB MISS
                           │                         │
                           ▼                         ▼
                 ┌─────────────────┐    ┌─────────────────────────┐
                 │ Return DB       │    │ STEP 3 — FULL PIPELINE   │
                 │ decision        │    │                          │
                 │ Summary +       │    │ 3a. Classifier (LLM)      │
                 │ END OF FLOW     │    │     → case summary        │
                 └─────────────────┘    │ 3b. Researcher (LLM +   │
                                        │     search_regulations   │
                                        │     on RAG index)         │
                                        │ 3c. Analyst (LLM +       │
                                        │     delay/bag/refund     │
                                        │     tools)               │
                                        │ 3d. Writer (LLM +       │
                                        │     generate_letter)     │
                                        │ 3e. Judge (LLM)          │
                                        │     review                │
                                        └───────────┬───────────────┘
                                                    │
                                                    ▼
                                        ┌─────────────────────────┐
                                        │ STEP 4 — SAVE           │
                                        │ • Cache (JSON + Excel)   │
                                        │ • PostgreSQL (1 row)    │
                                        │ Summary + Flow diagram  │
                                        │ END OF FLOW             │
                                        └─────────────────────────┘
```

---

## 3. Where things live

| What | Where | Purpose |
|------|--------|--------|
| **User input** | Gradio UI (browser) | Form: case type, flight type, ticket type, payment, accepted alternative, description |
| **API that receives it** | Gradio server (multi_agent.py) | Button click → `analyze_streaming()` with form values. No separate REST API; Gradio handles HTTP and calls your Python function. |
| **Cache (fast reuse)** | `decision_cache.json` | Exact hash match + semantic similarity (embeddings in JSON). Avoids re-running LLMs for same/similar questions. |
| **Cache export** | `decision_log.xlsx` | Human-readable log of decisions (Excel). Updated on every new decision stored in cache. |
| **Persistent store** | PostgreSQL `refund_decisions` | Same idea as cache: exact + semantic lookup. Durable, can scale independently. |
| **Regulation PDFs** | `bilgiler/*.pdf` (and .docx, .txt, .md) | Source documents for RAG. |
| **RAG index** | LlamaIndex (e.g. `storage/`) | Vector index over document chunks. Used by Researcher’s `search_regulations` tool. |
| **Logs** | Terminal + `logs/multi_agent.log` | Step-by-step flow, USER QUESTION block, SUMMARY, FLOW DIAGRAM, END OF FLOW. Stdout is tee’d to the log file. |

---

## 4. What triggers the LLM

- **Gradio** receives the user input (via its own HTTP layer) and calls your code.
- **Your code** in `multi_agent.py` runs the pipeline. It:
  - Tries cache and DB (no LLM).
  - On miss, runs: **Classifier** → **Researcher** → **Analyst** → **Writer** → **Judge** (each step uses the LLM and/or tools as needed).
- So the “thing that receives the user input and triggers the LLM” is **Gradio + your `analyze_streaming` pipeline** in one process. No Django API in this path.

---

## 5. Smooth end-to-end story

**You open the app** (Gradio on port 7862). The app loads the RAG index from disk (or builds it from `bilgiler/`), connects to PostgreSQL if configured, and loads the JSON cache. Nothing calls Django.

**You enter a case** (e.g. baggage delay, domestic, bag 20 hours late) and click **Run Multi-Agent Analysis**. The browser sends the form to the Gradio server, which calls `analyze_streaming` with those values.

**First, we try to avoid work.** We hash your inputs and look for an exact match in the JSON cache. If we don’t find one, we compute an embedding for your description and compare it to cached ones. If something is close enough (e.g. ≥ 0.9), we return that decision and stop. Same idea in PostgreSQL: exact by hash, then semantic by embedding. If we hit there, we return and stop. All of this is logged (cache exact/semantic, DB exact/semantic, “Django API not used,” etc.).

**If we miss everywhere**, we run the full pipeline. The **Classifier** (LLM) reads your description and extracts structured fields (case category, delay hours, baggage delay, etc.). We build a case summary and pass it to the **Researcher**. The Researcher (LLM) uses the **search_regulations** tool, which queries the RAG index over your PDFs and returns relevant regulation snippets. The **Analyst** (LLM) uses deterministic tools (delay threshold, baggage threshold, refund calculation, timeline) and decides APPROVED/DENIED/PARTIAL. The **Writer** (LLM) turns that into a structured decision and, if needed, a formal letter. The **Judge** (LLM) reviews the outcome and can override if something looks wrong. Every step is logged (agent name, tools, recursion limit, message count, output length).

**We then save the result** so we don’t have to run the pipeline again for the same or a very similar question. We append to the JSON cache, export to Excel, and insert one row into PostgreSQL (with embedding for future semantic hit). We log “Saving: cache + Excel + DB” and print a **SUMMARY** and **FLOW DIAGRAM** for that question (path taken, decision, where it was stored). Finally we print **END OF FLOW** and the separator line.

**So in one sentence:** Gradio receives your question, tries cache and PostgreSQL for a quick answer, and on miss runs a local multi-agent pipeline (Classifier → Researcher → Analyst → Writer → Judge) over your regulations and tools, then saves the result back into the cache and DB and logs everything in detail for that single question.

This is what we have built so far; the diagram and this narrative are the “drawing” of it with details.
