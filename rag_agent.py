"""
RAG Agent: Notepad + Kısa/Uzun Bellek + Araçlar (Tools) + Tool döngüsü.
- search_documents: belgelerde arama (RAG)
- read_notepad / write_notepad: notepad okuma/yazma
- remember / recall: uzun süreli bellek
- Kısa bellek: son N sohbet turu
- LangChain Agent + AgentExecutor ile tool döngüsü
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Terminalde akışı okunaklı göstermek için callback
try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.agents import AgentFinish
except Exception:
    BaseCallbackHandler = None
    AgentFinish = None


class AkisCallbackHandler(BaseCallbackHandler if BaseCallbackHandler else object):
    """Terminalde araç döngüsü, kullanılan araçlar ve API çağrılarını detaylı loglar."""

    def __init__(self):
        self._adim = 0
        self._tools_used = []   # [("remember", 1), ("recall", 2)] gibi sıralı araç listesi
        self._dongu_no = 0      # tool döngü sayacı
        self._llm_calls = 0     # kaç kez LLM çağrıldı

    def _adim_artir(self):
        self._adim += 1
        return self._adim

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._llm_calls += 1
        kw = serialized.get("kwargs") or {}
        model = kw.get("model") or kw.get("model_name") or "gpt-4o-mini"
        print("\n[API] OpenAI Chat API çağrılıyor (model: {}) – LLM düşünüyor / cevap üretiyor (#{})".format(model, self._llm_calls))
        if prompts and len(prompts[0]) > 100:
            print("[API] Girdi uzunluğu: {} karakter".format(len(prompts[0])))

    def on_llm_end(self, response, **kwargs):
        print("[API] OpenAI Chat API yanıt aldı.")

    def on_tool_start(self, serialized, input_str, **kwargs):
        name = serialized.get("name", "?")
        self._tools_used.append(name)
        self._dongu_no += 1
        self._adim = self._adim_artir()
        print("\n" + "=" * 60)
        print("[AKIŞ] Adım {} | TOOL DÖNGÜSÜ #{}: ARAÇ = {}".format(self._adim, self._dongu_no, name))
        print("[AKIŞ] Araç girişi: {}".format((input_str[:300] + "…") if len(input_str) > 300 else input_str))
        if name == "search_documents":
            print("[API] (Bu araç içeride OpenAI Embeddings API kullanır: text-embedding-3-small)")
        print("=" * 60)

    def on_tool_end(self, output, **kwargs):
        out_str = str(output) if output else ""
        if len(out_str) > 400:
            out_str = out_str[:400] + "\n... (kısaltıldı)"
        print("[AKIŞ] Araç çıkışı (özet):\n{}".format(out_str))
        print("-" * 60)

    def on_agent_finish(self, finish: "AgentFinish", **kwargs):
        self._adim = self._adim_artir()
        out = (finish.return_values.get("output") or "")[:300]
        if len(out) > 300:
            out = out + "…"
        print("\n[AKIŞ] Adım {}: AGENT CEVABI ÜRETTİ (ilk 300 karakter):\n{}".format(self._adim, out))
        print("=" * 60)
        # Özet: kullanılan araçlar
        if self._tools_used:
            from collections import Counter
            tool_counts = Counter(self._tools_used)
            summary_tools = ", ".join("{} ({}x)".format(t, c) for t, c in tool_counts.items())
            print("[ÖZET] Kullanılan araçlar (tool döngüsü): {}".format(summary_tools))
            print("[ÖZET] Toplam tool çağrısı: {}".format(len(self._tools_used)))
        else:
            print("[ÖZET] Bu turda araç çağrılmadı (doğrudan cevap).")
        # Özet: kullanılan API'ler
        apis = ["OpenAI Chat (gpt-4o-mini): {} çağrı".format(self._llm_calls)]
        if "search_documents" in (self._tools_used or []):
            apis.append("OpenAI Embeddings (text-embedding-3-small): search_documents içinde")
        print("[ÖZET] Kullanılan API'ler: " + "; ".join(apis))
        print("=" * 60 + "\n")

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY bulunamadı. .env dosyasına ekleyin.")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

PROJECT_ROOT = Path(__file__).resolve().parent
BILGILER_DIR = PROJECT_ROOT / "bilgiler"
INDEX_DIR = PROJECT_ROOT / "storage"

# Kısa bellek: son kaç tur sohbet agent'a verilecek
SHORT_MEMORY_TURNS = 6


def build_or_load_index():
    """LlamaIndex ile indeks oluşturur veya storage'dan yükler."""
    from llama_index.core import (
        SimpleDirectoryReader,
        VectorStoreIndex,
        StorageContext,
        load_index_from_storage,
        Settings,
    )
    from llama_index.embeddings.openai import OpenAIEmbedding

    BILGILER_DIR.mkdir(parents=True, exist_ok=True)
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    required_exts = [".pdf", ".docx", ".doc", ".txt", ".md"]

    if INDEX_DIR.exists():
        try:
            storage_context = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
            index = load_index_from_storage(storage_context)
            print("[RAG] İndeks storage'dan yüklendi.")
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
        print("[RAG] bilgiler/ klasöründe dosya yok.")
        return None
    print(f"[RAG] İndeks oluşturuluyor: {len(documents)} belge...")
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[RAG] İndeks hazır.")
    return index


def make_tools(index):
    """İndeks ve bellek dosyalarına bağlı LangChain araçlarını döner."""
    from langchain_core.tools import tool

    from memory_utils import read_notepad, write_notepad, remember_fact, recall_fact

    @tool
    def search_documents(query: str) -> str:
        """Belgelerde (PDF, Word, metin) arama yapar. İade, uçuş iptali, bilet, bagaj, DOT kuralları vb. konularda kullan."""
        if index is None:
            return "Belge indeksi yok. Önce bilgiler/ klasörüne dosya ekleyin."
        retriever = index.as_retriever(similarity_top_k=8)
        nodes = retriever.retrieve(query)
        if not nodes:
            return "İlgili parça bulunamadı."
        return "\n\n".join(n.get_content() for n in nodes)

    @tool
    def read_notepad_tool() -> str:
        """Notepad'in şu anki içeriğini okur."""
        return read_notepad() or "(Notepad boş)"

    @tool
    def write_notepad_tool(content: str, mode: str = "overwrite") -> str:
        """Notepad'e yazar. mode: 'overwrite' (varsayılan) veya 'append'."""
        return write_notepad(content, mode)

    @tool
    def remember(key: str, value: str) -> str:
        """Kullanıcının söylediği bir bilgiyi uzun süreli belleğe kaydeder. 'Adım Ali' / 'My name is X' gibi cümlelerde mutlaka çağır: key='isim' veya 'name', value=isim. Tercih vb. için de key/value kullan."""
        return remember_fact(key, value)

    @tool
    def recall(key: str = "") -> str:
        """Kaydedilmiş bilgiyi okur. 'Adım ne?', 'Nerede yaşıyorum?', 'Hangi şehirde?' sorularda önce bunu çağır: key='isim' veya key='şehir'. key boşsa tüm kayıtlar döner."""
        return recall_fact(key if key else None)

    return [search_documents, read_notepad_tool, write_notepad_tool, remember, recall]


def _question_language(question: str) -> str:
    """Soru dilini kabaca tespit eder: 'tr' veya 'en'."""
    turkish_chars = set("ğüşıöçĞÜŞİÖÇ")
    text = question.strip()
    if not text:
        return "tr"
    if any(c in turkish_chars for c in text):
        return "tr"
    turkish_words = ("ve", "bir", "için", "bu", "ne", "nasıl", "var", "mı", "mi", "mu", "mü", "da", "de", "ta", "te")
    if set(text.lower().split()[:5]) & set(turkish_words):
        return "tr"
    return "en"


def build_agent(index):
    """LangChain Agent + Tool döngüsü (AgentExecutor) oluşturur."""
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_openai import ChatOpenAI

    tools = make_tools(index)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    system = (
        "Sen belgeler, notepad ve uzun süreli belleği kullanan yardımcı bir agentsın. "
        "Kurallar: "
        "(1) Belgelerle ilgili sorularda search_documents ile ara, bulduğun metne göre cevapla. "
        "(2) Notepad için write_notepad_tool / read_notepad_tool kullan. "
        "(3) UZUN BELLEK - ZORUNLU: Kullanıcı isim, tercih, nerede yaşadığı vb. bir bilgi verdiğinde (örn. 'Adım Ali', 'Orlando\'da yaşıyorum', 'Bunu kaydet') MUTLAKA remember(key, value) araçını ÇAĞIR. Örnek: yaşadığı şehir için remember('şehir', 'Orlando'). 'Kaydettim' demeden önce mutlaka remember kullan. "
        "Kullanıcı kaydettiğin bir şeyi sorduğunda (adım ne?, nerede yaşıyorum?, hangi şehirde?, what did I tell you?) ÖNCE recall() veya ilgili anahtarla recall(key) çağır: isim için recall('isim'), şehir için recall('şehir'). Dönen değere göre cevapla. Recall çağırmadan asla 'hatırlamıyorum' deme. "
        "(4) Cevabı SADECE sorunun dilinde ver. "
        "(5) Basit selamlaşmada araç kullanma."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=5,
        handle_parsing_errors=True,
    )
    return executor


def run_agent(executor, user_input: str, chat_history: list) -> str:
    """Kısa belleği (son N tur) mesaj listesine çevirir ve agent'ı çalıştırır."""
    from langchain_core.messages import HumanMessage, AIMessage

    # Terminalde akış: 1. adım (renkli – soru bölümü kolay bulunsun)
    _cyan = "\033[1;36m"
    _reset = "\033[0m"
    print("\n" + _cyan + "=" * 60, flush=True)
    print("[AKIŞ] Adım 1: KULLANICI SORUSU ALINDI", flush=True)
    print("[AKIŞ] Soru: {}".format(user_input[:200] + "…" if len(user_input) > 200 else user_input), flush=True)
    print("=" * 60 + _reset, flush=True)

    # Son N turu LangChain mesaj formatına çevir
    messages = []
    for user_msg, assistant_msg in chat_history[-SHORT_MEMORY_TURNS:]:
        if user_msg:
            messages.append(HumanMessage(content=user_msg))
        if assistant_msg:
            messages.append(AIMessage(content=assistant_msg))

    # Akış callback'i: araç çağrıları ve agent bitişi terminalde görünsün
    callbacks = []
    if BaseCallbackHandler is not None:
        callbacks = [AkisCallbackHandler()]

    result = executor.invoke(
        {
            "input": user_input,
            "chat_history": messages,
        },
        config={"callbacks": callbacks} if callbacks else {},
    )

    out = result.get("output", "Yanıt alınamadı.")
    print("[AKIŞ] Son adım: Cevap kullanıcıya döndü ({} karakter).".format(len(out)))
    print("=" * 60 + "\n")
    return out


def create_gradio_app():
    """Gradio: Sohbet geçmişi (kısa bellek) + Notepad paneli + Agent."""
    import gradio as gr

    from memory_utils import read_notepad, write_notepad

    index = build_or_load_index()
    executor = build_agent(index) if index else None

    def _history_to_text(history):
        """Sohbet geçmişini tek metin olarak formatlar (Chatbot yerine Textbox için)."""
        if not history:
            return "(Henüz mesaj yok.)"
        lines = []
        for user_msg, asst_msg in history:
            if user_msg:
                lines.append("**Siz:** " + user_msg)
            if asst_msg:
                lines.append("**Agent:** " + asst_msg)
        return "\n\n".join(lines)

    def chat_turn(message, history):
        if not message or not message.strip():
            return history, _history_to_text(history)
        if executor is None:
            history = history + [[message, "Belge indeksi yok. bilgiler/ klasörüne dosya ekleyip uygulamayı yeniden başlatın."]]
            return history, _history_to_text(history)
        reply = run_agent(executor, message.strip(), history)
        history = history + [[message, reply]]
        return history, _history_to_text(history)

    def refresh_notepad():
        return read_notepad()

    def save_notepad_content(content):
        write_notepad(content or "", "overwrite")
        return "Notepad kaydedildi."

    with gr.Blocks(title="RAG Agent – Notepad & Bellek", theme=gr.themes.Soft()) as app:
        gr.Markdown("# RAG Agent – Notepad, Bellek ve Araçlar")
        gr.Markdown("Belgelerde arama, notepad okuma/yazma, uzun süreli bellek (remember/recall). Soru dilinde cevap verilir.")

        history_state = gr.State([])  # [[user, assistant], ...]

        with gr.Row():
            with gr.Column(scale=2):
                chat_display = gr.Textbox(
                    label="Sohbet (kısa bellek: son {} tur)".format(SHORT_MEMORY_TURNS),
                    lines=16,
                    max_lines=20,
                    interactive=False,
                    value="(Henüz mesaj yok.)",
                )
                msg = gr.Textbox(placeholder="Sorunuzu veya notunuzu yazın...", label="Mesaj", lines=2)
                gr.Button("Gönder").click(
                    fn=chat_turn,
                    inputs=[msg, history_state],
                    outputs=[history_state, chat_display],
                ).then(lambda: "", outputs=[msg])
                msg.submit(
                    fn=chat_turn,
                    inputs=[msg, history_state],
                    outputs=[history_state, chat_display],
                ).then(lambda: "", outputs=[msg])

            with gr.Column(scale=1):
                gr.Markdown("### Notepad")
                notepad_display = gr.Textbox(
                    label="İçerik (agent da okuyup yazabilir)",
                    lines=12,
                    value=read_notepad(),
                )
                with gr.Row():
                    gr.Button("Yenile").click(fn=refresh_notepad, outputs=[notepad_display])
                    gr.Button("Kaydet").click(fn=save_notepad_content, inputs=[notepad_display], outputs=[]).then(
                        fn=refresh_notepad, outputs=[notepad_display]
                    )

        gr.Markdown("---")
        gr.Markdown("**Araçlar:** `search_documents` (belgelerde arama), `read_notepad_tool` / `write_notepad_tool`, `remember` / `recall` (uzun bellek). Agent gerektikçe bunları kullanır.")

    return app


if __name__ == "__main__":
    app = create_gradio_app()
    # share=False: localhost erişim hatasını önler; 127.0.0.1 ile sadece yerel erişim
    app.launch(server_name="127.0.0.1", server_port=7860, share=False)
