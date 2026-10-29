"""Retrieval tool exposed to the agents."""

from __future__ import annotations

from academic_helpdesk import config
from academic_helpdesk.rag import store

VALID_CATEGORIES = {
    "academic_rules",
    "curriculum",
    "schedule",
    "office_order",
    "directory",
    "template",
}


def search_academic_documents(query: str, category: str) -> dict:
    """Search the official academic document corpus and return the most relevant passages.

    Use this for any question about rules, regulations, policies, curriculum,
    credit requirements, deadlines, office orders or procedures. Always call this
    before answering such a question; never answer from your own knowledge.

    Args:
        query: The search query. Prefer the student's own wording plus any
            identifier that appears in it (for example "attendance 75% Major
            examination" or "AR-02.4 condonation").
        category: Optional filter, one of "academic_rules", "curriculum",
            "schedule", "office_order", "directory", "template". Pass an empty
            string to search the whole corpus, which is the usual choice.

    Returns:
        A dict with "results" (each carrying doc_id, title, section, citation and
        the passage text) and "sufficient_evidence", which is False when nothing
        in the corpus is relevant enough to ground an answer.
    """
    query = (query or "").strip()
    if not query:
        return {"results": [], "sufficient_evidence": False, "note": "Empty query."}

    category = (category or "").strip()
    if category and category not in VALID_CATEGORIES:
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
        results.append(
            {
                "doc_id": meta.get("doc_id", ""),
                "title": meta.get("title", ""),
                "section": meta.get("section", ""),
                "category": meta.get("category", ""),
                "citation": citation,
                "relevance": round(hit.score, 3),
                "passage": hit.text,
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
