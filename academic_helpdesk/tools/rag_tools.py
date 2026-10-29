"""Retrieval tool exposed to the agents."""

from __future__ import annotations

import re

from academic_helpdesk import config
from academic_helpdesk.rag import store

_WORD = re.compile(r"[a-z0-9]{3,}")


def _excerpt(text: str, query: str, limit: int) -> str:
    """The `limit`-character window of `text` that overlaps the query terms most."""
    if len(text) <= limit:
        return text
    terms = set(_WORD.findall(query.lower()))
    step = max(100, limit // 6)
    best_start, best_score = 0, -1
    for start in range(0, len(text) - limit + step, step):
        window = text[start : start + limit].lower()
        score = sum(window.count(t) for t in terms)
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
    """Search the official academic document corpus and return the most relevant passages.

    Use this for any question about rules, regulations, policies, curriculum,
    credit requirements, deadlines, office orders or procedures. Always call this
    before answering such a question; never answer from your own knowledge.

    Args:
        query: The search query. Prefer the student's own wording plus any
            identifier that appears in it (for example "attendance 75% Major
            examination" or "CSL7620").
        category: Optional category filter. Pass an empty string to search the
            whole corpus, which is almost always the right choice.

    Returns:
        A dict with "results" (each carrying doc_id, title, section, citation and
        the passage text) and "sufficient_evidence", which is False when nothing
        in the corpus is relevant enough to ground an answer.
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

    results = []
    for hit in hits:
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
                "title": meta.get("title", ""),
                "section": meta.get("section", ""),
                "category": meta.get("category", ""),
                "source_url": meta.get("source_url", ""),
                "doc_date": meta.get("doc_date", ""),
                "citation": citation,
                "relevance": round(hit.score, 3),
                "passage": _excerpt(hit.text, query, config.PASSAGE_MAX_CHARS),
            }
        )

    best_distance = min((h.distance for h in hits), default=1.0)
    sufficient = bool(results) and best_distance <= config.MAX_RELEVANT_DISTANCE

    payload: dict = {"results": results, "sufficient_evidence": sufficient}
    if not sufficient:
        payload["note"] = (
            "No passage in the official corpus is close enough to this question. "
            "Refuse to answer and log the question as unanswered."
        )
    return payload
