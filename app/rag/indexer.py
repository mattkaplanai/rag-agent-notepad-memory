"""Document indexer -- builds and loads the vector index (Chroma as vector store)."""

import logging

import chromadb
from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
    Settings,
)
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.config import (
    CHROMA_PERSIST_DIR,
    DATA_DIR,
    INDEX_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT,
    REQUIRED_EXTS,
)

logger = logging.getLogger(__name__)

CHROMA_COLLECTION_NAME = "llama_index"


def _get_chroma_vector_store():
    """Create Chroma persistent client and return LlamaIndex ChromaVectorStore."""
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PERSIST_DIR))
    collection = client.get_or_create_collection(CHROMA_COLLECTION_NAME)
    return ChromaVectorStore(chroma_collection=collection)


def _ensure_sample_document(data_dir):
    """If data/bilgiler is empty, add a minimal .txt so index build can run."""
    data_dir.mkdir(parents=True, exist_ok=True)
    sample = data_dir / "ornek_metin.txt"
    if sample.exists():
        return
    for p in data_dir.iterdir():
        if p.suffix.lower() in (".pdf", ".docx", ".doc", ".txt", ".md"):
            return
    sample.write_text(
        "Örnek metin. data/bilgiler/ klasörüne PDF, DOCX veya TXT ekleyip uygulamayı yeniden başlatın.\n"
        "Sample text. Add PDF, DOCX or TXT files to data/bilgiler/ and restart the app.",
        encoding="utf-8",
    )
    logger.info("Created sample file: %s", sample.name)


def _collect_data_files(data_dir):
    """Collect paths of supported files in data_dir (avoids SimpleDirectoryReader scan issues)."""
    exts = tuple(e.lower() for e in REQUIRED_EXTS)
    files = []
    for p in data_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            files.append(str(p.resolve()))
    return sorted(files)


def build_or_load_index():
    """Build a new index from bilgiler/ or load from storage/ (Chroma + docstore)."""
    data_dir = DATA_DIR.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    Settings.embed_model = OpenAIEmbedding(
        model=EMBEDDING_MODEL, timeout=EMBEDDING_TIMEOUT
    )
    Settings.chunk_size = CHUNK_SIZE
    Settings.chunk_overlap = CHUNK_OVERLAP

    vector_store = _get_chroma_vector_store()

    # Try load: docstore from INDEX_DIR, vector store from Chroma
    if INDEX_DIR.exists():
        try:
            ctx = StorageContext.from_defaults(
                vector_store=vector_store,
                persist_dir=str(INDEX_DIR),
            )
            index = load_index_from_storage(ctx)
            logger.info(
                "Index loaded from storage/ (Chroma + docstore, %d-token chunks).",
                CHUNK_SIZE,
            )
            return index
        except Exception:
            pass

    _ensure_sample_document(data_dir)
    input_files = _collect_data_files(data_dir)
    if not input_files:
        logger.warning("No documents found in data/bilgiler/.")
        return None
    reader = SimpleDirectoryReader(input_files=input_files)
    documents = reader.load_data()
    if not documents:
        logger.warning("No documents found in data/bilgiler/.")
        return None

    logger.info(
        "Building index with Chroma: %d documents (chunk_size=%d)...",
        len(documents),
        CHUNK_SIZE,
    )
    node_parser = SentenceSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        documents,
        transformations=[node_parser],
        storage_context=storage_context,
    )
    storage_context.persist(persist_dir=str(INDEX_DIR))
    logger.info("Index ready (Chroma + docstore persisted).")
    return index
