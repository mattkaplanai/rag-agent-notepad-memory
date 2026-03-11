"""
Airlines Refund Decision Maker
Step 1: Advanced Prompt Engineering

Demonstrates:
  - Structured JSON output (the LLM returns a strict schema)
  - Chain-of-thought reasoning (step-by-step analysis before the verdict)
  - Few-shot examples (correct decisions embedded in the prompt)
  - Dynamic system prompts (prompt adapts based on retrieved regulations)
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY bulunamadı. Lütfen .env dosyasına ekleyin."
    )
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

PROJECT_ROOT = Path(__file__).resolve().parent
BILGILER_DIR = PROJECT_ROOT / "bilgiler"
INDEX_DIR = PROJECT_ROOT / "storage"

# ── Case type definitions ────────────────────────────────────────────────────

CASE_TYPES = [
    "Flight Cancellation",
    "Schedule Change / Significant Delay",
    "Downgrade to Lower Class",
    "Baggage Lost or Delayed",
    "Ancillary Service Not Provided",
    "24-Hour Cancellation (within 24h of booking)",
]

FLIGHT_TYPES = ["Domestic (within US)", "International"]
TICKET_TYPES = ["Refundable", "Non-refundable"]
PAYMENT_METHODS = ["Credit Card", "Debit Card", "Cash", "Check", "Airline Miles", "Other"]

ACCEPTED_ALTERNATIVES = [
    "No — I did not accept any alternative",
    "Yes — I accepted a rebooked flight",
    "Yes — I accepted a travel voucher / credit",
    "Yes — I accepted other compensation (miles, etc.)",
    "Yes — I traveled on the flight anyway",
]

# ── RAG: build / load the document index ─────────────────────────────────────

def build_or_load_index():
    from llama_index.core import (
        SimpleDirectoryReader,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
        Settings,
    )
    from llama_index.embeddings.openai import OpenAIEmbedding

    from llama_index.core.node_parser import SentenceSplitter

    BILGILER_DIR.mkdir(parents=True, exist_ok=True)
    embed_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    Settings.embed_model = OpenAIEmbedding(model=embed_model)
    Settings.chunk_size = 512
    Settings.chunk_overlap = 50
    required_exts = [".pdf", ".docx", ".doc", ".txt", ".md"]

    if INDEX_DIR.exists():
        try:
            ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
            index = load_index_from_storage(ctx)
            print("[RAG] Index loaded from storage/ (512-token chunks)")
            return index
        except Exception:
            pass

    reader = SimpleDirectoryReader(
        input_dir=str(BILGILER_DIR),
        required_exts=required_exts,
        recursive=True,
    )
    documents = reader.load_data()
    if not documents:
        print("[RAG] No documents found in bilgiler/")
        return None
    print(f"[RAG] Building index: {len(documents)} documents (chunk_size=512) …")
    node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    index = VectorStoreIndex.from_documents(documents, transformations=[node_parser])
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[RAG] Index ready.")
    return index


def retrieve_regulations(index, query: str, top_k: int = 8) -> str:
    if index is None:
        return ""
    retriever = index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query)
    return "\n\n".join(n.get_content() for n in nodes)


def retrieve_regulations_advanced(index, query: str, top_k: int = 12):
    """Advanced retrieval: hybrid search + re-ranking + citations."""
    from advanced_rag import hybrid_search, RetrievalResult
    if index is None:
        return "", RetrievalResult(query=query)
    result = hybrid_search(index, query, top_k=top_k, vector_k=16, bm25_k=16)
    return result.context_text, result


# ── Prompt Engineering ───────────────────────────────────────────────────────
#
# KEY CONCEPTS demonstrated here:
#
# 1. STRUCTURED OUTPUT  – We instruct the LLM to return valid JSON matching a
#    precise schema.  This makes the response machine-readable so the UI can
#    render it nicely.
#
# 2. CHAIN-OF-THOUGHT   – The JSON schema includes an "analysis_steps" array
#    that forces the model to reason step-by-step *before* reaching a verdict.
#
# 3. FEW-SHOT EXAMPLES  – We embed two solved cases (one APPROVED, one DENIED)
#    inside the system prompt so the model learns the expected format and
#    reasoning style.
#
# 4. DYNAMIC PROMPT      – The retrieved regulation text is injected into the
#    prompt at runtime, so the model's reasoning is grounded in real rules.
# ─────────────────────────────────────────────────────────────────────────────

FEW_SHOT_EXAMPLES = """
=== EXAMPLE 1 (APPROVED) ===
INPUT:
  Case Type: Flight Cancellation
  Flight Type: Domestic
  Ticket Type: Non-refundable
  Payment: Credit Card
  Accepted Alternative: No
  Description: My flight from Chicago to Miami on Jan 15 was cancelled by the airline due to a mechanical issue. I was offered a rebooking for the next day but I declined because I had a time-sensitive meeting.

OUTPUT:
{{{{
  "decision": "APPROVED",
  "confidence": "HIGH",
  "analysis_steps": [
    "Step 1 — Identify the case type: The airline cancelled the flight. This falls under 'Cancelled Flight' per DOT regulations.",
    "Step 2 — Check entitlement rule: Under DOT rules, a consumer is entitled to a refund if the airline cancelled a flight, regardless of the reason, and the consumer chooses not to travel or accept alternatives.",
    "Step 3 — Check if passenger accepted alternatives: The passenger declined the rebooking offer and did not accept any voucher or compensation.",
    "Step 4 — Check ticket type impact: For cancelled flights, even non-refundable ticket holders are entitled to a refund under DOT rules.",
    "Step 5 — Determine refund timeline: Payment was by credit card, so the refund must be issued within 7 business days."
  ],
  "reasons": [
    "The airline cancelled the flight (regardless of reason, this triggers refund entitlement).",
    "The passenger did not accept the rebooking or any alternative compensation.",
    "DOT's Automatic Refund Rule requires airlines to issue refunds automatically for cancelled flights when the passenger chooses not to travel."
  ],
  "applicable_regulations": [
    "DOT Automatic Refund Rule (April 2024) — Cancelled flights entitle passengers to a refund.",
    "14 CFR Part 259 — Airlines must provide automatic refunds without requiring passengers to request them."
  ],
  "refund_details": {{{{
    "refund_type": "Full refund of ticket price plus all taxes and fees",
    "payment_method": "Original form of payment (credit card)",
    "timeline": "Within 7 business days (credit card purchase)"
  }}}},
  "passenger_action_items": [
    "No action required — the airline must issue the refund automatically.",
    "If the refund is not received within 7 business days, file a complaint with DOT at https://airconsumer.dot.gov."
  ]
}}}}

=== EXAMPLE 2 (DENIED) ===
INPUT:
  Case Type: Schedule Change / Significant Delay
  Flight Type: Domestic
  Ticket Type: Non-refundable
  Payment: Credit Card
  Accepted Alternative: Yes — I traveled on the flight anyway
  Description: My flight from New York to Los Angeles was delayed by 1 hour and 30 minutes. I still took the flight but I was unhappy with the delay and want a refund.

OUTPUT:
{{{{
  "decision": "DENIED",
  "confidence": "HIGH",
  "analysis_steps": [
    "Step 1 — Identify the case type: The flight was delayed by 1 hour 30 minutes. This falls under 'Schedule Change / Significant Delay'.",
    "Step 2 — Check significance threshold: For domestic flights, a 'significant delay' means departure 3+ hours early or arrival 3+ hours late. A 1.5-hour delay does NOT meet the threshold.",
    "Step 3 — Check if passenger traveled: The passenger chose to travel on the delayed flight.",
    "Step 4 — Apply the rule: Even if the delay had been significant, the passenger traveled on the flight and is therefore not entitled to a refund under DOT rules."
  ],
  "reasons": [
    "The 1.5-hour delay does not meet the DOT 'significant delay' threshold of 3+ hours for domestic flights.",
    "The passenger chose to travel on the delayed flight, which waives refund entitlement.",
    "Unsatisfactory service experience alone does not entitle a consumer to a refund."
  ],
  "applicable_regulations": [
    "DOT Automatic Refund Rule — Domestic significant delay threshold is 3+ hours.",
    "DOT Refund Policy — Consumers who chose to travel on a delayed flight are not entitled to a refund."
  ],
  "refund_details": null,
  "passenger_action_items": [
    "You are not entitled to a refund in this situation.",
    "You may check flightrights.gov for airline commitments regarding amenities for delays caused by the airline."
  ]
}}}}

=== EXAMPLE 3 (DENIED — baggage threshold) ===
INPUT:
  Case Type: Baggage Lost or Delayed
  Flight Type: International
  Ticket Type: Refundable
  Payment: Credit Card
  Accepted Alternative: No
  Description: I flew on a 16-hour flight from Singapore to New York. I paid $100 for checked baggage. My bag was delivered to my hotel 25 hours after I deplaned. I want my baggage fee refunded.

OUTPUT:
{{{{
  "decision": "DENIED",
  "confidence": "HIGH",
  "analysis_steps": [
    "Step 1 — Identify the case type: The passenger's checked bag was delayed on an international flight. This falls under 'Baggage Lost or Delayed'.",
    "Step 2 — Determine the flight duration: The flight was 16 hours, which is MORE than 12 hours.",
    "Step 3 — Select the correct baggage delay threshold: For international flights MORE than 12 hours in duration, a bag is considered 'significantly delayed' ONLY if it is not delivered within 30 hours after arrival. This is NOT the 15-hour threshold — the 15-hour threshold applies ONLY to international flights of 12 hours or LESS.",
    "Step 4 — Compare delivery time to threshold: The bag was delivered 25 hours after deplaning. 25 hours < 30 hours. The bag was NOT significantly delayed under DOT rules.",
    "Step 5 — Conclusion: Since the bag was delivered within the 30-hour window, the passenger is not entitled to a refund of the baggage fee."
  ],
  "reasons": [
    "The flight was 16 hours (more than 12 hours), so the applicable baggage delay threshold is 30 hours — NOT 15 hours.",
    "The bag was delivered 25 hours after deplaning, which is within the 30-hour threshold.",
    "The bag is NOT considered 'significantly delayed' under DOT regulations."
  ],
  "applicable_regulations": [
    "DOT Baggage Delay Rule — International flights over 12 hours: bag must be delivered within 30 hours to NOT be significantly delayed.",
    "DOT Baggage Delay Rule — The 15-hour threshold applies ONLY to international flights of 12 hours or less in duration."
  ],
  "refund_details": null,
  "passenger_action_items": [
    "You are not entitled to a refund of the baggage fee because the bag was delivered within the 30-hour threshold.",
    "If the bag had been delivered after 30 hours, you would have been entitled to a refund."
  ]
}}}}
"""

SYSTEM_PROMPT = """You are an expert Airlines Refund Decision Maker AI, trained on U.S. Department of Transportation (DOT) regulations.

YOUR ROLE: Analyze passenger refund requests and issue a legally grounded decision based on DOT regulations and the documents provided.

REGULATIONS (retrieved from the knowledge base):
{regulations}

INSTRUCTIONS:
1. Analyze the passenger's case step by step using chain-of-thought reasoning.
2. For each step, cite the specific regulation or rule that applies.
3. Consider ALL factors: case type, flight type (domestic/international), ticket type, whether the passenger accepted alternatives, and the specific circumstances described.
4. Issue a clear decision: APPROVED, DENIED, or PARTIAL (for cases like downgrades where only a fare difference refund applies).
5. Set confidence to HIGH, MEDIUM, or LOW based on how clearly the regulations apply.

CRITICAL RULES:
- Cancelled flights ALWAYS entitle a refund if the passenger did not accept alternatives, regardless of ticket type.
- For schedule changes: domestic = 3+ hours threshold, international = 6+ hours threshold.
- If the passenger accepted a rebooking, voucher, or traveled on the flight, they are generally NOT entitled to a refund.
- Non-refundable tickets do NOT entitle a refund when the flight operates as scheduled and the passenger chooses not to travel.
- Baggage delay refund logic (MUST check flight duration first):
  * Domestic: refund the baggage fee ONLY if bag arrived MORE than 12 hours after deplaning.
  * International, flight ≤12 hours: refund ONLY if bag arrived MORE than 15 hours after deplaning.
  * International, flight >12 hours: refund ONLY if bag arrived MORE than 30 hours after deplaning.
  If the bag arrived WITHIN the threshold, the bag is NOT significantly delayed and the passenger is NOT entitled to a refund. "Within the threshold" = bag arrived on time = DENIED.
  IMPORTANT: Do NOT confuse "within the threshold" with "qualifying for a refund." Within = on time = DENIED.
- 24-hour cancellation: only applies to tickets purchased 7+ days before departure.

OUTPUT FORMAT: You MUST respond with valid JSON matching this exact schema:
{{{{
  "decision": "APPROVED" | "DENIED" | "PARTIAL",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "analysis_steps": ["Step 1 — ...", "Step 2 — ...", ...],
  "reasons": ["reason 1", "reason 2", ...],
  "applicable_regulations": ["regulation 1", "regulation 2", ...],
  "refund_details": {{{{
    "refund_type": "description of what is refunded",
    "payment_method": "how the refund is paid",
    "timeline": "when the refund must be issued"
  }}}} or null if DENIED,
  "passenger_action_items": ["action 1", "action 2", ...]
}}}}

Do NOT include any text outside the JSON object. Return ONLY the JSON.

{few_shot}
"""


def build_case_description(
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> str:
    return (
        f"Case Type: {case_type}\n"
        f"Flight Type: {flight_type}\n"
        f"Ticket Type: {ticket_type}\n"
        f"Payment Method: {payment_method}\n"
        f"Accepted Alternative: {accepted_alternative}\n"
        f"Passenger Description: {description}"
    )


def get_refund_decision(
    index,
    case_type: str,
    flight_type: str,
    ticket_type: str,
    payment_method: str,
    accepted_alternative: str,
    description: str,
) -> tuple[dict, any]:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    case_text = build_case_description(
        case_type, flight_type, ticket_type,
        payment_method, accepted_alternative, description,
    )

    retrieval_query = f"{case_type} {flight_type} {description}"
    regulations, retrieval_result = retrieve_regulations_advanced(index, retrieval_query)

    system = SYSTEM_PROMPT.format(
        regulations=regulations if regulations else "(No regulations retrieved — decide based on your training knowledge of DOT rules.)",
        few_shot=FEW_SHOT_EXAMPLES,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Analyze this refund request and return your decision as JSON:\n\n{case}"),
    ])

    llm_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=llm_model, temperature=0.1)
    chain = prompt | llm | StrOutputParser()
    raw = chain.invoke({"case": case_text})

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned), retrieval_result
    except json.JSONDecodeError:
        return {
            "decision": "ERROR",
            "confidence": "LOW",
            "analysis_steps": ["Failed to parse LLM response as JSON."],
            "reasons": [f"Raw response: {raw[:500]}"],
            "applicable_regulations": [],
            "refund_details": None,
            "passenger_action_items": ["Please try again or rephrase your description."],
        }, retrieval_result


# ── Gradio UI ────────────────────────────────────────────────────────────────

def format_decision(result: dict, cache_status: str = "miss") -> str:
    d = result.get("decision", "UNKNOWN")
    emoji = {"APPROVED": "✅", "DENIED": "❌", "PARTIAL": "⚠️"}.get(d, "❓")
    confidence = result.get("confidence", "?")

    cache_labels = {
        "exact_hit": "⚡ **Cache: EXACT HIT** — Instant response, $0 LLM cost",
        "semantic_hit": "🔍 **Cache: SIMILAR CASE FOUND** — Reused previous decision, minimal cost",
        "miss": "🤖 **Cache: MISS** — Full LLM analysis performed",
    }
    cache_line = cache_labels.get(cache_status, "")

    lines = [
        f"# {emoji} Decision: {d}",
        f"**Confidence:** {confidence}",
        "",
        cache_line,
        "",
        "---",
        "## 🔍 Analysis (Chain-of-Thought)",
    ]
    for step in result.get("analysis_steps", []):
        lines.append(f"- {step}")

    lines += ["", "---", "## 📋 Reasons"]
    for reason in result.get("reasons", []):
        lines.append(f"- {reason}")

    lines += ["", "---", "## 📜 Applicable Regulations"]
    for reg in result.get("applicable_regulations", []):
        lines.append(f"- {reg}")

    refund = result.get("refund_details")
    if refund:
        lines += [
            "", "---", "## 💰 Refund Details",
            f"- **Type:** {refund.get('refund_type', 'N/A')}",
            f"- **Payment:** {refund.get('payment_method', 'N/A')}",
            f"- **Timeline:** {refund.get('timeline', 'N/A')}",
        ]

    lines += ["", "---", "## 📝 What You Should Do"]
    for action in result.get("passenger_action_items", []):
        lines.append(f"- {action}")

    return "\n".join(lines)


def create_gradio_app():
    import gradio as gr
    from decision_cache import DecisionCache

    print("[APP] Building document index …")
    index = build_or_load_index()
    cache = DecisionCache()
    print(f"[APP] Ready. Cache has {cache.stats['total_entries']} entries.")

    def analyze(case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description):
        from advanced_rag import format_retrieval_dashboard

        if not description or not description.strip():
            return "⚠️ Please describe what happened with your flight.", "", ""

        cached_result, cache_status = cache.lookup(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        if cached_result:
            return (
                format_decision(cached_result, cache_status),
                f"📊 Cache: {cache.stats['total_entries']} entries stored",
                "*Served from cache — no retrieval performed.*",
            )

        result, retrieval_result = get_refund_decision(
            index, case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        if result.get("decision") != "ERROR":
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, result,
            )

        dashboard = format_retrieval_dashboard(retrieval_result) if retrieval_result else ""

        return (
            format_decision(result, "miss"),
            f"📊 Cache: {cache.stats['total_entries']} entries stored",
            dashboard,
        )

    def clear_cache():
        cache.clear()
        return f"📊 Cache cleared. 0 entries stored."

    with gr.Blocks(
        title="Airlines Refund Decision Maker",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown("# ✈️ Airlines Refund Decision Maker")
        gr.Markdown(
            "Submit your flight details and the AI will analyze your case "
            "against **U.S. DOT regulations** and issue a refund decision "
            "with step-by-step reasoning."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📋 Case Details")
                case_type = gr.Dropdown(
                    choices=CASE_TYPES,
                    value=CASE_TYPES[0],
                    label="Case Type",
                )
                flight_type = gr.Dropdown(
                    choices=FLIGHT_TYPES,
                    value=FLIGHT_TYPES[0],
                    label="Flight Type",
                )
                ticket_type = gr.Dropdown(
                    choices=TICKET_TYPES,
                    value=TICKET_TYPES[1],
                    label="Ticket Type",
                )
                payment_method = gr.Dropdown(
                    choices=PAYMENT_METHODS,
                    value=PAYMENT_METHODS[0],
                    label="Payment Method",
                )
                accepted_alternative = gr.Dropdown(
                    choices=ACCEPTED_ALTERNATIVES,
                    value=ACCEPTED_ALTERNATIVES[0],
                    label="Did you accept any alternative?",
                )
                description = gr.Textbox(
                    label="Describe what happened",
                    placeholder=(
                        "Example: My flight AA1234 from Dallas to New York on "
                        "March 5 was cancelled due to weather. The airline "
                        "offered me a flight the next morning but I declined "
                        "because I had a meeting that day."
                    ),
                    lines=5,
                )
                submit_btn = gr.Button(
                    "🔍 Analyze My Case",
                    variant="primary",
                    size="lg",
                )

            with gr.Column(scale=1):
                with gr.Tabs():
                    with gr.Tab("📄 Decision"):
                        output = gr.Markdown(
                            value="*Submit your case details to receive a decision.*"
                        )
                    with gr.Tab("📡 Retrieval Dashboard"):
                        retrieval_dashboard = gr.Markdown(
                            value="*Submit a case to see how documents are retrieved, ranked, and cited.*"
                        )
                gr.Markdown("---")
                cache_status_display = gr.Textbox(
                    label="Cache Status",
                    value=f"📊 Cache: {cache.stats['total_entries']} entries stored",
                    interactive=False,
                )
                clear_cache_btn = gr.Button("🗑️ Clear Cache", size="sm")

        submit_btn.click(
            fn=analyze,
            inputs=[
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description,
            ],
            outputs=[output, cache_status_display, retrieval_dashboard],
        )

        clear_cache_btn.click(
            fn=clear_cache,
            outputs=cache_status_display,
        )

        gr.Markdown("---")
        gr.Markdown(
            "**Techniques Used:**  \n"
            "🔗 Chain-of-Thought · "
            "📐 Structured JSON · "
            "📝 Few-Shot Examples · "
            "🔄 Dynamic RAG · "
            "⚡ Two-Level Cache · "
            "🔀 Hybrid Search (BM25 + Vector) · "
            "📊 Re-Ranking · "
            "📚 Source Citations"
        )

    return app


if __name__ == "__main__":
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=7860)
