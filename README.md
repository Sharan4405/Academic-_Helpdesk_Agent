# Multi-Agent Academic Helpdesk Agent

A local, fully offline academic helpdesk for IIT Jodhpur, built with **Google ADK**,
**Ollama**-hosted 8B models, **ChromaDB** retrieval and deterministic CSV tools.
It answers questions about academic rules and regulations, curriculum and credit
requirements, the timetable and the examination schedule, and it drafts emails to
course instructors. Anything outside that scope it refuses and logs for a human.

Course project for *Autonomous Systems*.

---

## 1. What it does

| Student asks | Handled by | How |
|---|---|---|
| "What is the attendance requirement to sit in the Major exam?" | `policy_agent` | RAG over the document corpus |
| "What is the slot for the course Autonomous Systems?" | `schedule_agent` | CSV lookup over the offering list and timetable |
| "How many 400 level electives have been floated by the Humanities department in this semester?" | `schedule_agent` | Deterministic filter + count, cross-checked against the offering notice |
| "How many Open Elective credits do I need for a B.Tech. degree?" | `policy_agent` | RAG over the curriculum documents |
| "Write an email to the course instructor of CSL7570 that I need leave for 2 days" | `email_agent` | Instructor lookup + template-rendered draft |
| "What are the available dining options on the campus?" | orchestrator | Refuses, and logs the question for human referral |

Every answer ends with a `Sources:` line naming the document or CSV it came from.

---

## 2. Architecture

```
                         ┌──────────────────────────────┐
     student question ──▶ │  helpdesk_orchestrator       │
                         │  routes, refuses, logs       │
                         └───┬──────────┬───────────┬───┘
                 transfer_to │          │           │
            ┌────────────────▼─┐ ┌──────▼────────┐ ┌▼───────────────┐
            │  policy_agent    │ │ schedule_agent│ │  email_agent   │
            │  rules, curric.  │ │ slots, exams  │ │ contacts,draft │
            └────────┬─────────┘ └──────┬────────┘ └───────┬────────┘
                     │                  │                  │
     ┌───────────────▼──────────┐  ┌────▼─────────────┐  ┌──▼──────────────────┐
     │ search_academic_documents│  │ lookup_course    │  │ lookup_course_      │
     │  (ChromaDB + Ollama      │  │ find_courses     │  │   instructor        │
     │   embeddings, hybrid     │  │ get_slot_timing  │  │ draft_student_email │
     │   vector + lexical)      │  │ lookup_exam_...  │  │ (TPL-01 templates)  │
     └──────────────────────────┘  │ check_slot_clash │  └─────────────────────┘
                                   └──────────────────┘
                     log_unanswered_question  ──▶ logs/unanswered_questions.jsonl
```

Three design decisions carry most of the quality:

1. **Facts that can be computed are never left to the model.** Counts, slots,
   dates, credits and email addresses come from CSV tools that return an
   authoritative `match_count` / record. An 8B model miscounts table rows; it does
   not miscount a number handed to it.
2. **Retrieval is hybrid.** Pure cosine similarity on a local embedding model is
   weak on exact identifiers (`AR-02.4`, `CSL7620`, `HSL4110`). The store
   over-fetches 20 candidates and re-ranks with a small lexical bonus for
   identifier overlap. Cheap, and it is what makes citations land on the right
   clause.
3. **Refusal is driven by evidence, not vibes.** `search_academic_documents`
   returns `sufficient_evidence: false` when the best cosine distance exceeds a
   threshold, and the instruction makes that a hard stop. Out-of-scope questions
   are refused by the orchestrator without ever reaching a specialist.

Email drafts are rendered **by code** from the approved templates in `TPL-01`, so
every draft carries the mandatory fields and the right clause references
regardless of how the model phrases its covering text. Nothing is ever sent.

---

## 3. Repository layout

```
academic_helpdesk/
  agent.py              agent graph; root_agent, plus the single-agent baseline
  prompts.py            all agent instructions (routing, citation, refusal policy)
  runner.py             programmatic driver; returns answer + tool-call trace
  cli.py                interactive terminal client
  config.py             env-driven configuration
  rag/
    chunking.py         front-matter-aware, header-aware markdown chunking
    store.py            ChromaDB + Ollama embeddings + lexical re-rank
    ingest.py           index builder CLI
  tools/
    catalogue.py        CSV loading, department alias normalisation
    rag_tools.py        search_academic_documents
    schedule_tools.py   lookup_course, find_courses, get_slot_timing, exams, clash
    contact_tools.py    instructor / faculty / office contact lookups
    email_tools.py      draft_student_email (TPL-01 template rendering)
    escalation_tools.py log_unanswered_question, read_unanswered_log
data/
  documents/            33 academic documents (markdown + YAML front matter)
  structured/           courses.csv, instructors.csv, slots.csv, exam_schedule.csv
eval/
  questions.json        the 30-question evaluation set with ground truth
  QUESTIONS.md          the same set, human-readable
  run_eval.py           accuracy / groundedness / refusal / routing / consistency
  summarise_results.py  turns result JSON into the report's markdown tables
  check_tools.py        LLM-free self-test of the deterministic layer
  check_retrieval.py    LLM-free retrieval recall and refusal separability
  results/              evaluation output
logs/
  unanswered_questions.jsonl   questions referred to a human
  email_drafts.jsonl           every draft produced, for audit
report/REPORT.md        findings
```

### The document corpus

33 documents, with all personal data replaced by dummy values, covering:

| Prefix | Count | Content |
|---|---|---|
| `AR-` | 11 | Academic rules: grading, attendance, examinations, makeup, leave, registration, add/drop, probation, integrity, rechecking, leave of absence |
| `CU-` | 9 | Curriculum: B.Tech. and M.Tech. degree requirements, CSE and AI&DS curricula, open elective policy, minor/honours, Ph.D. coursework, course catalogue, credit definition |
| `SC-` | 4 | Academic calendar, timetable slot system, examination schedule notice, course offering list |
| `OO-` | 6 | Recent office orders: attendance condonation, registration extension, makeup committee, fees, SWAYAM credit transfer, eligibility publication |
| `DIR-` | 2 | Faculty contact directory, academic administration contacts and forms index |
| `TPL-` | 1 | Approved email templates |

The documents deliberately **cross-reference and partially override each other**
(for example `OO-02` moves a deadline set in `SC-01`, and `OO-01` relaxes a
ceiling set in `AR-02`), which is what makes citation accuracy worth measuring
rather than trivial.

---

## 4. Setup

The chat model and the embedding model are configured independently, which gives
two supported setups. **Path A is fully local and is what the project reports on
as the primary configuration** (the brief names Ollama). **Path B runs the chat
model on Groq** — useful because an 8B model is far more reliable at tool-calling
when hosted than when run locally at Q4, and because it needs no multi-gigabyte
download; it is also the LLM-comparison axis the brief asks for.

| | Path A — fully local | Path B — Groq |
|---|---|---|
| Chat | `ollama_chat/qwen3:8b` | `groq/openai/gpt-oss-20b` |
| Embeddings | `nomic-embed-text` via Ollama | Chroma's bundled MiniLM, no server |
| Needs Ollama | yes | **no** |
| Cost | free | free tier available, then per-token |
| Download | ~5 GB | ~80 MB (embedder only) |
| Offline | yes | no |

Common steps:

```powershell
# Python environment (3.10+)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

On Linux or macOS use `source .venv/bin/activate`.

**Path A — fully local (default).** Runs comfortably on a 16 GB laptop: an 8B
chat model at Q4 uses about 6 GB and the embedder about 0.3 GB.

```powershell
# Install Ollama from https://ollama.com/download, then
ollama pull qwen3:8b
ollama pull nomic-embed-text
ollama serve                 # if not already running as a service

python -m academic_helpdesk.rag.ingest
```

**Path B — Groq, no Ollama required.**

1. Create a free account at [console.groq.com](https://console.groq.com) and
   open **API Keys** → **Create API Key**. Copy it immediately — Groq shows it
   once.
2. Check which model ids are currently live — Groq retires them often enough
   that this project hit two dead ids (`llama-3.1-8b-instant`,
   `llama-3.3-70b-versatile`) while being built:
   ```bash
   curl -s https://api.groq.com/openai/v1/models \
     -H "Authorization: Bearer gsk_..." | python -m json.tool
   ```
   `groq/openai/gpt-oss-20b` is verified working with this project as of
   2026-10. `groq/qwen/qwen3.8-27b` is the same Qwen3 family the brief names,
   also verified, but its free-tier cap is tighter (7000 vs 8000 tokens/min) —
   prefer `gpt-oss-20b` unless you specifically want the Qwen3 comparison.
3. Edit `.env`:
   ```ini
   HELPDESK_MODEL=groq/openai/gpt-oss-20b
   GROQ_API_KEY=gsk_...
   EMBEDDING_BACKEND=local
   ```
   `EMBEDDING_BACKEND=local` is required here — Groq serves chat completions
   only, no embeddings endpoint, so RAG needs the server-free MiniLM embedder
   instead of Ollama's `nomic-embed-text`.

   Groq's reasoning models (gpt-oss, qwen3) attach a `reasoning_content` field
   to their replies; ADK round-trips it into the next turn's history, and Groq
   then rejects that resubmitted field as invalid — a 400 on the second turn of
   every conversation. `build_model()` in `academic_helpdesk/agent.py` works
   around this by setting `reasoning_format="hidden"` for any `groq/` model, so
   you don't need to do anything beyond picking a `groq/` model id.
4. Build the index (first run downloads the ~80 MB ONNX embedder, cached after):
   ```bash
   python -m academic_helpdesk.rag.ingest
   ```
5. Try it:
   ```bash
   python -m academic_helpdesk.cli --trace
   ```

**Free-tier rate limits.** Groq's free tier caps requests per minute (check your
current limits at [console.groq.com/settings/limits](https://console.groq.com/settings/limits)
— they change). A single question is fine; a 30-question evaluation run can hit
the limit partway through. `eval/run_eval.py` retries rate-limited calls with
exponential backoff automatically, and `--delay` adds a pause between questions
if you want to stay under the limit rather than lean on retries:
```bash
python eval/run_eval.py --model groq/openai/gpt-oss-20b --tag groq-gptoss20b --delay 2
```

Any provider LiteLLM supports works the same way — only `HELPDESK_MODEL` and the
matching key change (`openai/...` + `OPENAI_API_KEY`, `anthropic/...` +
`ANTHROPIC_API_KEY`, etc.). A missing key fails immediately with a message
naming the variable, rather than as a 401 inside an agent turn.

The two embedding backends produce different vector dimensions (768 vs 384), so
they are kept in separate Chroma collections (`academic_documents_ollama` and
`academic_documents_local`). Switching backends means re-running the ingest, not
a corrupted index.

### Verify before spending time on model runs

```bash
python eval/check_tools.py        # 44 assertions, no LLM and no Ollama needed
python eval/check_retrieval.py    # retrieval recall + refusal separability
```

`check_tools.py` validates the ground truth behind the evaluation set.
`check_retrieval.py` measures the retrieval layer deterministically — see
Section 6.1.

---

## 5. Running

```bash
# Interactive, multi-agent (default)
python -m academic_helpdesk.cli

# Show which agent handled the question and which tools it called
python -m academic_helpdesk.cli --trace

# One-shot
python -m academic_helpdesk.cli --ask "What is the slot for Autonomous Systems?"

# Single-agent baseline, for the architecture comparison
python -m academic_helpdesk.cli --mode single

# A different LLM -- any LiteLLM model string
python -m academic_helpdesk.cli --model ollama_chat/llama3.1:8b
python -m academic_helpdesk.cli --model groq/openai/gpt-oss-20b
```

**Web demo.** A React UI with a chat panel (the full agent system: answer, cited
sources, agent route and tool calls) beside an Evidence panel (RAG layer only, no
LLM: every retrieved chunk with its distance, re-rank score and the refusal
verdict). After ingesting once:

```bash
python -m academic_helpdesk.web.server        # http://127.0.0.1:8000
```

The built UI is committed in `academic_helpdesk/web/static/`, so no Node is needed
to run it. To change the UI: `cd frontend && npm install && npm run dev`
(proxies `/api` to the Python server), then `npm run build`.

The ADK developer UI also works, since `academic_helpdesk/agent.py` exposes
`root_agent`:

```bash
adk web          # then pick "academic_helpdesk" in the browser
adk run academic_helpdesk
```

---

## 6. Evaluation

```bash
# Single pass over all 30 questions
python eval/run_eval.py

# Three passes, to find questions whose answers move between runs
python eval/run_eval.py --runs 3 --tag qwen3-multi

# Architecture comparison
python eval/run_eval.py --mode single --tag baseline

# LLM comparison
python eval/run_eval.py --model ollama_chat/llama3.1:8b --tag llama31
python eval/run_eval.py --model groq/openai/gpt-oss-20b --tag groq-gptoss20b --delay 2
```

Results land in `eval/results/` as JSON with per-question detail. Metrics:

| Metric | Definition |
|---|---|
| **accuracy** | Answerable questions whose answer contains every required fact and no forbidden one; refusal questions that were refused |
| **groundedness** | Accurate answers that cite at least one expected source **and** cite no document id that does not exist in the corpus |
| **correct refusal** | Share of the 5 out-of-scope / 1 personal-record questions that were refused |
| **false refusal** | Answerable questions that were wrongly refused |
| **routing** | Share delegated to the expected specialist agent |
| **consistency** | With `--runs > 1`, the questions whose verdict changed between runs |

The 30 questions are 11 policy, 8 schedule, 5 email and 6 out-of-scope, listed in
`eval/questions.json` with a reference answer and the sources a grounded answer
must cite. Findings are in [report/REPORT.md](report/REPORT.md).

---

## 7. Unanswered-question log

Every refusal appends a line to `logs/unanswered_questions.jsonl`:

```json
{"timestamp": "2026-10-26T14:31:07", "question": "What are the available dining options on the campus?",
 "reason_code": "out_of_scope", "reason": "Not an academic matter the helpdesk covers ...",
 "notes": "no matching passage in the corpus", "status": "pending_human_review"}
```

Reason codes are `out_of_scope`, `no_supporting_document`, `needs_personal_record`
and `ambiguous`. The `no_supporting_document` entries are the useful ones: they
are in-scope questions the corpus does not yet cover, i.e. the backlog of
documents to add.

---

## 8. Tuning notes

| Symptom | Change |
|---|---|
| Refuses questions it should answer | raise `MAX_RELEVANT_DISTANCE` (local default 0.55 → 0.62) |
| Answers questions no document covers | lower `MAX_RELEVANT_DISTANCE`, then re-check with `eval/check_retrieval.py` |
| Answers out-of-scope *topics* | this is not a threshold problem — see Section 9 and extend the out-of-scope list in `prompts.REFUSAL_BLOCK` |
| Cites the right document but the wrong clause | lower `CHUNK_TARGET_CHARS` to 900 and re-ingest |
| Misses context that spans sections | raise `TOP_K` to 7 |
| Model emits malformed tool calls | keep the `ollama_chat/` prefix; prefer `qwen3:8b` over `mistral:7b`, or switch to a hosted model (Path B) |

After changing any chunking or embedding value, re-ingest:
`python -m academic_helpdesk.rag.ingest --rebuild`

Measured retrieval behaviour with `EMBEDDING_BACKEND=local`
(`python eval/check_retrieval.py`, deterministic):

- expected document in the top-5 for **23/24** questions (95.8%)
- in-scope best distance 0.184–0.488; out-of-scope 0.471–0.670
- the two ranges **overlap by 0.017**, so the threshold cannot enforce topical
  scope on its own. At 0.55 it correctly refuses the three questions no document
  covers (dining, transport, hostel) with zero false refusals, and the remaining
  two (placement statistics, "what is *my* attendance") are refused by the
  orchestrator's explicit out-of-scope list instead.

---

## 9. Limitations

- The corpus is a realistic reconstruction with dummy personal data, not the
  Institute's live document set. Answers are correct with respect to this corpus.
- No access to any individual student's record, so attendance, grades and
  registration status questions are refused by design.
- Email drafts are drafts. Nothing is sent, and no mail credentials exist
  anywhere in the project.
- Conversation memory is in-process (`InMemorySessionService`); restarting the
  CLI starts a new conversation.
