"""
Airlines Refund Decision Agent — Multi-Tool Agent (Step 3)

This replaces the single-shot LLM call with an agent that can call
specialized tools during its reasoning loop:

  1. search_regulations — RAG search for DOT rules
  2. check_delay_threshold — deterministic delay threshold check
  3. check_baggage_threshold — deterministic baggage threshold check
  4. calculate_refund — compute exact refund amounts
  5. calculate_refund_timeline — compute exact deadline dates
  6. generate_decision_letter — create a formal letter for the passenger

The agent uses LangChain's tool-calling agent + AgentExecutor which
implements the ReAct pattern: Reason → Act (call tool) → Observe → Repeat.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Add it to .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

PROJECT_ROOT = Path(__file__).resolve().parent
BILGILER_DIR = PROJECT_ROOT / "bilgiler"
INDEX_DIR = PROJECT_ROOT / "storage"


# ── Build index (reuse from refund_decision.py) ─────────────────────────────

def build_or_load_index():
    from llama_index.core import (
        SimpleDirectoryReader, StorageContext, VectorStoreIndex,
        load_index_from_storage, Settings,
    )
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.core.node_parser import SentenceSplitter

    BILGILER_DIR.mkdir(parents=True, exist_ok=True)
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.chunk_size = 512
    Settings.chunk_overlap = 50

    if INDEX_DIR.exists():
        try:
            ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
            index = load_index_from_storage(ctx)
            print("[RAG] Index loaded from storage/")
            return index
        except Exception:
            pass

    reader = SimpleDirectoryReader(
        input_dir=str(BILGILER_DIR),
        required_exts=[".pdf", ".docx", ".doc", ".txt", ".md"],
        recursive=True,
    )
    documents = reader.load_data()
    if not documents:
        print("[RAG] No documents in bilgiler/")
        return None
    print(f"[RAG] Building index: {len(documents)} documents (chunk_size=512)...")
    node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    index = VectorStoreIndex.from_documents(documents, transformations=[node_parser])
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[RAG] Index ready.")
    return index


# ── Agent System Prompt ──────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """You are an expert Airlines Refund Decision Agent with access to specialized tools.

YOUR ROLE: Analyze passenger refund requests and issue legally grounded decisions using DOT regulations.

AVAILABLE TOOLS:
- search_regulations: Search DOT regulation documents. ALWAYS use this first to find relevant rules.
- check_delay_threshold: Check if a flight delay is "significant" (domestic 3h / international 6h). Use for delay/schedule change cases.
- check_baggage_threshold: Check if a baggage delay is "significant." REQUIRES flight duration. Use for baggage cases.
- calculate_refund: Compute exact refund amounts. Use when you know the ticket price or fare difference.
- calculate_refund_timeline: Compute the exact deadline date for the refund. Use when you know the payment method and event date.
- generate_decision_letter: Create a formal refund request letter. Use ONLY after deciding APPROVED or PARTIAL.

WORKFLOW:
1. FIRST: Call search_regulations to find the relevant DOT rules for this case type.
2. THEN: Use the appropriate threshold checker tool (check_delay_threshold or check_baggage_threshold) if the case involves delays or baggage. TRUST the tool result — do NOT override it.
3. THEN: Use calculate_refund if you can determine the refund amount.
4. THEN: Use calculate_refund_timeline to determine the deadline.
5. FINALLY: Produce your final answer as valid JSON.

CRITICAL: When a tool tells you the delay is NOT significant or the bag is NOT significantly delayed, the decision MUST be DENIED. Do NOT override tool results with your own reasoning.

OUTPUT FORMAT: Your FINAL answer must be valid JSON with this schema:
{{
  "decision": "APPROVED" | "DENIED" | "PARTIAL",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "analysis_steps": ["Step 1 — ...", "Step 2 — ...", ...],
  "reasons": ["reason 1", "reason 2", ...],
  "applicable_regulations": ["regulation 1", ...],
  "refund_details": {{
    "refund_type": "...",
    "refund_amount": "...",
    "payment_method": "...",
    "timeline": "..."
  }} or null if DENIED,
  "passenger_action_items": ["action 1", ...],
  "tools_used": ["tool_name_1", "tool_name_2", ...],
  "decision_letter": "..." or null if DENIED
}}

Return ONLY the JSON in your final answer. No text outside the JSON."""


# ── Build the Agent ──────────────────────────────────────────────────────────

def build_agent(index):
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI
    from refund_tools import get_all_tools

    tools = get_all_tools(index)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

    agent = create_react_agent(
        llm,
        tools,
        prompt=AGENT_SYSTEM_PROMPT,
    )
    return agent


def run_agent(executor, case_text: str) -> dict:
    result = executor.invoke({"messages": [{"role": "user", "content": case_text}]})
    messages = result.get("messages", [])
    raw = messages[-1].content if messages else ""

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "decision": "ERROR",
            "confidence": "LOW",
            "analysis_steps": ["Failed to parse agent response as JSON."],
            "reasons": [f"Raw response: {raw[:500]}"],
            "applicable_regulations": [],
            "refund_details": None,
            "passenger_action_items": ["Please try again."],
            "tools_used": [],
            "decision_letter": None,
        }


# ── Formatting ───────────────────────────────────────────────────────────────

def format_agent_decision(result: dict) -> str:
    d = result.get("decision", "UNKNOWN")
    emoji = {"APPROVED": "✅", "DENIED": "❌", "PARTIAL": "⚠️"}.get(d, "❓")
    confidence = result.get("confidence", "?")

    lines = [
        f"# {emoji} Decision: {d}",
        f"**Confidence:** {confidence}",
        "",
    ]

    tools_used = result.get("tools_used", [])
    if tools_used:
        tools_str = ", ".join(f"`{t}`" for t in tools_used)
        lines.append(f"**Tools Used:** {tools_str}")
        lines.append("")

    lines += ["---", "## 🔍 Analysis (Chain-of-Thought)"]
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
            f"- **Amount:** {refund.get('refund_amount', 'N/A')}",
            f"- **Payment:** {refund.get('payment_method', 'N/A')}",
            f"- **Timeline:** {refund.get('timeline', 'N/A')}",
        ]

    lines += ["", "---", "## 📝 What You Should Do"]
    for action in result.get("passenger_action_items", []):
        lines.append(f"- {action}")

    letter = result.get("decision_letter")
    if letter:
        lines += [
            "", "---", "## ✉️ Formal Refund Request Letter",
            "", "```", letter, "```",
        ]

    return "\n".join(lines)


# ── Gradio UI ────────────────────────────────────────────────────────────────

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


def create_gradio_app():
    import gradio as gr
    from decision_cache import DecisionCache

    print("[AGENT] Building document index...")
    index = build_or_load_index()
    executor = build_agent(index)
    cache = DecisionCache()
    print(f"[AGENT] Ready. Cache: {cache.stats['total_entries']} entries.")

    def analyze(case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description):
        if not description or not description.strip():
            return "⚠️ Please describe what happened with your flight.", ""

        cached_result, cache_status = cache.lookup(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        if cached_result:
            cache_labels = {
                "exact_hit": "⚡ EXACT HIT",
                "semantic_hit": "🔍 SIMILAR CASE",
            }
            label = cache_labels.get(cache_status, cache_status)
            return (
                format_agent_decision(cached_result),
                f"📊 Cache: {label} | {cache.stats['total_entries']} entries",
            )

        case_text = (
            f"Case Type: {case_type}\n"
            f"Flight Type: {flight_type}\n"
            f"Ticket Type: {ticket_type}\n"
            f"Payment Method: {payment_method}\n"
            f"Accepted Alternative: {accepted_alternative}\n"
            f"Passenger Description: {description}"
        )

        result = run_agent(executor, case_text)

        if result.get("decision") != "ERROR":
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, result,
            )

        return (
            format_agent_decision(result),
            f"📊 Cache: MISS | {cache.stats['total_entries']} entries",
        )

    def clear_cache():
        cache.clear()
        return "📊 Cache cleared. 0 entries."

    with gr.Blocks(
        title="Airlines Refund Agent",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown("# ✈️ Airlines Refund Decision Agent")
        gr.Markdown(
            "**Step 3: Multi-Tool Agent** — The AI agent uses specialized tools "
            "(threshold checker, refund calculator, timeline calculator, letter generator) "
            "during its reasoning loop. Tools use **code** for math — no more LLM guessing."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📋 Case Details")
                case_type = gr.Dropdown(choices=CASE_TYPES, value=CASE_TYPES[0], label="Case Type")
                flight_type = gr.Dropdown(choices=FLIGHT_TYPES, value=FLIGHT_TYPES[0], label="Flight Type")
                ticket_type = gr.Dropdown(choices=TICKET_TYPES, value=TICKET_TYPES[1], label="Ticket Type")
                payment_method = gr.Dropdown(choices=PAYMENT_METHODS, value=PAYMENT_METHODS[0], label="Payment Method")
                accepted_alternative = gr.Dropdown(choices=ACCEPTED_ALTERNATIVES, value=ACCEPTED_ALTERNATIVES[0], label="Did you accept any alternative?")
                description = gr.Textbox(
                    label="Describe what happened",
                    placeholder="Example: My flight was cancelled and I declined the rebooking...",
                    lines=5,
                )
                submit_btn = gr.Button("🤖 Agent: Analyze My Case", variant="primary", size="lg")

            with gr.Column(scale=1):
                gr.Markdown("### 📄 Decision")
                output = gr.Markdown(value="*Submit your case details for the agent to analyze.*")
                gr.Markdown("---")
                cache_display = gr.Textbox(
                    label="Status",
                    value=f"📊 Cache: {cache.stats['total_entries']} entries",
                    interactive=False,
                )
                clear_btn = gr.Button("🗑️ Clear Cache", size="sm")

        submit_btn.click(
            fn=analyze,
            inputs=[case_type, flight_type, ticket_type, payment_method, accepted_alternative, description],
            outputs=[output, cache_display],
        )
        clear_btn.click(fn=clear_cache, outputs=cache_display)

        gr.Markdown("---")
        gr.Markdown(
            "**Tools Available:** "
            "`search_regulations` · `check_delay_threshold` · `check_baggage_threshold` · "
            "`calculate_refund` · `calculate_refund_timeline` · `generate_decision_letter`"
        )

    return app


if __name__ == "__main__":
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=7861)
