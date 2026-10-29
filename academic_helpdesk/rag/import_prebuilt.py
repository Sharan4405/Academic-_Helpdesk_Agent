"""Load the pre-embedded corpus in data1/chroma into this project's vector store.

    python -m academic_helpdesk.rag.import_prebuilt

data1/chroma was built elsewhere and its HNSW index file is incomplete (it holds
100 of the 390 vectors), so ChromaDB crashes when it tries to open the folder.
The SQLite file next to it still holds every vector in its write-ahead queue,
along with each chunk's text and metadata. We read those directly, read-only, and
upsert them into a fresh collection -- the embeddings are used exactly as stored,
nothing is re-embedded.

Queries must then be embedded with the model that produced these vectors. The
dimension (384) and the check below identify it as ChromaDB's bundled
all-MiniLM-L6-v2, i.e. EMBEDDING_BACKEND=local.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys

import numpy as np

from academic_helpdesk import config
from academic_helpdesk.rag import store

QUEUE_SQL = """
    SELECT id, vector, metadata FROM embeddings_queue
    WHERE operation = 2 AND vector IS NOT NULL ORDER BY seq_id
"""


def _manifest() -> dict[str, dict]:
    path = config.PREBUILT_DIR.parent / "manifest_source.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {row["doc_id"]: row for row in csv.DictReader(fh)}


def read_prebuilt() -> tuple[list[str], np.ndarray, list[str], list[dict]]:
    db = config.PREBUILT_DIR / "chroma.sqlite3"
    if not db.exists():
        raise FileNotFoundError(f"No prebuilt index at {db}")

    # mode=ro: never modify the user's folder.
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    manifest = _manifest()
    ids, vectors, documents, metadatas = [], [], [], []
    for chunk_id, blob, meta_json in conn.execute(QUEUE_SQL):
        meta = json.loads(meta_json)
        text = meta.pop("chroma:document", "")
        info = manifest.get(meta.get("doc_id", ""), {})
        # The stored titles are file slugs; the manifest has the real ones.
        if info.get("title"):
            meta["title"] = info["title"]
        if info.get("source_url") and not meta.get("source_url"):
            meta["source_url"] = info["source_url"]
        ids.append(chunk_id)
        vectors.append(np.frombuffer(blob, dtype=np.float32))
        documents.append(text)
        metadatas.append(meta)
    conn.close()
    return ids, np.vstack(vectors), documents, metadatas


def verify_embedder(vectors: np.ndarray, documents: list[str]) -> float:
    """Mean cosine between stored vectors and our query embedder on the same text."""
    sample = list(range(0, len(documents), max(1, len(documents) // 12)))[:12]
    fresh = np.array(store.embed([documents[i] for i in sample]), dtype=np.float32)
    stored = vectors[sample]
    cos = (fresh * stored).sum(1) / (np.linalg.norm(fresh, axis=1) * np.linalg.norm(stored, axis=1))
    return float(cos.mean())


def import_prebuilt(*, verbose: bool = True) -> int:
    if config.EMBEDDING_BACKEND != "local":
        raise RuntimeError(
            "The prebuilt vectors are 384-dim MiniLM; set EMBEDDING_BACKEND=local."
        )
    ids, vectors, documents, metadatas = read_prebuilt()
    if vectors.shape[1] != 384:
        raise RuntimeError(f"Unexpected vector dimension {vectors.shape[1]}")

    agreement = verify_embedder(vectors, documents)
    if verbose:
        print(f"Read {len(ids)} chunks x {vectors.shape[1]} dims from {config.PREBUILT_DIR}")
        print(f"Query-embedder agreement with stored vectors (mean cosine): {agreement:.4f}")
    if agreement < 0.98:
        raise RuntimeError(
            f"Query embedder does not match the stored vectors (cosine {agreement:.3f}); "
            "retrieval would be meaningless."
        )

    store.drop_collection()
    collection = store.get_collection()
    for start in range(0, len(ids), 100):
        end = start + 100
        collection.upsert(
            ids=ids[start:end],
            embeddings=[v.tolist() for v in vectors[start:end]],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
    store.known_categories.cache_clear()
    return collection.count()


def main() -> int:
    try:
        count = import_prebuilt()
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    print(f"Done. Collection '{config.COLLECTION_NAME}' in {config.VECTOR_STORE_DIR} holds {count} chunks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
