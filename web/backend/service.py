"""Web service that connects the helpdesk logic to the React frontend.

    python -m web.backend.service              # http://127.0.0.1:8000
    python -m web.backend.service --port 8080

  GET  /api/status          index size, models, refusal threshold
  POST /api/search          RAG layer only -- ranked chunks, no LLM
  POST /api/chat/stream     one agent turn, streamed as server-sent events:
                              step    an agent hand-off, tool call or tool result
                              wait    the provider rate-limited us; seconds until retry
                              done    the final answer plus the full trace
  POST /api/reset           forget a conversation
  GET  /api/unanswered      questions the agent refused (the human-referral log)
  GET  /api/email-drafts    email drafts the agent produced (never sent)

The service holds no logic of its own: it calls academic_helpdesk.runner for the
agents and academic_helpdesk.rag.store for retrieval, so the web UI exercises the
same code path as the CLI and the evaluation harness.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Lets `python service.py` work from any directory, not only `python -m web.backend.service`
# from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from academic_helpdesk import config
from academic_helpdesk.llm_client import rate_limit_callback
from academic_helpdesk.rag import store
from academic_helpdesk.runner import HelpdeskSession, Turn
from academic_helpdesk.tools.rag_tools import valid_categories

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(title="Academic Helpdesk web service")

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


def _read_jsonl(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:][::-1]  # newest first


def _compact(response: object) -> object:
    """Tool responses for the trace: keep the facts, drop bulky passage text."""
    if isinstance(response, dict):
        return {
            k: ([_compact_hit(h) for h in v] if k == "results" and isinstance(v, list) else _compact(v))
            for k, v in response.items()
        }
    if isinstance(response, list):
        return [_compact(v) for v in response[:20]]
    return response


def _compact_hit(hit: object) -> object:
    if not isinstance(hit, dict):
        return hit
    return {k: v for k, v in hit.items() if k != "passage"} | {
        "passage": str(hit.get("passage", ""))[:400]
    }


def _turn_payload(turn: Turn) -> dict:
    draft = next(
        (r["response"] for r in turn.tool_results if r["name"] == "draft_student_email"), None
    )
    return {
        "answer": turn.answer,
        "error": turn.error,
        "agents": turn.agents_involved,
        "delegated_to": turn.delegated_to,
        "tool_calls": turn.tool_calls,
        "tool_results": [
            {"name": r["name"], "response": _compact(r["response"])} for r in turn.tool_results
        ],
        "retrieved_doc_ids": turn.retrieved_doc_ids,
        "email_draft": draft,
    }


# --------------------------------------------------------------------------- API
@app.get("/api/status")
def status() -> dict:
    ready, reason = _chat_ready()
    return {
        "chunks": _chunk_count(),
        "collection": config.COLLECTION_NAME,
        "corpus": config.CORPUS_SOURCE,
        "vector_backend": config.VECTOR_BACKEND,
        "embedding": store.embedding_label(),
        "chat_model": config.CHAT_MODEL,
        "chat_ready": ready,
        "chat_issue": reason,
        "threshold": config.MAX_RELEVANT_DISTANCE,
        "top_k": config.TOP_K,
        "categories": sorted(valid_categories()),
    }


@app.post("/api/search")
def search(req: SearchRequest) -> dict:
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "Empty query.")
    category = req.category if req.category in valid_categories() else None
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
                "category": h.metadata.get("category", ""),
                "page_start": h.metadata.get("page_start"),
                "page_end": h.metadata.get("page_end"),
                "source_url": h.metadata.get("source_url", ""),
                "distance": round(h.distance, 3),
                "score": round(h.score, 3),
                "passage": h.text,
            }
            for h in hits
        ],
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
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

    queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

    async def run() -> None:
        rate_limit_callback.set(lambda seconds: queue.put_nowait(("wait", {"seconds": round(seconds)})))
        try:
            turn = await session.ask(question, on_step=lambda step: queue.put_nowait(("step", step)))
            queue.put_nowait(("done", _turn_payload(turn)))
        except Exception as exc:
            queue.put_nowait(("fail", {"error": f"{type(exc).__name__}: {exc}"}))
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(run())

    async def events():
        try:
            while (item := await queue.get()) is not None:
                yield _sse(*item)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/reset")
def reset(session_id: str) -> dict:
    _sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/api/unanswered")
def unanswered(limit: int = 50) -> list[dict]:
    return _read_jsonl(config.UNANSWERED_LOG, limit)


@app.get("/api/email-drafts")
def email_drafts(limit: int = 20) -> list[dict]:
    return _read_jsonl(config.EMAIL_DRAFTS_LOG, limit)


# ---------------------------------------------------------------- frontend bundle
@app.get("/")
def index() -> FileResponse:
    page = DIST_DIR / "index.html"
    if not page.exists():
        raise HTTPException(
            503, "Frontend not built. Run: cd web/frontend && npm install && npm run build"
        )
    return FileResponse(page)


if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")


def main() -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="Academic Helpdesk web service")
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
