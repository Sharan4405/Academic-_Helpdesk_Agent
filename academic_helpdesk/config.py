"""Central configuration, driven by environment variables with laptop-friendly defaults."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env so the CLI and the evaluation harness see the same configuration that
# `adk web` would. python-dotenv ships with google-adk.
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

DATA_DIR = PROJECT_ROOT / "data1"
DOCUMENTS_DIR = DATA_DIR / "documents"
STRUCTURED_DIR = DATA_DIR / "structured"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Which corpus the RAG index is built from:
#   "synthetic" -- the hand-written documents in data/documents (what eval/ scores)
#   "raw"       -- the real institute files in data/raw, run through
#                  `python -m academic_helpdesk.rag.extract` into data/processed
#   "all"       -- both
CORPUS_SOURCE = os.environ.get("CORPUS_SOURCE", "synthetic").strip().lower()
#   "prebuilt"  -- the already-embedded index in data1/chroma, imported with
#                  `python -m academic_helpdesk.rag.import_prebuilt`
CORPUS_DIRS = {
    "synthetic": [DOCUMENTS_DIR],
    "raw": [PROCESSED_DIR],
    "all": [DOCUMENTS_DIR, PROCESSED_DIR],
    "prebuilt": [],
}.get(CORPUS_SOURCE, [DOCUMENTS_DIR])
PREBUILT_DIR = DATA_DIR / "chroma"
LOGS_DIR = PROJECT_ROOT / "logs"
VECTOR_STORE_DIR = PROJECT_ROOT / ".chroma"

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Embeddings. Two backends:
#   "ollama" -- nomic-embed-text through a running Ollama server (768 dims)
#   "local"  -- ChromaDB's bundled all-MiniLM-L6-v2 ONNX model (384 dims), which
#               needs no server at all and so lets a hosted chat model (Groq,
#               OpenAI, Anthropic) run the whole system without Ollama. Groq
#               serves no embeddings endpoint, so this is required there.
EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "ollama").strip().lower()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")

# Vector store: "chroma" (default) or "numpy", an exact brute-force cosine search
# with no native dependency. Use numpy if ChromaDB crashes on your machine -- its
# HNSW code access-violates on some Windows setups. Fine up to ~100k chunks.
VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "chroma").strip().lower()

# The two backends produce different vector dimensions, so they must not share a
# collection. Keying the name on the backend makes switching safe: you re-ingest
# into a separate collection instead of corrupting the existing one.
COLLECTION_NAME = f"academic_documents_{EMBEDDING_BACKEND}"
if CORPUS_SOURCE == "prebuilt":
    COLLECTION_NAME = "iitj_academic"
elif CORPUS_SOURCE != "synthetic":
    COLLECTION_NAME += f"_{CORPUS_SOURCE}"  # likewise, one collection per corpus

# LiteLLM model string -- this is the only thing that changes to swap providers.
#   ollama_chat/qwen3:8b             local, free, 8B (what the brief names)
#   ollama_chat/llama3.1:8b          local, free, 8B
#   groq/openai/gpt-oss-20b          Groq, needs GROQ_API_KEY -- verified working,
#                                    see build_model()'s reasoning_format note
#   groq/qwen/qwen3.8-27b            Groq, same Qwen3 family as the local default;
#                                    tighter free-tier cap (7000 tok/min) than
#                                    gpt-oss-20b (8000), so gpt-oss-20b is the
#                                    better default for a multi-agent system
#   openai/gpt-4.1-mini              OpenAI, needs OPENAI_API_KEY
# Groq retires model ids often -- llama-3.1-8b-instant and llama-3.3-70b-versatile
# were both pulled from the catalog during this project. List the live ones with
#   curl -s https://api.groq.com/openai/v1/models \
#     -H "Authorization: Bearer $GROQ_API_KEY" | python -m json.tool
# For Ollama, prefer the "ollama_chat/" prefix over the legacy "ollama/"
# completion path -- it gives markedly better tool-calling behaviour.
CHAT_MODEL = os.environ.get("HELPDESK_MODEL", "ollama_chat/qwen3:8b")

# Environment variable LiteLLM expects for each non-Ollama provider prefix, used
# to fail fast with a useful message instead of a provider-side 401.
PROVIDER_API_KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together_ai": "TOGETHER_AI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Retrieval
CHUNK_TARGET_CHARS = int(os.environ.get("CHUNK_TARGET_CHARS", "1400"))
CHUNK_OVERLAP_CHARS = int(os.environ.get("CHUNK_OVERLAP_CHARS", "200"))
TOP_K = int(os.environ.get("TOP_K", "5"))
CANDIDATE_K = int(os.environ.get("CANDIDATE_K", "60"))
# Longest passage handed to the chat model. Pre-embedded chunks can run to
# thousands of characters; the tool sends the most query-relevant window of each
# so a request stays inside small per-minute token budgets (Groq free tier).
PASSAGE_MAX_CHARS = int(os.environ.get("PASSAGE_MAX_CHARS", "1500"))

# A cosine distance above this means "no document in the corpus covers this", and
# drives a refusal rather than letting the model improvise.
#
# The two embedding backends have different distance scales, so the default is
# per-backend. The "local" value is measured: `eval/check_retrieval.py` puts
# in-scope questions at 0.18-0.49 and out-of-scope ones at 0.47-0.67, so 0.55
# catches the genuinely uncovered topics with a ~0.06 margin.
#
# Note that the ranges OVERLAP. This threshold is a backstop against answering
# from an irrelevant passage; it cannot by itself enforce topical scope, because
# "what is my attendance in CSL7620" is legitimately close to the attendance
# policy. Scope is enforced by the orchestrator's explicit out-of-scope list in
# prompts.REFUSAL_BLOCK. See report section 8.3.
_DEFAULT_MAX_DISTANCE = {"local": "0.55", "ollama": "0.62"}
MAX_RELEVANT_DISTANCE = float(
    os.environ.get(
        "MAX_RELEVANT_DISTANCE", _DEFAULT_MAX_DISTANCE.get(EMBEDDING_BACKEND, "0.60")
    )
)

UNANSWERED_LOG = LOGS_DIR / "unanswered_questions.jsonl"
EMAIL_DRAFTS_LOG = LOGS_DIR / "email_drafts.jsonl"

CURRENT_SEMESTER = os.environ.get("CURRENT_SEMESTER", "Semester I")
CURRENT_ACADEMIC_YEAR = os.environ.get("CURRENT_ACADEMIC_YEAR", "2026-27")

LOGS_DIR.mkdir(parents=True, exist_ok=True)
