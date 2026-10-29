"""ChromaDB-backed vector store with Ollama embeddings and a lexical re-rank.

Pure vector search on an 8B-scale local embedding model is weak at exact-token
queries ("AR-02.4", "HSL4110", "CSL7620"). We over-fetch candidates and re-rank
with a small lexical bonus, which costs nothing and markedly improves citation
accuracy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import chromadb
from chromadb.config import Settings

from academic_helpdesk import config
from academic_helpdesk.rag.chunking import chunk_corpus

TOKEN_RE = re.compile(r"[A-Za-z]{2,}\d{2,}(?:\.\d+)?|[A-Za-z]{3,}")


@dataclass
class Retrieved:
    text: str
    distance: float
    score: float
    metadata: dict


@lru_cache(maxsize=1)
def _client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=str(config.VECTOR_STORE_DIR),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )


@lru_cache(maxsize=1)
def _ollama_client():
    import ollama

    return ollama.Client(host=config.OLLAMA_HOST)


@lru_cache(maxsize=1)
def _local_embedder():
    """ChromaDB's bundled all-MiniLM-L6-v2 ONNX model -- no server required."""
    from chromadb.utils import embedding_functions

    return embedding_functions.DefaultEmbeddingFunction()


def embed(texts: list[str]) -> list[list[float]]:
    """Embed with the configured backend. See config.EMBEDDING_BACKEND."""
    if config.EMBEDDING_BACKEND == "local":
        # The ONNX embedder returns numpy float32; Chroma wants plain floats.
        return [[float(x) for x in vector] for vector in _local_embedder()(texts)]

    if config.EMBEDDING_BACKEND != "ollama":
        raise ValueError(
            f"Unknown EMBEDDING_BACKEND '{config.EMBEDDING_BACKEND}'. "
            "Use 'ollama' or 'local'."
        )

    response = _ollama_client().embed(model=config.EMBEDDING_MODEL, input=texts)
    return list(response["embeddings"])


def embedding_label() -> str:
    if config.EMBEDDING_BACKEND == "local":
        return "local ONNX all-MiniLM-L6-v2 (no server)"
    return f"{config.EMBEDDING_MODEL} via Ollama at {config.OLLAMA_HOST}"


@lru_cache(maxsize=1)
def _numpy_collection():
    from academic_helpdesk.rag.numpy_store import NumpyCollection

    return NumpyCollection(config.VECTOR_STORE_DIR / "numpy", config.COLLECTION_NAME)


def get_collection():
    if config.VECTOR_BACKEND == "numpy":
        return _numpy_collection()
    return _client().get_or_create_collection(
        name=config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def drop_collection() -> None:
    """Delete the current collection if it exists."""
    if config.VECTOR_BACKEND == "numpy":
        _numpy_collection().delete()
        return
    try:
        _client().delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass


@lru_cache(maxsize=1)
def known_categories() -> tuple[str, ...]:
    """Categories actually present in the loaded collection."""
    try:
        metas = get_collection().get(include=["metadatas"])["metadatas"]
    except Exception:
        return ()
    return tuple(sorted({m.get("category", "") for m in metas if m.get("category")}))


def build_index(*, rebuild: bool = False, batch_size: int = 32, verbose: bool = True) -> int:
    """(Re)build the vector store from the markdown corpus. Returns the chunk count."""
    if rebuild:
        drop_collection()

    collection = get_collection()
    chunks = chunk_corpus()

    if collection.count() == len(chunks) and not rebuild:
        if verbose:
            print(f"Index already holds {collection.count()} chunks; nothing to do.")
        return collection.count()

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        collection.upsert(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            metadatas=[c.metadata for c in batch],
            embeddings=embed([c.text for c in batch]),
        )
        if verbose:
            print(f"  embedded {min(start + batch_size, len(chunks))}/{len(chunks)} chunks")

    return collection.count()


def _lexical_bonus(query: str, text: str, metadata: dict) -> float:
    """Reward exact overlap on identifier-like tokens (clause numbers, course codes)."""
    q_tokens = {t.lower() for t in TOKEN_RE.findall(query)}
    if not q_tokens:
        return 0.0

    haystack = f"{text} {metadata.get('doc_id', '')} {metadata.get('title', '')}".lower()
    identifiers = {t for t in q_tokens if any(ch.isdigit() for ch in t)}
    words = q_tokens - identifiers

    bonus = 0.0
    bonus += 0.12 * sum(1 for t in identifiers if t in haystack)
    if words:
        bonus += 0.10 * (sum(1 for t in words if t in haystack) / len(words))
    return min(bonus, 0.45)


def search(
    query: str,
    top_k: int | None = None,
    category: str | None = None,
) -> list[Retrieved]:
    top_k = top_k or config.TOP_K
    collection = get_collection()
    if collection.count() == 0:
        raise RuntimeError(
            "Vector store is empty. Run: python -m academic_helpdesk.rag.ingest"
        )

    result = collection.query(
        query_embeddings=embed([query]),
        n_results=min(config.CANDIDATE_K, collection.count()),
        where={"category": category} if category else None,
        include=["documents", "metadatas", "distances"],
    )

    candidates: list[Retrieved] = []
    for text, metadata, distance in zip(
        result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        similarity = 1.0 - float(distance)
        candidates.append(
            Retrieved(
                text=text,
                distance=float(distance),
                score=similarity + _lexical_bonus(query, text, metadata),
                metadata=dict(metadata),
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_k]
