"""Demo web app for the helpdesk RAG.

    python -m academic_helpdesk.web.server            # http://127.0.0.1:8000
    python -m academic_helpdesk.web.server --port 8080

The React UI (frontend/) has two panels:
  * Chat -- the full multi-agent system, with the agent route, tool calls and
    retrieved documents behind each answer.
  * Evidence -- the RAG layer alone (no LLM): every retrieved chunk with its
    cosine distance, lexical re-rank score and the refusal verdict.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from academic_helpdesk import config
from academic_helpdesk.rag import store
from academic_helpdesk.runner import HelpdeskSession
from academic_helpdesk.tools.rag_tools import VALID_CATEGORIES

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Academic Helpdesk RAG demo")

# One agent session per browser conversation, keyed by a client-generated id.
_sessions: dict[str, HelpdeskSession] = {}


class SearchRequest(BaseModel):
    query: str
    category: str = ""
    top_k: int = config.TOP_K


class ChatRequest(BaseModel):
    session_id: str
    question: str
    mode: str = "multi"


def _chunk_count() -> int:
    try:
        return store.get_collection().count()
    except Exception:
        return 0


def _chat_ready() -> tuple[bool, str]:
    """Whether the configured chat model has what it needs, without calling it."""
    provider = config.CHAT_MODEL.split("/", 1)[0]
    key_env = config.PROVIDER_API_KEY_ENV.get(provider)
    if key_env and not os.environ.get(key_env):
        return False, f"{key_env} is not set"
    return True, ""


@app.get("/")
def index() -> FileResponse:
    page = STATIC_DIR / "index.html"
    if not page.exists():
        raise HTTPException(
            503, "Frontend not built. Run: cd frontend && npm install && npm run build"
        )
    return FileResponse(page)


@app.get("/api/status")
def status() -> dict:
    ready, reason = _chat_ready()
    return {
        "chunks": _chunk_count(),
        "collection": config.COLLECTION_NAME,
        "embedding": store.embedding_label(),
        "chat_model": config.CHAT_MODEL,
        "chat_ready": ready,
        "chat_issue": reason,
        "threshold": config.MAX_RELEVANT_DISTANCE,
        "top_k": config.TOP_K,
        "candidate_k": config.CANDIDATE_K,
        "categories": sorted(VALID_CATEGORIES),
    }


@app.post("/api/search")
def search(req: SearchRequest) -> dict:
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "Empty query.")
    category = req.category if req.category in VALID_CATEGORIES else None
    try:
        hits = store.search(query, top_k=max(1, min(req.top_k, 20)), category=category)
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc

    best = min((h.distance for h in hits), default=1.0)
    return {
        "query": query,
        "best_distance": round(best, 3),
        "threshold": config.MAX_RELEVANT_DISTANCE,
        "sufficient_evidence": bool(hits) and best <= config.MAX_RELEVANT_DISTANCE,
        "results": [
            {
                "doc_id": h.metadata.get("doc_id", ""),
                "title": h.metadata.get("title", ""),
                "section": h.metadata.get("section", ""),
                "category": h.metadata.get("category", ""),
                "order_no": h.metadata.get("order_no", ""),
                "distance": round(h.distance, 3),
                "score": round(h.score, 3),
                "passage": h.text,
            }
            for h in hits
        ],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Empty question.")

    session = _sessions.get(req.session_id)
    if session is None or session.mode != req.mode:
        try:
            session = HelpdeskSession(mode=req.mode)
        except Exception as exc:  # e.g. missing API key
            raise HTTPException(500, str(exc)) from exc
        _sessions[req.session_id] = session

    turn = await session.ask(question)
    return {
        "answer": turn.answer,
        "error": turn.error,
        "agents": turn.agents_involved,
        "delegated_to": turn.delegated_to,
        "tool_calls": turn.tool_calls,
        "retrieved_doc_ids": turn.retrieved_doc_ids,
    }


@app.post("/api/reset")
def reset(session_id: str) -> dict:
    _sessions.pop(session_id, None)
    return {"ok": True}


# Vite's hashed JS/CSS bundles.
if (STATIC_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


def main() -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="Academic Helpdesk RAG demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if _chunk_count() == 0:
        print("Vector store is empty. Run first: python -m academic_helpdesk.rag.ingest")
        return 1

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
