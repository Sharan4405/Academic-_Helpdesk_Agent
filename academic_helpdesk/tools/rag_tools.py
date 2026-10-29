"""Retrieval tool exposed to the agents."""

from __future__ import annotations

from academic_helpdesk import config
from academic_helpdesk.rag import store

def _stem(word: str) -> str:
    return word[:5]


def _excerpt(text: str, query: str, limit: int) -> str:
    """The `limit`-character window of `text` that best covers the query's distinctive words.

    Windows are scored by the IDF weight of the distinct query words (matched by
    5-letter stem, so "exam" matches "examination") they contain. Counting raw word
    frequency instead lets common words such as "exam" or "semester" drag the window
    away from the one sentence that holds the answer.
    """
    if len(text) <= limit:
        return text
    idf = store._idf()
    unseen = max(idf.values(), default=1.0)
    weights = {_stem(w): idf.get(w, unseen) for w in store._words(query)}
    step = max(60, limit // 12)
    best_start, best_score = 0, -1.0
    for start in range(0, max(1, len(text) - limit + step), step):
        window = text[start : start + limit]
        present = {_stem(w) for w in store._words(window)}
        score = sum(weight for stem, weight in weights.items() if stem in present)
        if score > best_score:
            best_start, best_score = start, score
    start = max(0, min(best_start, len(text) - limit))
    if start > 0:  # begin on a word boundary
        start = text.find(" ", start) + 1 or start
    piece = text[start : start + limit].rsplit(" ", 1)[0]
    return ("..." if start > 0 else "") + piece + ("..." if start + limit < len(text) else "")


def valid_categories() -> set[str]:
    """Categories present in the loaded corpus (they differ between corpora)."""
    return set(store.known_categories())


def search_academic_documents(query: str, category: str) -> dict:
    """Search the official document corpus (rules, regulations, circulars, curricula, calendar, fees).

    Call this before answering any such question.

    Args:
        query: The student's wording plus any identifier in it.
        category: Leave as an empty string.

    Returns:
        "results" (doc_id, citation, passage) and "sufficient_evidence", False
        when nothing in the corpus is relevant enough to answer from.
    """
    query = (query or "").strip()
    if not query:
        return {"results": [], "sufficient_evidence": False, "note": "Empty query."}

    category = (category or "").strip()
    if category and category not in valid_categories():
        category = ""

    try:
        hits = store.search(query, category=category or None)
    except Exception as exc:
        return {
            "results": [],
            "sufficient_evidence": False,
            "error": f"Retrieval failed: {exc}",
        }

    # One shared character budget (TOP_K x PASSAGE_MAX_CHARS), weighted to the best hit:
    # the top passage may use up to 1.8x the per-passage cap, and what short chunks do
    # not use is passed down, so the request size stays the same.
    remaining = config.TOP_K * config.PASSAGE_MAX_CHARS
    limits: list[int] = []
    for i, hit in enumerate(hits):
        cap = int(1.8 * config.PASSAGE_MAX_CHARS) if i == 0 else remaining // (len(hits) - i)
        limit = max(300, min(len(hit.text), cap))
        limits.append(limit)
        remaining -= min(len(hit.text), limit)

    results = []
    for hit, limit in zip(hits, limits):
        meta = hit.metadata
        citation = f"{meta.get('doc_id', '?')} -- {meta.get('title', '?')}"
        if meta.get("section") not in {None, "", "(document)", "(preamble)"}:
            citation += f", section '{meta['section']}'"
        if meta.get("order_no"):
            citation += f" (Order/Notice No. {meta['order_no']})"
        first, last = meta.get("page_start"), meta.get("page_end")
        if first:
            citation += f", p. {first}" if first == last or not last else f", pp. {first}-{last}"
        results.append(
            {
                "doc_id": meta.get("doc_id", ""),
                "citation": citation,
                "passage": _excerpt(hit.text, query, limit),
            }
        )

    sufficient = bool(results) and store.is_sufficient(hits)

    payload: dict = {"results": results, "sufficient_evidence": sufficient}
    if not sufficient:
        payload["note"] = (
            "No passage in the official corpus is close enough to this question. "
            "Refuse to answer and log the question as unanswered."
        )
    return payload
