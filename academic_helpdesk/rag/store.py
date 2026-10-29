"""ChromaDB-backed vector store with Ollama embeddings and a lexical re-rank.

Pure vector search on an 8B-scale local embedding model is weak at exact-token
queries ("AR-02.4", "HSL4110", "CSL7620"). We over-fetch candidates and re-rank
with a small lexical bonus, which costs nothing and markedly improves citation
accuracy.
"""

from __future__ import annotations

import math
import re
from collections import Counter
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
    coverage: float = 0.0  # share of the query's distinctive words found in the passage
    query_words: int = 0  # how many distinctive words the query had


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


STOPWORDS = frozenset(
    "the and for are was were what when where which who whom how why can could should would "
    "does did has have had not you your our their from with into that this these those there "
    "than then also any all one two about over under been being its his her they them will "
    "shall may must per via get got make made take need needs want like give tell please "
    "much many more most some such very just only each other another".split()
)
WORD_RE = re.compile(r"[a-z0-9][a-z0-9.\-]*[a-z0-9]|[a-z0-9]")


def _words(text: str) -> set[str]:
    return {w for w in WORD_RE.findall(text.lower()) if len(w) >= 3 and w not in STOPWORDS}


@lru_cache(maxsize=1)
def _idf() -> dict[str, float]:
    """Inverse document frequency of every word over the loaded chunks."""
    documents = get_collection().get(include=["documents"])["documents"]
    frequency: Counter[str] = Counter()
    for document in documents:
        frequency.update(_words(document))
    n = max(1, len(documents))
    return {word: math.log((n + 1) / (count + 0.5)) for word, count in frequency.items()}


def _stems(text: str) -> set[str]:
    return {w[:5] for w in _words(text) if len(w) >= 4}


@lru_cache(maxsize=1)
def _authority() -> tuple[tuple[str, frozenset[str], frozenset[str]], ...]:
    """(superseding doc, docs it supersedes, stems of the topics it overrides).

    Built from the chunk metadata (supersedes / superseded_topics), which comes from
    the dataset's own document-authority table.
    """
    seen: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for meta in get_collection().get(include=["metadatas"])["metadatas"]:
        if meta.get("supersedes") and meta.get("superseded_topics"):
            seen[meta["doc_id"]] = (
                frozenset(x.strip() for x in meta["supersedes"].split(";") if x.strip()),
                frozenset(_stems(meta["superseded_topics"].replace(";", " "))),
            )
    return tuple((doc, old, topics) for doc, (old, topics) in seen.items())


def authority_adjustment(query: str, doc_id: str) -> float:
    """Prefer the amendment over the regulation it overrides, on the topics it overrides.

    +0.12 for a superseding document when the question is about a topic it
    overrides; -0.06 for the superseded base document in that same case. Without
    this, the long base regulation outranks the short circular that changed it.
    """
    query_stems = _stems(query)
    adjustment = 0.0
    for superseding, superseded, topics in _authority():
        if not query_stems & topics:
            continue
        if doc_id == superseding:
            adjustment += 0.12
        elif doc_id in superseded:
            adjustment -= 0.06
    return adjustment


def keyword_coverage(query: str, text: str) -> float:
    """IDF-weighted share of the query's words that appear in `text`.

    Words the corpus has never seen weigh the most, so a question about "dining"
    cannot be fully covered by a passage that merely mentions "campus".
    """
    idf = _idf()
    unseen = math.log(len(idf) + 1) + 1.0  # weight for a word absent from the corpus
    present = _words(text)
    total = matched = 0.0
    for word in _words(query):
        weight = idf.get(word, unseen)
        total += weight
        if word in present:
            matched += weight
    return matched / total if total else 0.0


@lru_cache(maxsize=1)
def _all_chunks() -> tuple[list[str], list[str], list[dict]]:
    got = get_collection().get(include=["documents", "metadatas"])
    return got["ids"], got["documents"], got["metadatas"]


LEXICAL_EXTRA = 12  # chunks added to the pool purely on keyword coverage
LEXICAL_MIN_COVERAGE = 0.6


def _lexical_candidates(query: str, exclude: set[str], category: str | None) -> list[str]:
    """Ids of the chunks that contain most of the question's distinctive words.

    Vector search alone misses passages whose source text embeds badly -- scanned
    PDFs, mixed-language headers -- even when they use the question's own words.
    """
    ids, documents, metadatas = _all_chunks()
    scored = []
    for chunk_id, document, meta in zip(ids, documents, metadatas):
        if chunk_id in exclude or (category and meta.get("category") != category):
            continue
        coverage = keyword_coverage(query, f"{document} {meta.get('title', '')}")
        if coverage >= LEXICAL_MIN_COVERAGE:
            scored.append((coverage, chunk_id))
    scored.sort(reverse=True)
    return [chunk_id for _, chunk_id in scored[:LEXICAL_EXTRA]]


def is_sufficient(hits: list["Retrieved"]) -> bool:
    """Whether the retrieved evidence is strong enough to answer from.

    Normally the best cosine distance must be within MAX_RELEVANT_DISTANCE. A
    passage that contains every distinctive word of the question also qualifies,
    however far its embedding is, because scanned or noisy source text embeds poorly
    even when it plainly answers the question.
    """
    if not hits:
        return False
    if min(h.distance for h in hits) <= config.MAX_RELEVANT_DISTANCE:
        return True
    return any(h.coverage >= 0.95 and h.query_words >= 2 for h in hits)


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
    return min(bonus, 0.30)


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

    query_embedding = embed([query])
    result = collection.query(
        query_embeddings=query_embedding,
        n_results=min(config.CANDIDATE_K, collection.count()),
        where={"category": category} if category else None,
        include=["documents", "metadatas", "distances"],
    )

    pool = list(
        zip(result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0])
    )

    # Add chunks that share the question's distinctive words but embed badly.
    extra_ids = _lexical_candidates(query, {row[0] for row in pool}, category)
    if extra_ids:
        extra = collection.get(ids=extra_ids, include=["documents", "metadatas", "embeddings"])
        q = [float(x) for x in query_embedding[0]]
        q_norm = math.sqrt(sum(x * x for x in q)) or 1.0
        for chunk_id, text, metadata, vector in zip(
            extra["ids"], extra["documents"], extra["metadatas"], extra["embeddings"]
        ):
            v_norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            cosine = sum(a * b for a, b in zip(q, vector)) / (q_norm * v_norm)
            pool.append((chunk_id, text, metadata, 1.0 - cosine))

    candidates: list[Retrieved] = []
    for _chunk_id, text, metadata, distance in pool:
        similarity = 1.0 - float(distance)
        coverage = keyword_coverage(query, f"{text} {metadata.get('title', '')}")
        candidates.append(
            Retrieved(
                text=text,
                distance=float(distance),
                score=(
                    similarity
                    + _lexical_bonus(query, text, metadata)
                    + 0.2 * coverage
                    + (0.3 if coverage >= 0.95 and len(_words(query)) >= 2 else 0.0)
                    + authority_adjustment(query, metadata.get("doc_id", ""))
                ),
                metadata=dict(metadata),
                coverage=coverage,
                query_words=len(_words(query)),
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_k]
