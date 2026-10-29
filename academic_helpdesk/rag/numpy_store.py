"""Exact cosine-similarity store with the slice of the Chroma Collection API we use.

Selected with VECTOR_BACKEND=numpy. It exists because ChromaDB's native HNSW code
access-violates on some Windows machines (seen with chromadb 0.6.3, 1.0.21 and
1.5.9 on this project's dev laptop). For a corpus of a few hundred chunks an exact
brute-force search is instantaneous and has no native dependency beyond numpy.

Persisted as <dir>/<name>.npz (vectors) + <dir>/<name>.json (ids, text, metadata).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class NumpyCollection:
    def __init__(self, directory: Path, name: str):
        self.directory = Path(directory)
        self.name = name
        self.ids: list[str] = []
        self.documents: list[str] = []
        self.metadatas: list[dict] = []
        self.vectors = np.zeros((0, 0), dtype=np.float32)
        self._load()

    # -- persistence ---------------------------------------------------------
    @property
    def _vec_path(self) -> Path:
        return self.directory / f"{self.name}.npz"

    @property
    def _meta_path(self) -> Path:
        return self.directory / f"{self.name}.json"

    def _load(self) -> None:
        if not (self._vec_path.exists() and self._meta_path.exists()):
            return
        self.vectors = np.load(self._vec_path)["vectors"].astype(np.float32)
        data = json.loads(self._meta_path.read_text(encoding="utf-8"))
        self.ids, self.documents, self.metadatas = data["ids"], data["documents"], data["metadatas"]

    def _save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self._vec_path, vectors=self.vectors)
        self._meta_path.write_text(
            json.dumps(
                {"ids": self.ids, "documents": self.documents, "metadatas": self.metadatas},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def delete(self) -> None:
        for path in (self._vec_path, self._meta_path):
            path.unlink(missing_ok=True)
        self.ids, self.documents, self.metadatas = [], [], []
        self.vectors = np.zeros((0, 0), dtype=np.float32)

    # -- Chroma-shaped API -----------------------------------------------------
    def count(self) -> int:
        return len(self.ids)

    def upsert(self, ids, documents, metadatas, embeddings) -> None:
        new = np.asarray(embeddings, dtype=np.float32)
        if self.vectors.size == 0:
            self.vectors = np.zeros((0, new.shape[1]), dtype=np.float32)
        index = {chunk_id: i for i, chunk_id in enumerate(self.ids)}
        for chunk_id, doc, meta, vec in zip(ids, documents, metadatas, new):
            if chunk_id in index:
                i = index[chunk_id]
                self.documents[i], self.metadatas[i], self.vectors[i] = doc, dict(meta), vec
            else:
                index[chunk_id] = len(self.ids)
                self.ids.append(chunk_id)
                self.documents.append(doc)
                self.metadatas.append(dict(meta))
                self.vectors = np.vstack([self.vectors, vec])
        self._save()

    def get(self, ids=None, include=None) -> dict:
        rows = range(len(self.ids))
        if ids is not None:
            wanted = set(ids)
            rows = [i for i in rows if self.ids[i] in wanted]
        out = {
            "ids": [self.ids[i] for i in rows],
            "metadatas": [self.metadatas[i] for i in rows],
            "documents": [self.documents[i] for i in rows],
        }
        if include and "embeddings" in include:
            out["embeddings"] = [self.vectors[i].tolist() for i in rows]
        return out

    def query(self, query_embeddings, n_results, where=None, include=None) -> dict:
        if not self.ids:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}
        q = np.asarray(query_embeddings[0], dtype=np.float32)
        norms = np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(q)
        distances = 1.0 - (self.vectors @ q) / np.maximum(norms, 1e-12)  # cosine distance, as Chroma reports it

        allowed = np.ones(len(self.ids), dtype=bool)
        if where:
            for key, value in where.items():
                allowed &= np.array([m.get(key) == value for m in self.metadatas])
        order = [i for i in np.argsort(distances) if allowed[i]][:n_results]
        return {
            "ids": [[self.ids[i] for i in order]],
            "documents": [[self.documents[i] for i in order]],
            "metadatas": [[self.metadatas[i] for i in order]],
            "distances": [[float(distances[i]) for i in order]],
        }
