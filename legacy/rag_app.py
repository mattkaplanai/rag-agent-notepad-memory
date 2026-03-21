"""
RAG Uygulaması: LlamaIndex + LangChain + OpenAI + Gradio
- bilgiler/ klasöründeki PDF, Word ve metin dosyaları indekslenir.
- Soru gelince ilgili metin bulunur, OpenAI ile cevap üretilir.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# OpenAI API anahtarı (zorunlu)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "OPENAI_API_KEY bulunamadı. Lütfen .env dosyasına ekleyin veya ortam değişkeni tanımlayın."
    )

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Proje kökü ve bilgiler klasörü
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BILGILER_DIR = PROJECT_ROOT / "data" / "bilgiler"
INDEX_DIR = PROJECT_ROOT / "storage"


def _ensure_bilgiler_dir():
    """bilgiler klasörü yoksa oluşturur."""
    BILGILER_DIR.mkdir(parents=True, exist_ok=True)


def build_or_load_index():
    """
    LlamaIndex ile 'bilgiler' klasörünü tarar, vektör indeksi oluşturur veya
    daha önce kaydedilmiş indeksi yükler.
    """
    from llama_index.core import (
        SimpleDirectoryReader,
        VectorStoreIndex,
        StorageContext,
        load_index_from_storage,
        Settings,
    )
    from llama_index.embeddings.openai import OpenAIEmbedding

    _ensure_bilgiler_dir()

    # Global ayar: sorgu embedding'i için (yükleme ve oluşturma aynı modeli kullanır)
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")

    # Desteklenen uzantılar: PDF, Word, metin
    required_exts = [".pdf", ".docx", ".doc", ".txt", ".md"]

    # Her seferinde bilgiler/ klasöründen yeniden indeksle (güncel dosyalar dahil)
    import shutil
    if INDEX_DIR.exists():
        try:
            shutil.rmtree(INDEX_DIR)
        except Exception:
            pass

    reader = SimpleDirectoryReader(
        input_dir=str(BILGILER_DIR),
        required_exts=required_exts,
        recursive=True,
    )
    documents = reader.load_data()

    if not documents:
        print("[RAG] Uyarı: bilgiler/ klasöründe uygun dosya bulunamadı.")
        return None

    print(f"[RAG] İndeks oluşturuluyor: {len(documents)} belge yüklendi...")
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[RAG] İndeks hazır. Uygulama başlatıldı.")
    return index


def _is_greeting_or_small_talk(question: str) -> bool:
    """Selamlama veya belge dışı kısa sohbet mi kontrol eder."""
    q = question.strip().lower()
    greetings = ("merhaba", "selam", "hey", "hi", "hello", "günaydın", "iyi günler", "naber", "ne haber")
    return not q or q in greetings or q.startswith(greetings)


def _question_language(question: str) -> str:
    """Soru Türkçe mi İngilizce mi kabaca tespit eder. 'tr' veya 'en' döner."""
    turkish_chars = set("ğüşıöçĞÜŞİÖÇ")
    text = question.strip()
    if not text:
        return "tr"
    # Türkçe karakter varsa veya yaygın Türkçe kelimeler varsa Türkçe say
    if any(c in turkish_chars for c in text):
        return "tr"
    turkish_words = ("ve", "bir", "için", "bu", "ne", "nasıl", "var", "mı", "mi", "mu", "mü", "da", "de", "ta", "te")
    first_words = set(text.lower().split()[:5])  # ilk birkaç kelime
    if first_words & set(turkish_words):
        return "tr"
    return "en"


def get_answer(question: str, index) -> str:
    """
    LangChain ve OpenAI ile: soru + LlamaIndex'ten gelen bağlam → cevap.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    if index is None:
        return (
            "Henüz indeks oluşturulmadı. Lütfen 'bilgiler' klasörüne en az bir "
            "PDF, Word veya metin dosyası ekleyin ve uygulamayı yeniden başlatın."
        )

    # Selamlama / belge dışı soru: kısa karşılık ver, belge sorusu iste
    if _is_greeting_or_small_talk(question):
        return (
            "Merhaba. Belgelerdeki konular hakkında sorularınızı yazabilirsiniz. "
            "Örneğin: iade koşulları, uçuş iptali, bagaj ücreti iadesi, DOT kuralları."
        )

    # LlamaIndex: ilgili parçaları getir (daha fazla parça; İngilizce/Türkçe sorular için)
    retriever = index.as_retriever(similarity_top_k=10)
    nodes = retriever.retrieve(question)
    context = "\n\n".join(node.get_content() for node in nodes)

    if not context.strip():
        return "Belgelerde bu soruyla eşleşen ilgili bilgi bulunamadı."

    lang = _question_language(question)
    if lang == "tr":
        lang_rule = "Cevabı MUTLAKA ve SADECE Türkçe yaz. Hiç İngilizce kelime veya cümle kullanma."
    else:
        lang_rule = "Answer ONLY in English. Do not use any Turkish words or sentences."

    # LangChain: soru + bağlam → OpenAI → cevap (dil kuralına göre)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Sen belgelerden gelen bağlamı kullanarak soru cevaplayan bir asistansın. "
         + lang_rule + " "
         "Bağlamda iade, uçuş iptali, bilet, bagaj, DOT, airline, refund, cancellation, ticket gibi konular varsa MUTLAKA bu bilgiyle cevap ver. "
         "Bağlam konuyla ilgisizse Türkçe soruda 'Belgelerde bu bilgi yok.', İngilizce soruda 'This information is not in the documents.' de. Kısa ve net yanıt ver; gerekirse madde madde yaz."),
        ("human", "Bağlam:\n{context}\n\nSoru: {question}\n\nCevap:"),
    ])
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    chain = prompt | llm | StrOutputParser()
    answer_text = chain.invoke({"context": context, "question": question})

    # Kullanılan bağlamın kısa önizlemesi (ne geldiğini görmek için)
    preview_len = 350
    preview = context.strip()[:preview_len] + ("..." if len(context.strip()) > preview_len else "")
    return answer_text + "\n\n---\n📎 Kullanılan bağlam (önizleme): " + preview


def create_gradio_app():
    """Gradio arayüzü: soru kutusu + cevap alanı (ChatBox)."""
    import gradio as gr

    index = build_or_load_index()

    def answer(question: str):
        if not (question or question.strip()):
            return "Lütfen bir soru yazın."
        return get_answer(question.strip(), index)

    with gr.Blocks(title="RAG Sohbet", theme=gr.themes.Soft()) as app:
        gr.Markdown("# Doküman tabanlı soru-cevap")
        gr.Markdown("**bilgiler** klasöründeki PDF, Word ve metin dosyalarına göre sorularınızı yanıtlar.")
        with gr.Row():
            question_box = gr.Textbox(
                label="Sorunuz",
                placeholder="Örn: Bu belgede X nasıl tanımlanıyor?",
                lines=2,
                scale=3,
            )
            submit_btn = gr.Button("Gönder", variant="primary", scale=1)
        answer_box = gr.Textbox(
            label="Cevap",
            lines=8,
            interactive=False,
        )
        submit_btn.click(fn=answer, inputs=question_box, outputs=answer_box)
        question_box.submit(fn=answer, inputs=question_box, outputs=answer_box)

    return app


if __name__ == "__main__":
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=7860)
