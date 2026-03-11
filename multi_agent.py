"""
Multi-Agent System: Supervisor + Researcher + Analyst + Writer

Step 5 of the learning roadmap: Agent-to-Agent communication.

Demonstrates:
  - Agent delegation: Supervisor routes work to specialist workers
  - Separation of concerns: each agent has its own tools and focus
  - Multi-agent coordination: agents share information via the Supervisor
  - Scalability: adding a new capability = adding a new worker agent
"""

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv

# Load .env from project root; override=True so .env wins over shell env
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, override=True)

from langgraph.errors import GraphRecursionError

from citation_links import format_regulation_with_citation
from citation_validator import (
    CitationValidationResult,
    format_validation_for_log,
    validate_citations,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Add it to .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class WorkerOutput:
    agent_name: str
    result: str
    tools_used: list[str] = field(default_factory=list)


@dataclass
class MultiAgentResult:
    researcher_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Researcher", ""))
    analyst_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Analyst", ""))
    writer_output: WorkerOutput = field(default_factory=lambda: WorkerOutput("Writer", ""))
    supervisor_decision: dict = field(default_factory=dict)
    agent_log: list[str] = field(default_factory=list)
    citation_validation: Optional[CitationValidationResult] = None


# ── Worker Agent Builder ─────────────────────────────────────────────────────

def _build_worker(system_prompt: str, tools: list, model: Optional[str] = None):
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI

    llm_model = model or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=llm_model, temperature=0.1)
    agent = create_react_agent(llm, tools, prompt=system_prompt)
    return agent


# Higher limit so Researcher/Analyst/Writer can finish (default 25 was hit on tool-heavy runs)
RECURSION_LIMIT = 75
# Researcher gets a lower cap so we fail fast and show a clear message if it loops
RESEARCHER_RECURSION_LIMIT = 15

# Tool adları → logda görünecek amaç (hangi agent/tool, ne için kullanıldı)
TOOL_PURPOSES = {
    "search_regulations": "İlgili DOT düzenlemelerini arama",
    "check_delay_threshold": "Gecikme eşiğini kontrol (3h domestic / 6h international)",
    "check_baggage_threshold": "Bagaj gecikmesi eşiğini kontrol",
    "calculate_refund": "İade tutarını hesaplama",
    "calculate_refund_timeline": "İade süresi hesaplama (7 iş günü vb.)",
    "convert_currency": "Para birimi dönüşümü (cevap hep USD)",
    "generate_decision_letter": "Resmi iade mektubu oluşturma",
}

def _extract_researcher_retrieval_chunks(messages: List[Any]) -> List[str]:
    """Researcher'ın search_regulations tool cevaplarından dönen chunk metinlerini çıkarır (citation grounding için)."""
    chunks: List[str] = []
    for msg in messages:
        if type(msg).__name__ != "ToolMessage":
            continue
        if getattr(msg, "name", None) != "search_regulations":
            continue
        content = getattr(msg, "content", None) or ""
        if not content.strip():
            continue
        # refund_tools format: "[Source: ... | Relevance: ...]\ncontent\n\n---\n\n..."
        for block in content.split("\n\n---\n\n"):
            b = block.strip()
            if b:
                chunks.append(b)
    return chunks


def _extract_tool_calls_from_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """Agent mesajlarından tool çağrılarını ve sonuç önizlemesini çıkarır."""
    entries = []
    tool_msg_idx = 0
    for msg in messages:
        t = type(msg).__name__
        if t == "AIMessage":
            for tc in (getattr(msg, "tool_calls", None) or []):
                name = tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                args = tc.get("args", {}) if isinstance(tc, dict) else (getattr(tc, "args", None) or {})
                entries.append({"tool": name, "args": args, "result_preview": None})
        elif t == "ToolMessage":
            content = (getattr(msg, "content", None) or "")[:200]
            if tool_msg_idx < len(entries):
                entries[tool_msg_idx]["result_preview"] = content.replace("\n", " ").strip()
                tool_msg_idx += 1
    return entries


def _append_tool_log_to_result(result: "MultiAgentResult", agent_name: str, tool_entries: list, agent_emoji: str = "🔧"):
    """Tool çağrılarını agent_log'a ekler (UI'da farklı renkte/blokta görünsün)."""
    for e in tool_entries:
        tool_name = e.get("tool", "?")
        args = e.get("args", {}) or {}
        purpose = TOOL_PURPOSES.get(tool_name, "Araç çağrısı")
        args_str = ", ".join(f"{k}={v!r}" for k, v in (args.items() if isinstance(args, dict) else []))
        if len(args_str) > 80:
            args_str = args_str[:77] + "..."
        preview = (e.get("result_preview") or "")[:100]
        if preview:
            preview = f" | **Sonuç önizleme:** {preview}..."
        # UI log (Markdown): tool adı ve amaç net görünsün (kalın + code)
        line = (
            f"   **{agent_emoji} Tool:** `{tool_name}` "
            f"| **Amaç:** {purpose} | **Argümanlar:** `{args_str}`{preview}"
        )
        result.agent_log.append(line)


def _print_tool_log_terminal(agent_name: str, tool_entries: list, color: str = "\033[93m"):
    """Tool çağrılarını terminale renkli yazar."""
    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"
    for e in tool_entries:
        tool_name = e.get("tool", "?")
        args = e.get("args", {}) or {}
        purpose = TOOL_PURPOSES.get(tool_name, "Araç çağrısı")
        args_str = ", ".join(f"{k}={v!r}" for k, v in (args.items() if isinstance(args, dict) else []))
        if len(args_str) > 70:
            args_str = args_str[:67] + "..."
        print(f"  {color}{bold}[TOOL] {agent_name} → {tool_name}{reset} | Amaç: {purpose}", flush=True)
        print(f"       {dim}Argümanlar: {args_str}{reset}", flush=True)


def _run_worker(agent, task: str, recursion_limit: Optional[int] = None, log_prefix: str = "") -> str:
    limit = recursion_limit if recursion_limit is not None else RECURSION_LIMIT
    if log_prefix:
        print(f"[LOG] {log_prefix} invoking LLM (recursion_limit={limit})", flush=True)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": limit},
    )
    messages = result.get("messages", [])
    out = messages[-1].content if messages else ""
    if log_prefix:
        print(f"[LOG] {log_prefix} done — messages/steps={len(messages)}, output_len={len(out)}", flush=True)
    return out


def _run_worker_return_messages(agent, task: str, recursion_limit: Optional[int] = None, log_prefix: str = ""):
    """_run_worker ile aynı ama (out, messages) döner; tool log için kullanılır."""
    limit = recursion_limit if recursion_limit is not None else RECURSION_LIMIT
    if log_prefix:
        print(f"[LOG] {log_prefix} invoking LLM (recursion_limit={limit})", flush=True)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": limit},
    )
    messages = result.get("messages", [])
    out = messages[-1].content if messages else ""
    if log_prefix:
        print(f"[LOG] {log_prefix} done — messages/steps={len(messages)}, output_len={len(out)}", flush=True)
    return out, messages


def _run_researcher_with_detailed_log(researcher_agent, task: str, recursion_limit: int):
    """
    Run the Researcher agent and print a detailed step-by-step log (what the LLM did,
    which tool calls, what each search returned). Returns (out, messages) for tool log.
    """
    limit = recursion_limit
    researcher_model = os.getenv("OPENAI_RESEARCHER_MODEL", "gpt-4o")
    _b, _cyan, _r = "\033[1m", "\033[96m", "\033[0m"
    print(f"{_cyan}{_b}[RESEARCHER] Model: {researcher_model}{_r}", flush=True)
    print(f"[LOG] Researcher agent invoking (recursion_limit={limit})", flush=True)
    result = researcher_agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": limit},
    )
    messages = result.get("messages", [])
    out = messages[-1].content if messages else ""

    # ── Detailed Researcher log (terminal) ────────────────────────────────────
    _cyan = "\033[96m"
    _yellow = "\033[93m"
    _green = "\033[92m"
    _gray = "\033[37m"
    _bold = "\033[1m"
    _reset = "\033[0m"
    _dim = "\033[2m"
    sep = "─" * 64
    print(flush=True)
    print(_cyan + "╔" + sep + "╗" + _reset, flush=True)
    print(_cyan + "║" + _reset + _bold + " 📚 RESEARCHER AGENT — DETAYLI LOG" + _reset + _cyan + " " * 26 + "║" + _reset, flush=True)
    print(_cyan + "╠" + sep + "╣" + _reset, flush=True)
    print(_cyan + "║" + _reset + _bold + " Girdi (case summary) — TAM:" + _reset + _cyan + " " * 35 + "║" + _reset, flush=True)
    print(_cyan + "╠" + sep + "╣" + _reset, flush=True)
    for line in task.split("\n"):
        for chunk in (line[i : i + 62] for i in range(0, len(line), 62)):
            print(_cyan + "║ " + _reset + _gray + chunk.ljust(62) + _reset + _cyan + " ║" + _reset, flush=True)
    print(_cyan + "╠" + sep + "╣" + _reset, flush=True)

    step = 0
    for i, msg in enumerate(messages):
        t = type(msg).__name__
        if t == "HumanMessage":
            continue  # already printed task above
        if t == "AIMessage":
            tool_calls = getattr(msg, "tool_calls", None) or []
            content = (getattr(msg, "content", None) or "").strip()
            if tool_calls:
                step += 1
                for tc in tool_calls:
                    name = tc.get("name", "?")
                    args = tc.get("args", {})
                    q = args.get("query", args.get("input", str(args)))
                    print(_cyan + "║" + _reset + f" {_bold}Adım {step}:{_reset} LLM → Tool çağrısı: {_yellow}{name}{_reset}", flush=True)
                    print(_cyan + "║" + _reset + f"    Query: {_green}\"{q[:80]}{'...' if len(q) > 80 else ''}\"{_reset}", flush=True)
                    print(_cyan + "║" + _reset, flush=True)
            if content and not tool_calls:
                step += 1
                print(_cyan + "║" + _reset + f" {_bold}Adım {step}:{_reset} LLM → Nihai özet (ilk 500 karakter):", flush=True)
                for line in (content[:500] + ("..." if len(content) > 500 else "")).split("\n")[:12]:
                    print(_cyan + "║   " + _reset + _gray + line[:64].ljust(64) + _reset + _cyan + " ║" + _reset, flush=True)
                if len(content) > 500:
                    print(_cyan + "║   " + _reset + _dim + f" ... toplam {len(content)} karakter" + _reset + _cyan + " ║" + _reset, flush=True)
                print(_cyan + "║" + _reset, flush=True)
        elif t == "ToolMessage":
            name = getattr(msg, "name", "?")
            content = getattr(msg, "content", "") or ""
            num_chars = len(content)
            preview = (content[:200] + "..." if len(content) > 200 else content).replace("\n", " ")
            print(_cyan + "║" + _reset + f"    ← Tool cevabı ({name}): {num_chars} karakter döndü.", flush=True)
            print(_cyan + "║" + _reset + _dim + f"    Önizleme: {preview[:70]}..." + _reset, flush=True)
            print(_cyan + "║" + _reset, flush=True)

    print(_cyan + "╠" + sep + "╣" + _reset, flush=True)
    print(_cyan + "║" + _reset + f" Toplam mesaj/adım: {len(messages)}  |  Nihai çıktı uzunluğu: {len(out)} karakter" + _cyan + " ║" + _reset, flush=True)
    print(_cyan + "╚" + sep + "╝" + _reset, flush=True)
    print(flush=True)
    return out, messages


# ── RESEARCHER Agent ─────────────────────────────────────────────────────────
#
# Ne yapar: Classifier'dan gelen case summary'yi alır. Sadece search_regulations
# aracını kullanarak DOT belgelerinde (bilgiler/ + RAG index) ilgili yönetmelikleri
# arar. 1–3 odaklı sorgu (örn. delay refund, baggage, cancellation) atar, gelen
# chunk'ları okur ve nihai özeti (hangi kural, hangi belge, vakaya nasıl uygulanır)
# plain text olarak döner. Karar vermez; Analyst'in işi.
#
# Detaylı log: Her soruda terminalde "RESEARCHER AGENT — DETAYLI LOG" kutusunda
# girdi, her tool çağrısı (query metni), her tool cevabı (kaç karakter, önizleme)
# ve nihai özet görünür. search_regulations her çağrıda da [RESEARCHER TOOL] ile
# query, chunk sayısı, kaynak dosyalar ve relevance skorlarını yazar.

RESEARCHER_PROMPT = """You are a Regulation Researcher for airline refund cases.

YOUR ONLY JOB: Search the DOT regulation documents and find rules that apply to this case, then return a summary WITH clear citations so the passenger can see which official rule supports the decision.

EFFICIENCY (use 1–2 queries when possible):
1. Use targeted queries with regulation-style terms so the search matches well: e.g. "significant delay 3 hours domestic refund", "baggage fee refund 12 hours", "14 CFR 259 cancellation", "automatic refund DOT".
2. Prefer one strong query per case type (delay vs baggage vs cancellation). If the first result already contains relevant rules, do NOT search again — summarize from that.
3. After at most 3 tool calls, you MUST output your final summary. Do not call the tool again.

CITATIONS (required — you are the agent that finds the rules; the Writer will use this for links):
4. For each regulation you use, you MUST provide:
   - Official rule name: e.g. "14 CFR 259.4", "14 CFR Part 259", "14 CFR Part 254", "DOT Final Rule on Refunds". Use the exact names that appear in the document so the system can link to the official source.
   - Source document: the file name from the search result (e.g. "14 CFR 259.4 (up to date as of...).pdf").
   - Short quote or one-line summary: the key sentence that applies to this case.
5. End your output with a clear "APPLICABLE RULES FOR CITATION" section: list each rule on one line in the form "14 CFR 259.4 — significant delay refund requirement (domestic 3+ hours)". The Writer will copy these into the decision so the passenger gets clickable links to the official regulation.

OUTPUT FORMAT:
- First: a short narrative summary of what you found and how it applies to this case.
- Then: a "APPLICABLE RULES FOR CITATION" section with one line per rule, each starting with the official rule name (e.g. 14 CFR 259.4, 14 CFR Part 254) so citations can be linked.

Do NOT make a refund decision — that's the Analyst's job. Just find the rules, summarize, and list them for citation."""


def build_researcher(index):
    from refund_tools import make_search_tool
    search_tool = make_search_tool(index)
    researcher_model = os.getenv("OPENAI_RESEARCHER_MODEL", "gpt-4o")
    return _build_worker(RESEARCHER_PROMPT, [search_tool], model=researcher_model)


# ── ANALYST Agent ────────────────────────────────────────────────────────────

ANALYST_PROMPT = """You are a Refund Analyst for airline refund cases.

YOUR ONLY JOB: Use your tools to check thresholds, calculate amounts, and determine timelines. Do NOT write letters or search documents — other agents handle those.

CURRENCY RULE: We always respond in US dollars (USD). If the passenger states amounts in another currency (e.g. EUR, TRY, GBP), use convert_currency to convert to USD first. All amounts in your analysis and in refund_details must be stated in USD (e.g. $250.00 USD). Never leave amounts in the passenger's currency in the final output.

INSTRUCTIONS:
1. Based on the case type, call the appropriate threshold checker tool.
2. ALWAYS trust the tool results — do NOT override them with your own reasoning.
3. If the case involves a refund amount: if it was given in a non-USD currency, call convert_currency(amount, from_currency, "USD") first, then use the USD amount in calculate_refund and in your output.
4. Always use calculate_refund_timeline to determine the deadline.
5. State your recommendation clearly: APPROVED, DENIED, or PARTIAL.

OUTPUT FORMAT: Return a structured analysis with:
- Threshold check results (quote the tool output)
- Refund amount in USD (e.g. $XXX.XX USD) if applicable
- Refund deadline
- Your recommendation: APPROVED, DENIED, or PARTIAL
- Clear reasoning for your recommendation

CRITICAL: If a tool says "NOT significantly delayed" or "does NOT meet threshold", your recommendation MUST be DENIED. Never override tool results."""


def build_analyst():
    from refund_tools import (
        check_delay_threshold,
        check_baggage_threshold,
        calculate_refund,
        calculate_refund_timeline,
    )
    from app.tools.currency import convert_currency
    tools = [
        check_delay_threshold,
        check_baggage_threshold,
        calculate_refund,
        calculate_refund_timeline,
        convert_currency,
    ]
    return _build_worker(ANALYST_PROMPT, tools)


# ── WRITER Agent ─────────────────────────────────────────────────────────────

WRITER_PROMPT = """You are a Decision Writer for airline refund cases.

YOUR ONLY JOB: Take the Analyst's recommendation and the Researcher's regulations, and write a clear, passenger-friendly decision with a formal letter (if approved).

CURRENCY RULE: We always state amounts in US dollars (USD). The refund_amount you pass to generate_decision_letter must be in USD (e.g. "$250.00 USD" or "$1,500.00 USD"). If the Analyst gave you an amount in another currency, convert it to USD before writing; otherwise use the Analyst's USD amount as-is.

INSTRUCTIONS:
1. Write the final decision based on the Analyst's recommendation — do NOT change the APPROVED/DENIED/PARTIAL outcome.
2. If the decision is APPROVED or PARTIAL, use generate_decision_letter to create a formal letter. Always pass the refund amount in USD (e.g. "$XXX.XX USD").
3. Write clear action items for the passenger.
4. For applicable_regulations: use the Researcher's "APPLICABLE RULES FOR CITATION" section if present (each line is already formatted for citation links). Otherwise list each rule with its official name first (e.g. "14 CFR 259.4 — ...") so the passenger gets clickable links to the official source.

OUTPUT FORMAT: Return valid JSON with this schema:
{
  "decision": "APPROVED" | "DENIED" | "PARTIAL",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "analysis_steps": ["Step 1 — ...", ...],
  "reasons": ["reason 1", ...],
  "applicable_regulations": ["regulation 1 (include rule name e.g. 14 CFR 259.4)", ...],
  "refund_details": {"refund_type": "...", "refund_amount": "... (always in USD e.g. $250.00 USD)", "payment_method": "...", "timeline": "..."} or null,
  "passenger_action_items": ["action 1", ...],
  "decision_letter": "..." or null
}

Return ONLY the JSON."""


def build_writer():
    from refund_tools import generate_decision_letter
    return _build_worker(WRITER_PROMPT, [generate_decision_letter])


# ── SUPERVISOR ───────────────────────────────────────────────────────────────

def run_multi_agent(
    index,
    researcher_agent,
    analyst_agent,
    writer_agent,
    case_summary: str,
) -> MultiAgentResult:
    """
    Supervisor coordinates three workers:
      1. Researcher finds regulations
      2. Analyst checks thresholds and calculates (with Researcher's findings)
      3. Writer produces final decision (with both previous outputs)
    """
    result = MultiAgentResult()

    # ── Step 1: Researcher ───────────────────────────────────────────────
    result.agent_log.append("📚 **Researcher** — Finding applicable regulations...")
    researcher_task = (
        f"Find all DOT regulations that apply to this case:\n\n{case_summary}"
    )
    researcher_messages = []
    try:
        researcher_output, researcher_messages = _run_researcher_with_detailed_log(
            researcher_agent, researcher_task, recursion_limit=RESEARCHER_RECURSION_LIMIT,
        )
    except GraphRecursionError:
        researcher_output = (
            "[Researcher step limit reached — used too many search steps. "
            "Summarizing from available context.] No specific regulations retrieved; "
            "Analyst will rely on standard DOT delay/baggage rules."
        )
        result.agent_log.append(
            f"   ⚠️ Researcher hit step limit ({RESEARCHER_RECURSION_LIMIT}); using fallback summary."
        )
    if researcher_messages:
        _res_tools = _extract_tool_calls_from_messages(researcher_messages)
        _append_tool_log_to_result(result, "Researcher", _res_tools, "📚")
        _print_tool_log_terminal("Researcher", _res_tools, "\033[96m")
    result.researcher_output = WorkerOutput(
        agent_name="Researcher",
        result=researcher_output,
        tools_used=["search_regulations"],
    )
    preview = researcher_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Found regulations: {preview}...")

    # ── Step 2: Analyst ──────────────────────────────────────────────────
    analyst_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    _b, _yellow, _r = "\033[1m", "\033[93m", "\033[0m"
    print(f"{_yellow}{_b}[ANALYST] Model: {analyst_model}{_r}", flush=True)
    result.agent_log.append("\n🔢 **Analyst** — Checking thresholds and calculating...")
    analyst_task = (
        f"Analyze this case using your tools.\n\n"
        f"CASE:\n{case_summary}\n\n"
        f"REGULATIONS FOUND BY RESEARCHER:\n{researcher_output}"
    )
    analyst_output, analyst_messages = _run_worker_return_messages(
        analyst_agent, analyst_task,
        log_prefix="Agent Analyst (tools: check_delay_threshold, check_baggage_threshold, calculate_refund, calculate_refund_timeline, convert_currency)",
    )
    _analyst_tools = _extract_tool_calls_from_messages(analyst_messages)
    _append_tool_log_to_result(result, "Analyst", _analyst_tools, "🔢")
    _print_tool_log_terminal("Analyst", _analyst_tools, "\033[93m")
    result.analyst_output = WorkerOutput(
        agent_name="Analyst",
        result=analyst_output,
        tools_used=["check_delay_threshold", "check_baggage_threshold", "calculate_refund", "calculate_refund_timeline", "convert_currency"],
    )
    preview = analyst_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Analysis complete: {preview}...")

    # ── Step 3: Writer ───────────────────────────────────────────────────
    writer_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    _b, _green, _r = "\033[1m", "\033[92m", "\033[0m"
    print(f"{_green}{_b}[WRITER] Model: {writer_model}{_r}", flush=True)
    result.agent_log.append("\n✍️ **Writer** — Drafting decision and letter...")
    writer_task = (
        f"Write the final decision based on the Analyst's recommendation.\n\n"
        f"CASE:\n{case_summary}\n\n"
        f"REGULATIONS (from Researcher):\n{researcher_output}\n\n"
        f"ANALYSIS (from Analyst):\n{analyst_output}\n\n"
        f"Write the decision as JSON. If APPROVED or PARTIAL, also generate a formal letter."
    )
    writer_output, writer_messages = _run_worker_return_messages(
        writer_agent, writer_task,
        log_prefix="Agent Writer (tool: generate_decision_letter)",
    )
    _writer_tools = _extract_tool_calls_from_messages(writer_messages)
    _append_tool_log_to_result(result, "Writer", _writer_tools, "✍️")
    _print_tool_log_terminal("Writer", _writer_tools, "\033[92m")
    result.writer_output = WorkerOutput(
        agent_name="Writer",
        result=writer_output,
        tools_used=["generate_decision_letter"],
    )

    # Parse the Writer's JSON output
    cleaned = writer_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        decision = json.loads(cleaned)
    except json.JSONDecodeError:
        decision = {
            "decision": "ERROR",
            "confidence": "LOW",
            "analysis_steps": ["Writer failed to produce valid JSON."],
            "reasons": [writer_output[:300]],
            "applicable_regulations": [],
            "refund_details": None,
            "passenger_action_items": ["Please try again."],
            "decision_letter": None,
        }

    decision["agents_used"] = ["Researcher", "Analyst", "Writer"]
    result.supervisor_decision = decision
    result.agent_log.append(f"\n🟣 **Supervisor** — Final decision: {decision.get('decision', '?')}")

    # Citation validation: link + Researcher list + retrieval grounding
    retrieval_chunks = _extract_researcher_retrieval_chunks(researcher_messages)
    result.citation_validation = validate_citations(
        decision.get("applicable_regulations", []),
        researcher_output=result.researcher_output.result,
        retrieval_chunks=retrieval_chunks,
    )
    result.agent_log.append("\n" + format_validation_for_log(result.citation_validation))
    if not result.citation_validation.is_ok:
        print("\033[93m[CITATION] " + result.citation_validation.summary + "\033[0m", flush=True)

    return result


def run_multi_agent_streaming(
    index,
    researcher_agent,
    analyst_agent,
    writer_agent,
    case_summary: str,
):
    """
    Same as run_multi_agent but yields (ma_result_so_far, step_name) after each worker
    so the UI can show progress. step_name is "researcher" | "analyst" | "writer" | "done".
    """
    result = MultiAgentResult()

    # ── Step 1: Researcher ───────────────────────────────────────────────
    print("[FLOW] 📚 Researcher — running...", flush=True)
    result.agent_log.append("📚 **Researcher** — Finding applicable regulations...")
    researcher_task = (
        f"Find all DOT regulations that apply to this case:\n\n{case_summary}"
    )
    researcher_messages = []
    try:
        researcher_output, researcher_messages = _run_researcher_with_detailed_log(
            researcher_agent, researcher_task, recursion_limit=RESEARCHER_RECURSION_LIMIT,
        )
    except GraphRecursionError:
        researcher_output = (
            "[Researcher step limit reached — used too many search steps. "
            "Summarizing from available context.] No specific regulations retrieved; "
            "Analyst will rely on standard DOT delay/baggage rules."
        )
        result.agent_log.append(
            f"   ⚠️ Researcher hit step limit ({RESEARCHER_RECURSION_LIMIT}); using fallback summary."
        )
    if researcher_messages:
        _res_tools = _extract_tool_calls_from_messages(researcher_messages)
        _append_tool_log_to_result(result, "Researcher", _res_tools, "📚")
        _print_tool_log_terminal("Researcher", _res_tools, "\033[96m")
    result.researcher_output = WorkerOutput(
        agent_name="Researcher",
        result=researcher_output,
        tools_used=["search_regulations"],
    )
    preview = researcher_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Found regulations: {preview}...")
    print("[FLOW] 📚 Researcher — done.", flush=True)
    yield result, "researcher"

    # ── Step 2: Analyst ──────────────────────────────────────────────────
    analyst_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    _b, _yellow, _r = "\033[1m", "\033[93m", "\033[0m"
    print(f"{_yellow}{_b}[ANALYST] Model: {analyst_model}{_r}", flush=True)
    print("[FLOW] 🔢 Analyst — running...", flush=True)
    result.agent_log.append("\n🔢 **Analyst** — Checking thresholds and calculating...")
    analyst_task = (
        f"Analyze this case using your tools.\n\n"
        f"CASE:\n{case_summary}\n\n"
        f"REGULATIONS FOUND BY RESEARCHER:\n{researcher_output}"
    )
    analyst_output, analyst_messages = _run_worker_return_messages(
        analyst_agent, analyst_task,
        log_prefix="Agent Analyst (tools: check_delay_threshold, check_baggage_threshold, calculate_refund, calculate_refund_timeline, convert_currency)",
    )
    _analyst_tools = _extract_tool_calls_from_messages(analyst_messages)
    _append_tool_log_to_result(result, "Analyst", _analyst_tools, "🔢")
    _print_tool_log_terminal("Analyst", _analyst_tools, "\033[93m")
    result.analyst_output = WorkerOutput(
        agent_name="Analyst",
        result=analyst_output,
        tools_used=["check_delay_threshold", "check_baggage_threshold", "calculate_refund", "calculate_refund_timeline", "convert_currency"],
    )
    preview = analyst_output[:150].replace("\n", " ")
    result.agent_log.append(f"   ✓ Analysis complete: {preview}...")
    print("[FLOW] 🔢 Analyst — done.", flush=True)
    yield result, "analyst"

    # ── Step 3: Writer ───────────────────────────────────────────────────
    writer_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    _b, _green, _r = "\033[1m", "\033[92m", "\033[0m"
    print(f"{_green}{_b}[WRITER] Model: {writer_model}{_r}", flush=True)
    print("[FLOW] ✍️ Writer — running...", flush=True)
    result.agent_log.append("\n✍️ **Writer** — Drafting decision and letter...")
    writer_task = (
        f"Write the final decision based on the Analyst's recommendation.\n\n"
        f"CASE:\n{case_summary}\n\n"
        f"REGULATIONS (from Researcher):\n{researcher_output}\n\n"
        f"ANALYSIS (from Analyst):\n{analyst_output}\n\n"
        f"Write the decision as JSON. If APPROVED or PARTIAL, also generate a formal letter."
    )
    writer_output, writer_messages = _run_worker_return_messages(
        writer_agent, writer_task,
        log_prefix="Agent Writer (tool: generate_decision_letter)",
    )
    _writer_tools = _extract_tool_calls_from_messages(writer_messages)
    _append_tool_log_to_result(result, "Writer", _writer_tools, "✍️")
    _print_tool_log_terminal("Writer", _writer_tools, "\033[92m")
    result.writer_output = WorkerOutput(
        agent_name="Writer",
        result=writer_output,
        tools_used=["generate_decision_letter"],
    )

    cleaned = writer_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    try:
        decision = json.loads(cleaned)
    except json.JSONDecodeError:
        decision = {
            "decision": "ERROR",
            "confidence": "LOW",
            "analysis_steps": ["Writer failed to produce valid JSON."],
            "reasons": [writer_output[:300]],
            "applicable_regulations": [],
            "refund_details": None,
            "passenger_action_items": ["Please try again."],
            "decision_letter": None,
        }

    decision["agents_used"] = ["Researcher", "Analyst", "Writer"]
    result.supervisor_decision = decision
    result.agent_log.append(f"\n🟣 **Supervisor** — Final decision: {decision.get('decision', '?')}")

    # Citation validation: link + Researcher list + retrieval grounding
    retrieval_chunks = _extract_researcher_retrieval_chunks(researcher_messages)
    result.citation_validation = validate_citations(
        decision.get("applicable_regulations", []),
        researcher_output=result.researcher_output.result,
        retrieval_chunks=retrieval_chunks,
    )
    result.agent_log.append("\n" + format_validation_for_log(result.citation_validation))
    if not result.citation_validation.is_ok:
        print("\033[93m[CITATION] " + result.citation_validation.summary + "\033[0m", flush=True)

    print("[FLOW] ✍️ Writer — done.", flush=True)
    yield result, "writer"


# ── Formatting ───────────────────────────────────────────────────────────────

def format_multi_agent_decision(result: MultiAgentResult) -> str:
    d = result.supervisor_decision
    decision = d.get("decision", "UNKNOWN")
    emoji = {"APPROVED": "✅", "DENIED": "❌", "PARTIAL": "⚠️"}.get(decision, "❓")

    lines = [
        f"# {emoji} Decision: {decision}",
        f"**Confidence:** {d.get('confidence', '?')}",
        "",
        f"**Agents Used:** 📚 Researcher → 🔢 Analyst → ✍️ Writer",
        "",
    ]

    if d.get("judge_override"):
        lines.append("🔴 **Judge Override Applied**")
        lines.append(f"*{d.get('judge_explanation', '')}*")
        lines.append("")

    lines += ["---", "## 🔍 Analysis"]
    for step in d.get("analysis_steps", []):
        lines.append(f"- {step}")

    lines += ["", "---", "## 📋 Reasons"]
    for reason in d.get("reasons", []):
        lines.append(f"- {reason}")

    lines += ["", "---", "## 📜 Regulations & citations"]
    lines.append("*Karar aşağıdaki kurallara dayanmaktadır. Linkler resmi kaynağa gider; eCFR linkleri ilgili bölüm sayfasına (tek ekran) gider.*")
    lines.append("")
    for reg in d.get("applicable_regulations", []):
        lines.append(format_regulation_with_citation(reg))
    if getattr(result, "citation_validation", None) and not result.citation_validation.is_ok:
        lines.append("")
        lines.append(f"*🔗 Citation check: {result.citation_validation.summary} (see Agent Log for details)*")

    refund = d.get("refund_details")
    if refund:
        lines += ["", "---", "## 💰 Refund Details"]
        for k, v in refund.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")

    lines += ["", "---", "## 📝 What You Should Do"]
    for action in d.get("passenger_action_items", []):
        lines.append(f"- {action}")

    letter = d.get("decision_letter")
    if letter:
        lines += ["", "---", "## ✉️ Formal Letter", "", "```", letter, "```"]

    return "\n".join(lines)


def _classifier_output_to_dict(classifier_output):
    """ClassifierOutput dataclass -> dict for JSON serialization."""
    return asdict(classifier_output)


def format_classifier_json_for_ui(classifier_output) -> str:
    """Pretty Markdown block with Classifier JSON for the Agent Log tab."""
    d = _classifier_output_to_dict(classifier_output)
    json_str = json.dumps(d, indent=2, ensure_ascii=False)
    return (
        "## 🔵 Classifier Output (JSON)\n\n"
        "*Structured data passed to Researcher agent.*\n\n"
        "```json\n"
        + json_str
        + "\n```"
    )


def print_classifier_json_terminal(classifier_output) -> None:
    """Print Classifier JSON to terminal with pretty formatting and colors."""
    d = _classifier_output_to_dict(classifier_output)
    json_str = json.dumps(d, indent=2, ensure_ascii=False)
    cyan = "\033[96m"
    bold = "\033[1m"
    gray = "\033[37m"
    reset = "\033[0m"
    sep = "─" * 62
    print(flush=True)
    print(cyan + sep + reset, flush=True)
    print(bold + cyan + "  🔵 CLASSIFIER OUTPUT (JSON) → Researcher'a giden veri" + reset, flush=True)
    print(cyan + sep + reset, flush=True)
    for line in json_str.splitlines():
        print(gray + line + reset, flush=True)
    print(cyan + sep + reset, flush=True)
    print(flush=True)


def format_agent_log(result: MultiAgentResult) -> str:
    lines = ["## 🤖 Multi-Agent Execution Log", ""]
    lines.extend(result.agent_log)

    lines += [
        "", "---",
        "## 📚 Researcher's Full Output",
        "", result.researcher_output.result,
        "", "---",
        "## 🔢 Analyst's Full Output",
        "", result.analyst_output.result,
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
    from refund_agent import build_or_load_index
    from llm_pipeline import run_classifier, run_judge, format_pipeline_log, PipelineResult
    from decision_cache import DecisionCache, _get_embedding
    from decision_db import DecisionDB

    print("[MULTI-AGENT] Building index...")
    index = build_or_load_index()

    print("[MULTI-AGENT] Building worker agents...")
    _researcher_model = os.getenv("OPENAI_RESEARCHER_MODEL", "gpt-4o")
    print(f"[CONFIG] OPENAI_RESEARCHER_MODEL = {_researcher_model} (from .env)")
    researcher_agent = build_researcher(index)
    analyst_agent = build_analyst()
    writer_agent = build_writer()

    cache = DecisionCache()
    db = DecisionDB()
    db_status = f" | DB: {db.stats()['count']} rows" if db.enabled else ""
    print(f"[MULTI-AGENT] Ready. 3 workers + supervisor. Cache: {cache.stats['total_entries']} entries.{db_status}")

    def _status_str():
        return f"📊 Cache: {cache.stats['total_entries']} entries"

    def _print_flow_diagram(steps, decision):
        """Print the flow path taken (cyan, visible in log)."""
        _cyan = "\033[96m"
        _end = "\033[0m"
        print(f"\n{_cyan}[FLOW DIAGRAM]", flush=True)
        print("  " + " → ".join(steps), flush=True)
        print(f"  Decision: {decision}{_end}\n", flush=True)

    def _print_summary_for_question(question_preview, source, decision, flow_steps, from_cache=False, cache_entries=0, stored_msg=None):
        """Print a short summary for this question (one block, easy to find)."""
        _cyan = "\033[96m"
        _end = "\033[0m"
        print(f"\n{_cyan}[SUMMARY FOR THIS QUESTION]{_end}", flush=True)
        print(f"  Question: {question_preview[:100]}{'...' if len(question_preview) > 100 else ''}", flush=True)
        print(f"  Source:   {source}", flush=True)
        print(f"  Decision: {decision}", flush=True)
        print(f"  Path:     {' → '.join(flow_steps)}", flush=True)
        if stored_msg:
            print(f"  Stored:   {stored_msg}", flush=True)
        elif from_cache:
            print(f"  Stored:   cache ({cache_entries} entries) — no new save.", flush=True)
        print(flush=True)

    def analyze(case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description):
        if not description or not description.strip():
            return "⚠️ Please describe what happened.", "", ""

        try:
            return _analyze_impl(
                case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description, cache, db, index,
                researcher_agent, analyst_agent, writer_agent,
            )
        except Exception as e:
            tb = traceback.format_exc()
            err_msg = str(e)
            print(f"\n[ERROR] {type(e).__name__}: {err_msg}\n{tb}\n")
            decision_md = (
                "## ❌ Error\n\n"
                f"**{type(e).__name__}:** {err_msg}\n\n"
                "### Traceback (for debugging)\n\n"
                f"```\n{tb}\n```"
            )
            status_err = f"❌ Error: {err_msg[:80]}{'…' if len(err_msg) > 80 else ''}"
            log_md = (
                "## 🔴 Error during analysis\n\n"
                f"**Exception:** `{type(e).__name__}: {err_msg}`\n\n"
                "**Full traceback:**\n\n"
                f"```\n{tb}\n```"
            )
            return decision_md, status_err, log_md

    def analyze_streaming(case_type, flight_type, ticket_type, payment_method,
                          accepted_alternative, description):
        """Generator that yields (decision_md, status, log_md) after each step so you can watch the flow."""
        if not description or not description.strip():
            yield "⚠️ Please describe what happened.", _status_str(), ""
            return
        try:
            for decision_md, status, log_md in _analyze_impl_streaming(
                case_type, flight_type, ticket_type, payment_method,
                accepted_alternative, description, cache, db, index,
                researcher_agent, analyst_agent, writer_agent,
            ):
                yield decision_md, status, log_md
        except Exception as e:
            tb = traceback.format_exc()
            err_msg = str(e)
            print(f"\n[ERROR] {type(e).__name__}: {err_msg}\n{tb}\n")
            yield (
                f"## ❌ Error\n\n**{type(e).__name__}:** {err_msg}\n\n```\n{tb}\n```",
                f"❌ Error: {err_msg[:80]}{'…' if len(err_msg) > 80 else ''}",
                f"## 🔴 Error\n\n```\n{tb}\n```",
            )

    def _analyze_impl(case_type, flight_type, ticket_type, payment_method,
                      accepted_alternative, description, cache, db, index,
                      researcher_agent, analyst_agent, writer_agent):
        cached_result, cache_status = cache.lookup(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        if cached_result:
            label = {"exact_hit": "⚡ EXACT HIT", "semantic_hit": "🔍 SIMILAR"}.get(cache_status, "")
            return (
                format_multi_agent_decision(MultiAgentResult(supervisor_decision=cached_result)),
                f"📊 Cache: {label} | {cache.stats['total_entries']} entries",
                "*Served from cache.*",
            )

        query_embedding = None  # used for DB semantic and for storing after RAG
        # DB exact hit
        db_result = db.get_by_hash(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        ) if db.enabled else None
        if db_result:
            return (
                format_multi_agent_decision(MultiAgentResult(supervisor_decision=db_result)),
                f"📊 Cache: {cache.stats['total_entries']} entries (exact hit)",
                "*Served from DB (exact).*",
            )

        # DB semantic hit (need query embedding)
        query_embedding = None
        if db.enabled and description.strip():
            query_embedding = _get_embedding(description)
            db_result = db.get_by_semantic(query_embedding, threshold=0.90)
            if db_result:
                return (
                    format_multi_agent_decision(MultiAgentResult(supervisor_decision=db_result)),
                    f"📊 Cache: {cache.stats['total_entries']} entries (semantic hit)",
                    "*Served from DB (semantic ≥90%).*",
                )

        # Stage 1: Classifier
        classifier_output = run_classifier(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )

        case_summary = (
            f"Case Category: {classifier_output.case_category}\n"
            f"Flight Type: {classifier_output.flight_type}\n"
            f"Payment Method: {classifier_output.payment_method}\n"
            f"Accepted Alternative: {'Yes — ' + classifier_output.alternative_type if classifier_output.accepted_alternative else 'No'}\n"
            f"Passenger Traveled: {'Yes' if classifier_output.passenger_traveled else 'No'}\n"
        )
        if classifier_output.flight_duration_hours is not None:
            case_summary += f"Flight Duration: {classifier_output.flight_duration_hours} hours\n"
        if classifier_output.delay_hours is not None:
            case_summary += f"Flight Delay: {classifier_output.delay_hours} hours\n"
        if classifier_output.bag_delay_hours is not None:
            case_summary += f"Baggage Delay: {classifier_output.bag_delay_hours} hours\n"
        if classifier_output.ticket_price is not None:
            case_summary += f"Ticket Price: ${classifier_output.ticket_price}\n"
        if classifier_output.ancillary_fee is not None:
            case_summary += f"Baggage/Ancillary Fee: ${classifier_output.ancillary_fee}\n"
        if classifier_output.original_class:
            case_summary += f"Original Class: {classifier_output.original_class}\n"
        if classifier_output.downgraded_class:
            case_summary += f"Downgraded To: {classifier_output.downgraded_class}\n"
        if classifier_output.original_class_price is not None:
            case_summary += f"Original Class Price: ${classifier_output.original_class_price}\n"
        if classifier_output.downgraded_class_price is not None:
            case_summary += f"Downgraded Class Price: ${classifier_output.downgraded_class_price}\n"
        if classifier_output.airline_name:
            case_summary += f"Airline: {classifier_output.airline_name}\n"
        if classifier_output.flight_number:
            case_summary += f"Flight Number: {classifier_output.flight_number}\n"
        if classifier_output.flight_date:
            case_summary += f"Flight Date: {classifier_output.flight_date}\n"
        case_summary += f"\nKey Facts: {', '.join(classifier_output.key_facts)}"
        case_summary += f"\nOriginal Description: {description}"

        # Stage 2: Multi-Agent (Researcher → Analyst → Writer)
        ma_result = run_multi_agent(
            index, researcher_agent, analyst_agent, writer_agent, case_summary,
        )

        # Stage 3: Judge reviews
        judge_verdict = run_judge(classifier_output, ma_result.supervisor_decision)
        if not judge_verdict.approved and judge_verdict.override_decision:
            final = ma_result.supervisor_decision.copy()
            final["decision"] = judge_verdict.override_decision
            if judge_verdict.override_reasons:
                final["reasons"] = judge_verdict.override_reasons
            final["judge_override"] = True
            final["judge_issues"] = judge_verdict.issues_found
            final["judge_explanation"] = judge_verdict.explanation
            ma_result.supervisor_decision = final
            ma_result.agent_log.append(f"\n🔴 **Judge** — OVERRIDDEN: {judge_verdict.explanation}")
        else:
            ma_result.agent_log.append(f"\n🔴 **Judge** — Approved ✓")

        final = ma_result.supervisor_decision
        if final.get("decision") != "ERROR":
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, final,
            )
            if db.enabled:
                emb = query_embedding if query_embedding is not None else (_get_embedding(description) if description.strip() else None)
                db.insert(
                    case_type, flight_type, ticket_type,
                    payment_method, accepted_alternative, description, final,
                    embedding=emb,
                )

        status = f"📊 Cache: {cache.stats['total_entries']} entries"
        return (
            format_multi_agent_decision(ma_result),
            status,
            format_agent_log(ma_result),
        )

    def _analyze_impl_streaming(case_type, flight_type, ticket_type, payment_method,
                                accepted_alternative, description, cache, db, index,
                                researcher_agent, analyst_agent, writer_agent):
        """Generator: yields (decision_md, status, log_md) after each pipeline step."""
        # Always log incoming user request — very visible block so each question is easy to find in a busy log
        _sep = "=" * 72
        _green = "\033[92m"  # ANSI green
        _bold = "\033[1m"
        _end = "\033[0m"
        desc_preview = ((description or "").strip()[:200] + ("..." if len((description or "").strip()) > 200 else "")) or "(empty)"
        print(_sep, flush=True)
        print(f"{_green}{_bold}>>> USER QUESTION >>>{_end}", flush=True)
        print(f"  case_type={case_type!r}  flight_type={flight_type!r}  ticket_type={ticket_type!r}", flush=True)
        print(f"  payment={payment_method!r}  accepted_alternative={accepted_alternative!r}", flush=True)
        print("  ---", flush=True)
        print(f"  QUESTION:", flush=True)
        print(f"  {desc_preview}", flush=True)
        print("  ---", flush=True)
        print(_sep, flush=True)
        print("[DETAIL FOR THIS QUESTION — every step below until END OF FLOW]", flush=True)
        print("[LOG] Django API: not used — this flow uses local pipeline (Classifier→Researcher→Analyst→Writer→Judge) + JSON cache + PostgreSQL.", flush=True)

        # Track flow for diagram at the end
        flow_steps = ["User Question"]

        # Step 1: Cache (exact then semantic)
        print("[LOG] Step 1 — Checking cache: exact match first (by input hash)...", flush=True)
        cached_result, cache_status = cache.lookup(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        if cached_result:
            flow_steps.extend(["Cache (exact hit)" if cache_status == "exact_hit" else "Cache (semantic hit)", "→ END"])
            label = {"exact_hit": "⚡ EXACT HIT", "semantic_hit": "🔍 SIMILAR"}.get(cache_status, "")
            print(f"[FLOW] Served from cache ({cache_status}) — pipeline skipped.", flush=True)
            _d = cached_result.get("decision", "?")
            _print_summary_for_question(desc_preview, "cache", _d, flow_steps, from_cache=True, cache_entries=cache.stats["total_entries"])
            _print_flow_diagram(flow_steps, _d)
            print(f"\033[96m\033[1m<<< END OF FLOW (decision: {_d}, from cache) <<<\033[0m", flush=True)
            print("=" * 72, flush=True)
            yield (
                format_multi_agent_decision(MultiAgentResult(supervisor_decision=cached_result)),
                f"📊 Cache: {label} | {cache.stats['total_entries']} entries",
                "*Served from cache.*",
            )
            return
        flow_steps.append("Cache (exact miss, semantic miss)")

        # Step 2: DB exact
        query_embedding = None
        if db.enabled:
            print("[LOG] Step 2 — Checking DB: exact match (by hash)...", flush=True)
            db_result = db.get_by_hash(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description,
            )
        else:
            print("[LOG] Step 2 — DB disabled, skipping DB exact and semantic.", flush=True)
            db_result = None
        if db_result:
            flow_steps.extend(["DB (exact hit)", "→ END"])
            print("[FLOW] Served from DB (exact).", flush=True)
            _d = db_result.get("decision", "?")
            _print_summary_for_question(desc_preview, "DB (exact)", _d, flow_steps, from_cache=False)
            _print_flow_diagram(flow_steps, _d)
            print(f"\033[96m\033[1m<<< END OF FLOW (decision: {_d}, from DB exact) <<<\033[0m", flush=True)
            print("=" * 72, flush=True)
            yield (
                format_multi_agent_decision(MultiAgentResult(supervisor_decision=db_result)),
                f"📊 Cache: {cache.stats['total_entries']} entries (exact hit)",
                "*Served from DB (exact).*",
            )
            return
        if db.enabled:
            flow_steps.append("DB (exact miss)")
            print("[LOG] DB exact: miss. Step 3 — Checking DB semantic (comparing to stored embeddings)...", flush=True)
            query_embedding = _get_embedding(description) if description.strip() else None
            db_result = db.get_by_semantic(query_embedding, threshold=0.90) if query_embedding else None
            if db_result:
                flow_steps.extend(["DB (semantic hit)", "→ END"])
                print("[FLOW] Served from DB (semantic).", flush=True)
                _d = db_result.get("decision", "?")
                _print_summary_for_question(desc_preview, "DB (semantic)", _d, flow_steps, from_cache=False)
                _print_flow_diagram(flow_steps, _d)
                print(f"\033[96m\033[1m<<< END OF FLOW (decision: {_d}, from DB semantic) <<<\033[0m", flush=True)
                print("=" * 72, flush=True)
                yield (
                    format_multi_agent_decision(MultiAgentResult(supervisor_decision=db_result)),
                    f"📊 Cache: {cache.stats['total_entries']} entries (semantic hit)",
                    "*Served from DB (semantic ≥90%).*",
                )
                return
            flow_steps.append("DB (semantic miss)")

        # Step 4: Full pipeline
        flow_steps.append("Classifier (LLM)")
        print("[LOG] Cache + DB: miss. Step 4 — Running pipeline: Classifier first...", flush=True)
        print("[FLOW] 🔵 Classifier — running...", flush=True)
        print("[LOG] Classifier (LLM): invoking to extract case fields...", flush=True)
        yield (
            "## ⏳ Flow — Step 1/5\n\n🔵 **Classifier** — Running...",
            _status_str(),
            "## 🤖 Flow\n\n🔵 **Classifier** — Running...",
        )
        classifier_output = run_classifier(
            case_type, flight_type, ticket_type,
            payment_method, accepted_alternative, description,
        )
        case_summary = (
            f"Case Category: {classifier_output.case_category}\n"
            f"Flight Type: {classifier_output.flight_type}\n"
            f"Payment Method: {classifier_output.payment_method}\n"
            f"Accepted Alternative: {'Yes — ' + classifier_output.alternative_type if classifier_output.accepted_alternative else 'No'}\n"
            f"Passenger Traveled: {'Yes' if classifier_output.passenger_traveled else 'No'}\n"
        )
        if classifier_output.flight_duration_hours is not None:
            case_summary += f"Flight Duration: {classifier_output.flight_duration_hours} hours\n"
        if classifier_output.delay_hours is not None:
            case_summary += f"Flight Delay: {classifier_output.delay_hours} hours\n"
        if classifier_output.bag_delay_hours is not None:
            case_summary += f"Baggage Delay: {classifier_output.bag_delay_hours} hours\n"
        if classifier_output.ticket_price is not None:
            case_summary += f"Ticket Price: ${classifier_output.ticket_price}\n"
        if classifier_output.ancillary_fee is not None:
            case_summary += f"Baggage/Ancillary Fee: ${classifier_output.ancillary_fee}\n"
        if classifier_output.original_class:
            case_summary += f"Original Class: {classifier_output.original_class}\n"
        if classifier_output.downgraded_class:
            case_summary += f"Downgraded To: {classifier_output.downgraded_class}\n"
        if classifier_output.original_class_price is not None:
            case_summary += f"Original Class Price: ${classifier_output.original_class_price}\n"
        if classifier_output.downgraded_class_price is not None:
            case_summary += f"Downgraded Class Price: ${classifier_output.downgraded_class_price}\n"
        if classifier_output.airline_name:
            case_summary += f"Airline: {classifier_output.airline_name}\n"
        if classifier_output.flight_number:
            case_summary += f"Flight Number: {classifier_output.flight_number}\n"
        if classifier_output.flight_date:
            case_summary += f"Flight Date: {classifier_output.flight_date}\n"
        case_summary += f"\nKey Facts: {', '.join(classifier_output.key_facts)}"
        case_summary += f"\nOriginal Description: {description}"
        print("[LOG] Classifier (LLM): done.", flush=True)
        _delay = classifier_output.delay_hours
        _bag = classifier_output.bag_delay_hours
        _cat = classifier_output.case_category
        print(f"[LOG] Classifier extracted: case_category={_cat!r} delay_hours={_delay} bag_delay_hours={_bag} key_facts={len(classifier_output.key_facts)} items", flush=True)
        print("[FLOW] 🔵 Classifier — done.", flush=True)
        print_classifier_json_terminal(classifier_output)
        flow_steps.append("Researcher (LLM+tools)")
        print("[LOG] Step 5 — Running Researcher → Analyst → Writer (multi-agent)...", flush=True)

        # Steps 2–4: Researcher → Analyst → Writer (streaming)
        step_labels = {"researcher": (2, "📚 **Researcher**"), "analyst": (3, "🔢 **Analyst**"), "writer": (4, "✍️ **Writer**")}
        ma_result = None
        for ma_result, step in run_multi_agent_streaming(
            index, researcher_agent, analyst_agent, writer_agent, case_summary,
        ):
            num, name = step_labels.get(step, (0, step))
            yield (
                f"## ⏳ Flow — Step {num}/5\n\n{name} — Done. Next: running pipeline...",
                _status_str(),
                format_agent_log(ma_result),
            )
        flow_steps.append("Analyst (LLM+tools)")
        flow_steps.append("Writer (LLM+tools)")
        flow_steps.append("Judge (LLM)")
        print("[LOG] Step 6 — Running Judge (review decision)...", flush=True)
        print("[FLOW] 🔴 Judge — running...", flush=True)
        yield (
            "## ⏳ Flow — Step 5/5\n\n🔴 **Judge** — Reviewing...",
            _status_str(),
            format_agent_log(ma_result),
        )
        judge_verdict = run_judge(classifier_output, ma_result.supervisor_decision)
        if not judge_verdict.approved and judge_verdict.override_decision:
            final = ma_result.supervisor_decision.copy()
            final["decision"] = judge_verdict.override_decision
            if judge_verdict.override_reasons:
                final["reasons"] = judge_verdict.override_reasons
            final["judge_override"] = True
            final["judge_issues"] = judge_verdict.issues_found
            final["judge_explanation"] = judge_verdict.explanation
            ma_result.supervisor_decision = final
            ma_result.agent_log.append(f"\n🔴 **Judge** — OVERRIDDEN: {judge_verdict.explanation}")
        else:
            ma_result.agent_log.append(f"\n🔴 **Judge** — Approved ✓")
        print(f"[FLOW] 🔴 Judge — done. Decision: {ma_result.supervisor_decision.get('decision', '?')}", flush=True)
        final = ma_result.supervisor_decision
        if final.get("decision") != "ERROR":
            flow_steps.append("Save (cache + Excel + DB)")
            print("[LOG] Step 7 — Saving result: cache (JSON + Excel) and PostgreSQL.", flush=True)
            cache.store(
                case_type, flight_type, ticket_type,
                payment_method, accepted_alternative, description, final,
            )
            if db.enabled:
                emb = query_embedding if query_embedding is not None else (_get_embedding(description) if description.strip() else None)
                db.insert(
                    case_type, flight_type, ticket_type,
                    payment_method, accepted_alternative, description, final,
                    embedding=emb,
                )
        flow_steps.append("→ END")
        _decision = ma_result.supervisor_decision.get("decision", "?")
        _stored = f"cache ({cache.stats['total_entries']} entries), Excel (decision_log.xlsx)" + (", DB (1 row)" if db.enabled else "")
        _print_summary_for_question(desc_preview, "full pipeline (Classifier→Researcher→Analyst→Writer→Judge)", _decision, flow_steps, stored_msg=_stored)
        _print_flow_diagram(flow_steps, _decision)
        print(f"\033[96m\033[1m<<< END OF FLOW (decision: {_decision}) <<<\033[0m", flush=True)
        print("=" * 72, flush=True)
        yield (
            format_multi_agent_decision(ma_result),
            _status_str(),
            format_agent_log(ma_result),
        )

    def clear_cache():
        cache.clear()
        return "📊 Cache: 0 entries"

    def import_from_excel():
        imported, skipped = cache.import_from_excel(compute_embeddings=True)
        return f"📊 Cache: {cache.stats['total_entries']} entries (imported {imported}, skipped {skipped} duplicates)"

    with gr.Blocks(title="Airlines Refund Multi-Agent", theme=gr.themes.Soft()) as app:
        gr.Markdown("# ✈️ Airlines Refund — Multi-Agent System")
        gr.Markdown(
            "**Step 5: Agent-to-Agent** — A Supervisor coordinates three worker agents: "
            "📚 **Researcher** (finds regulations) → 🔢 **Analyst** (checks thresholds) → "
            "✍️ **Writer** (drafts decision). Then 🔴 **Judge** reviews."
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 📋 Case Details")
                case_type = gr.Dropdown(choices=CASE_TYPES, value=CASE_TYPES[0], label="Case Type")
                flight_type = gr.Dropdown(choices=FLIGHT_TYPES, value=FLIGHT_TYPES[0], label="Flight Type")
                ticket_type = gr.Dropdown(choices=TICKET_TYPES, value=TICKET_TYPES[1], label="Ticket Type")
                payment_method = gr.Dropdown(choices=PAYMENT_METHODS, value=PAYMENT_METHODS[0], label="Payment Method")
                accepted_alternative = gr.Dropdown(choices=ACCEPTED_ALTERNATIVES, value=ACCEPTED_ALTERNATIVES[0], label="Did you accept any alternative?")
                description = gr.Textbox(label="Describe what happened", placeholder="Example: My flight was cancelled...", lines=5)
                submit_btn = gr.Button("🤖 Run Multi-Agent Analysis", variant="primary", size="lg")

            with gr.Column(scale=1):
                with gr.Tabs():
                    with gr.Tab("📄 Decision"):
                        output = gr.Markdown(value="*Submit a case to run the multi-agent system.*")
                    with gr.Tab("🤖 Agent Log"):
                        agent_log = gr.Markdown(value="*Agent execution details will appear here.*")
                gr.Markdown("---")
                cache_display = gr.Textbox(
                    label="Status",
                    value=f"📊 Cache: {cache.stats['total_entries']} entries",
                    interactive=False,
                )
                with gr.Row():
                    clear_btn = gr.Button("🗑️ Clear Cache", size="sm")
                    import_excel_btn = gr.Button("📥 Import from Excel", size="sm")

        submit_btn.click(
            fn=analyze_streaming,
            inputs=[case_type, flight_type, ticket_type, payment_method, accepted_alternative, description],
            outputs=[output, cache_display, agent_log],
        )
        clear_btn.click(fn=clear_cache, outputs=cache_display)
        import_excel_btn.click(fn=import_from_excel, outputs=cache_display)

        gr.Markdown("---")
        gr.Markdown(
            "**Agents:** 🔵 Classifier → 🟣 Supervisor → 📚 Researcher → 🔢 Analyst → ✍️ Writer → 🔴 Judge  \n"
            "**Tools:** `search_regulations` · `check_delay_threshold` · `check_baggage_threshold` · "
            "`calculate_refund` · `calculate_refund_timeline` · `generate_decision_letter`"
        )

    return app


class _Tee:
    """Write to both stdout and a log file so you can tail -f the log."""

    def __init__(self, stream, path):
        self._stream = stream
        self._path = path
        self._file = open(path, "a", encoding="utf-8")

    def isatty(self):
        return self._stream.isatty()

    def write(self, data):
        self._stream.write(data)
        try:
            self._file.write(data)
            self._file.flush()
        except OSError:
            pass

    def flush(self):
        self._stream.flush()
        try:
            self._file.flush()
        except OSError:
            pass

    def close(self):
        try:
            self._file.close()
        except OSError:
            pass


if __name__ == "__main__":
    base_port = int(os.getenv("GRADIO_SERVER_PORT", "7861"))
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "multi_agent.log"
    _tee = _Tee(sys.stdout, log_file)
    sys.stdout = _tee
    sys.stderr = _tee
    print(f"[LOG] Writing to {log_file} (watch with: tail -f {log_file})")

    app = create_gradio_app()
    port = base_port
    for attempt in range(5):
        try:
            if attempt > 0:
                print(f"Port {base_port} in use. Using port {port} — open http://127.0.0.1:{port}")
            app.launch(server_name="0.0.0.0", server_port=port)
            break
        except OSError as e:
            if "address already in use" in str(e).lower() or "Errno 48" in str(e):
                port = base_port + attempt + 1
                if attempt < 4:
                    continue
            raise
