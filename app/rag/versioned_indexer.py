"""
Versioned index builder for the RAG pipeline.

Each ingestion run creates an immutable, numbered snapshot:
  storage/v{N}/          — LlamaIndex docstore  (JSON node files)
  storage/chroma_v{N}/   — Chroma vector store   (embeddings)

The active version is tracked in  storage/active_version.txt.
Activating a new version is a single file write — effectively atomic on POSIX.

Workers detect a version change lazily: every call to _get_pipeline() reads the
pointer file and rebuilds only when the number has changed.  In-flight queries
are unaffected because each worker holds its index in memory.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

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
    INDEX_DIR,
    DATA_DIR,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_MODEL,
    EMBEDDING_TIMEOUT,
    REQUIRED_EXTS,
)

logger = logging.getLogger(__name__)

# All versioned artifacts live inside the existing Docker volume at INDEX_DIR (/app/storage)
_STORAGE_BASE = INDEX_DIR
_ACTIVE_PTR = _STORAGE_BASE / "active_version.txt"


# ── Manifest ──────────────────────────────────────────────────────────────────

def get_doc_manifest(data_dir: Path = None) -> dict:
    """
    Return {filename: {size_bytes, mtime, sha256_prefix}} for every supported doc.

    The sha256 covers only the first 8 KB — fast fingerprint without reading
    entire PDFs.  Used to detect whether anything changed since last build.
    """
    if data_dir is None:
        data_dir = DATA_DIR.resolve()
    exts = {e.lower() for e in REQUIRED_EXTS}
    manifest = {}
    for p in sorted(data_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            stat = p.stat()
            with open(p, "rb") as f:
                head = f.read(8192)
            manifest[p.name] = {
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256_prefix": hashlib.sha256(head).hexdigest()[:16],
            }
    return manifest


# ── Active version pointer ────────────────────────────────────────────────────

def get_active_version() -> Optional[int]:
    """Return the active index version number, or None if nothing has been built yet."""
    if _ACTIVE_PTR.exists():
        try:
            return int(_ACTIVE_PTR.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def _write_active_version(version_n: int) -> None:
    _STORAGE_BASE.mkdir(parents=True, exist_ok=True)
    _ACTIVE_PTR.write_text(str(version_n))


# ── Directory layout ──────────────────────────────────────────────────────────

def _docstore_dir(version_n: int) -> Path:
    return _STORAGE_BASE / f"v{version_n}"


def _chroma_dir(version_n: int) -> Path:
    return _STORAGE_BASE / f"chroma_v{version_n}"


# ── Build ─────────────────────────────────────────────────────────────────────

def build_versioned_index(version_n: int, data_dir: Path = None) -> tuple:
    """
    Build a new index into versioned staging dirs.  Does NOT activate it.

    Returns (doc_count: int, manifest: dict).
    Raises on failure so the caller can mark the DB record as FAILED.
    """
    if data_dir is None:
        data_dir = DATA_DIR.resolve()

    docstore = _docstore_dir(version_n)
    chroma = _chroma_dir(version_n)
    docstore.mkdir(parents=True, exist_ok=True)
    chroma.mkdir(parents=True, exist_ok=True)

    Settings.embed_model = OpenAIEmbedding(model=EMBEDDING_MODEL, timeout=EMBEDDING_TIMEOUT)
    Settings.chunk_size = CHUNK_SIZE
    Settings.chunk_overlap = CHUNK_OVERLAP

    exts = {e.lower() for e in REQUIRED_EXTS}
    input_files = sorted(
        str(p.resolve()) for p in data_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in exts
    )
    if not input_files:
        raise ValueError(f"No documents found in {data_dir}")

    manifest = get_doc_manifest(data_dir)
    logger.info("[v%d] Building index: %d files...", version_n, len(input_files))

    documents = SimpleDirectoryReader(input_files=input_files).load_data()

    client = chromadb.PersistentClient(path=str(chroma))
    collection = client.get_or_create_collection("llama_index")
    vector_store = ChromaVectorStore(chroma_collection=collection)

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    VectorStoreIndex.from_documents(
        documents,
        transformations=[SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)],
        storage_context=storage_context,
    )
    storage_context.persist(persist_dir=str(docstore))

    logger.info("[v%d] Index built: %d documents.", version_n, len(documents))
    return len(documents), manifest


# ── Activate ──────────────────────────────────────────────────────────────────

def activate_version(version_n: int) -> None:
    """
    Point active_version.txt at version_n.

    This is the atomic "swap" — a single small file write.  Any worker that
    checks get_active_version() after this call will load the new index on
    its next pipeline access.
    """
    _write_active_version(version_n)
    logger.info("Active index pointer → v%d", version_n)


# ── Load ──────────────────────────────────────────────────────────────────────

def load_versioned_index(version_n: int):
    """Load and return the VectorStoreIndex for a specific version number."""
    docstore = _docstore_dir(version_n)
    chroma = _chroma_dir(version_n)

    Settings.embed_model = OpenAIEmbedding(model=EMBEDDING_MODEL, timeout=EMBEDDING_TIMEOUT)
    Settings.chunk_size = CHUNK_SIZE
    Settings.chunk_overlap = CHUNK_OVERLAP

    client = chromadb.PersistentClient(path=str(chroma))
    collection = client.get_or_create_collection("llama_index")
    vector_store = ChromaVectorStore(chroma_collection=collection)

    ctx = StorageContext.from_defaults(
        vector_store=vector_store,
        persist_dir=str(docstore),
    )
    return load_index_from_storage(ctx)


def load_active_index():
    """
    Load the currently active versioned index.
    Falls back to the legacy monolithic storage/ index if no versioned index exists yet.
    """
    active = get_active_version()
    if active is not None:
        try:
            index = load_versioned_index(active)
            logger.info("Loaded versioned index v%d.", active)
            return index
        except Exception as e:
            logger.warning("Could not load versioned index v%d: %s — falling back.", active, e)

    from app.rag.indexer import build_or_load_index
    return build_or_load_index()
