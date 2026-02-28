"""Document indexer — builds and loads the vector index."""

from app.config import DATA_DIR, INDEX_DIR, CHUNK_SIZE, CHUNK_OVERLAP, REQUIRED_EXTS


def build_or_load_index():
    """Build a new index from bilgiler/ or load from storage/."""
    from llama_index.core import (
        SimpleDirectoryReader, StorageContext, VectorStoreIndex,
        load_index_from_storage, Settings,
    )
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.core.node_parser import SentenceSplitter

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    Settings.chunk_size = CHUNK_SIZE
    Settings.chunk_overlap = CHUNK_OVERLAP

    if INDEX_DIR.exists():
        try:
            ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
            index = load_index_from_storage(ctx)
            print(f"[RAG] Index loaded from storage/ ({CHUNK_SIZE}-token chunks)")
            return index
        except Exception:
            pass

    reader = SimpleDirectoryReader(
        input_dir=str(DATA_DIR),
        required_exts=REQUIRED_EXTS,
        recursive=True,
    )
    documents = reader.load_data()
    if not documents:
        print("[RAG] No documents found in data/bilgiler/")
        return None

    print(f"[RAG] Building index: {len(documents)} documents (chunk_size={CHUNK_SIZE})...")
    node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    index = VectorStoreIndex.from_documents(documents, transformations=[node_parser])
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("[RAG] Index ready.")
    return index
