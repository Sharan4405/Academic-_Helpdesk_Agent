"""Measure the retrieval layer alone, with no LLM in the loop.

Two things are measured over the 30-question evaluation set:

1. **Retrieval recall** -- for each question whose expected sources include a
   document (as opposed to a CSV), is that document in the top-k?
2. **Refusal separability** -- the best cosine distance for in-scope questions
   versus out-of-scope ones. If the two ranges overlap, no single
   `MAX_RELEVANT_DISTANCE` can separate them and topical scope has to be
   enforced by the orchestrator instruction instead.

Because no model is sampled, these numbers are deterministic and reproducible,
which makes them the right thing to quote in the report alongside the
model-dependent results.

    python eval/check_retrieval.py
    EMBEDDING_BACKEND=local python eval/check_retrieval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from academic_helpdesk import config  # noqa: E402
from academic_helpdesk.rag import store  # noqa: E402
from academic_helpdesk.tools.rag_tools import search_academic_documents  # noqa: E402

QUESTIONS_PATH = Path(__file__).parent / "questions.json"


def main() -> int:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]

    try:
        count = store.get_collection().count()
    except Exception as exc:
        print(f"Cannot open the vector store: {exc}")
        return 1
    if count == 0:
        print(
            f"Collection '{config.COLLECTION_NAME}' is empty.\n"
            "Run: python -m academic_helpdesk.rag.ingest"
        )
        return 1

    print(f"Embeddings : {store.embedding_label()}")
    print(f"Collection : {config.COLLECTION_NAME} ({count} chunks)")
    print(f"Threshold  : MAX_RELEVANT_DISTANCE = {config.MAX_RELEVANT_DISTANCE}")
    print(f"Top-k      : {config.TOP_K} of {config.CANDIDATE_K} candidates\n")

    print(f"{'Q':<5}{'category':<14}{'bestDist':>9}  {'evidence':<9}{'expected docs':<22}recall")
    print("-" * 72)

    in_scope: list[tuple[str, float, bool]] = []
    out_scope: list[tuple[str, float, bool]] = []
    misses: list[tuple[str, list[str], list[str]]] = []

    for question in questions:
        hits = store.search(question["question"])
        best = min(h.distance for h in hits)
        retrieved = {h.metadata["doc_id"] for h in hits}
        expected = [d for d in question["groundedness_doc_ids"] if not d.endswith(".csv")]

        if expected:
            found = any(e in retrieved for e in expected)
            recall = "hit" if found else "MISS"
            if not found:
                misses.append((question["id"], expected, sorted(retrieved)))
        else:
            recall = "-"

        sufficient = search_academic_documents(question["question"], "")["sufficient_evidence"]
        row = (question["id"], best, sufficient)
        if question["answer_type"] == "refusal":
            out_scope.append(row)
        elif expected:  # CSV-backed questions never touch the document index
            in_scope.append(row)

        print(
            f"{question['id']:<5}{question['category']:<14}{best:>9.3f}  "
            f"{str(sufficient):<9}{str(expected):<22}{recall}"
        )

    with_expected = [q for q in questions if any(
        not d.endswith(".csv") for d in q["groundedness_doc_ids"])]
    recall_pct = 100.0 * (len(with_expected) - len(misses)) / len(with_expected)

    in_max = max(b for _, b, _ in in_scope)
    out_min = min(b for _, b, _ in out_scope)

    print("\nRetrieval recall")
    print(f"  expected document in top-{config.TOP_K}: "
          f"{len(with_expected) - len(misses)}/{len(with_expected)} ({recall_pct:.1f}%)")
    for qid, expected, retrieved in misses:
        print(f"  MISS {qid}: expected one of {expected}, retrieved {retrieved}")

    print("\nRefusal separability")
    print(f"  in-scope  best distance: {min(b for _, b, _ in in_scope):.3f} .. {in_max:.3f}")
    print(f"  out-scope best distance: {out_min:.3f} .. {max(b for _, b, _ in out_scope):.3f}")
    if out_min > in_max:
        print(f"  SEPARABLE: any threshold in ({in_max:.3f}, {out_min:.3f}) splits them cleanly.")
    else:
        print(
            f"  OVERLAPPING by {in_max - out_min:.3f}: no single threshold separates them. "
            "Topical scope must be enforced by the agent instruction."
        )

    wrong_refusals = [q for q, _, s in in_scope if not s]
    wrong_answers = [q for q, _, s in out_scope if s]
    print(f"\n  at the current threshold ({config.MAX_RELEVANT_DISTANCE}):")
    print(f"    in-scope questions with insufficient evidence (would wrongly refuse): "
          f"{wrong_refusals or 'none'}")
    print(f"    out-of-scope questions with sufficient evidence (refused on topical "
          f"grounds instead): {wrong_answers or 'none'}")

    return 1 if (misses and recall_pct < 80) or wrong_refusals else 0


if __name__ == "__main__":
    raise SystemExit(main())
