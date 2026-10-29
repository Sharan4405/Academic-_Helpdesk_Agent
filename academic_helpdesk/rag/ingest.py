"""CLI entry point: build the vector store.

    python -m academic_helpdesk.rag.ingest            # incremental
    python -m academic_helpdesk.rag.ingest --rebuild  # drop and rebuild
"""

from __future__ import annotations

import argparse
import sys

from academic_helpdesk import config
from academic_helpdesk.rag.chunking import chunk_corpus
from academic_helpdesk.rag.store import build_index, embedding_label


def main() -> int:
    parser = argparse.ArgumentParser(description="Index the academic document corpus.")
    parser.add_argument("--rebuild", action="store_true", help="delete and rebuild")
    parser.add_argument("--dry-run", action="store_true", help="chunk only, no embedding")
    args = parser.parse_args()

    if config.CORPUS_SOURCE == "prebuilt":
        from academic_helpdesk.rag.import_prebuilt import main as import_main

        return import_main()

    documents = [p for d in config.CORPUS_DIRS for p in sorted(d.glob("*.md"))]
    if not documents:
        hint = (
            "\nRun: python -m academic_helpdesk.rag.extract" if config.CORPUS_SOURCE != "synthetic" else ""
        )
        print(f"No markdown documents found in {config.CORPUS_DIRS}.{hint}", file=sys.stderr)
        return 1

    chunks = chunk_corpus()
    print(f"Corpus: {len(documents)} documents -> {len(chunks)} chunks")

    if args.dry_run:
        for chunk in chunks[:5]:
            print(f"\n--- {chunk.chunk_id} ---\n{chunk.text[:260]}...")
        return 0

    print(f"Embedding with {embedding_label()} ...")
    try:
        count = build_index(rebuild=args.rebuild)
    except Exception as exc:
        print(f"\nIndexing failed: {exc}", file=sys.stderr)
        if config.EMBEDDING_BACKEND == "ollama":
            print(
                "Check that Ollama is running and the embedding model is pulled:\n"
                f"  ollama pull {config.EMBEDDING_MODEL}\n"
                "Or switch to the server-free backend: EMBEDDING_BACKEND=local",
                file=sys.stderr,
            )
        return 1

    print(
        f"Done. Collection '{config.COLLECTION_NAME}' in {config.VECTOR_STORE_DIR} "
        f"holds {count} chunks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
