"""Document indexer -- builds and loads the vector index."""

import logging

from app.config import DATA_DIR, INDEX_DIR, CHUNK_SIZE, CHUNK_OVERLAP, EMBEDDING_MODEL, EMBEDDING_TIMEOUT, REQUIRED_EXTS

logger = logging.getLogger(__name__)


def build_or_load_index():
    """Build a new index from bilgiler/ or load from storage/."""
    from llama_index.core import (
        SimpleDirectoryReader, StorageContext, VectorStoreIndex,
        load_index_from_storage, Settings,
    )
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.core.node_parser import SentenceSplitter

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    Settings.embed_model = OpenAIEmbedding(model=EMBEDDING_MODEL, timeout=EMBEDDING_TIMEOUT)
    Settings.chunk_size = CHUNK_SIZE
    Settings.chunk_overlap = CHUNK_OVERLAP

    if INDEX_DIR.exists():
        try:
            ctx = StorageContext.from_defaults(persist_dir=str(INDEX_DIR))
            index = load_index_from_storage(ctx)
            logger.info("Index loaded from storage/ (%d-token chunks).", CHUNK_SIZE)
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
        logger.warning("No documents found in data/bilgiler/.")
        return None

    logger.info("Building index: %d documents (chunk_size=%d)...", len(documents), CHUNK_SIZE)
    node_parser = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    index = VectorStoreIndex.from_documents(documents, transformations=[node_parser])
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    logger.info("Index ready.")
    return index
