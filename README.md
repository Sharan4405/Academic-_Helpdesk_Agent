# Multi-Agent Academic Helpdesk Agent

An academic helpdesk for IIT Jodhpur built with **Google ADK**, **LiteLLM**, retrieval
over real Institute documents, and deterministic CSV tools. It answers questions about
academic rules, curriculum and credits, the timetable and course offerings, and drafts
emails to course instructors. Anything outside that scope it refuses, and logs for a
human.

Course project for *Autonomous Systems*, IIT Jodhpur. A browser demo is in
[web/](web/README.md).

**Authors:** Jatin Purbia (B23CH1022), Anuj Trivedi (B23CH1006), Sharana Gouda Lakshetty (B23CH1042).

## What it does

| Student asks | Handled by | How |
|---|---|---|
| "What is the attendance requirement to sit in the Major exam?" | `policy_agent` | RAG over the document index |
| "When is the Minor examination in Semester I?" | `policy_agent` | RAG over the academic calendar |
| "What is the slot for the course Autonomous Systems?" | `schedule_agent` | CSV lookup (`courses.csv`, `timetable.csv`) |
| "How many 400 level electives has the Humanities department floated?" | `schedule_agent` | Deterministic filter and count |
| "Write an email to the instructor of CSL7570 that I need leave for 2 days" | `email_agent` | Instructor lookup, then a template-rendered draft (never sent) |
| "What are the available dining options on the campus?" | orchestrator | Refuses, and logs the question |

Every answer ends with a `Sources:` line naming the document (with pages) or CSV it came
from.

## Architecture

```
student question ──▶ helpdesk_orchestrator  (routes, refuses, logs)
                        │ transfer_to_agent
          ┌─────────────┼───────────────┐
     policy_agent   schedule_agent   email_agent
          │              │               │
 search_academic_   lookup_course    lookup_course_instructor
   documents        find_courses     draft_student_email
 lookup_course      get_slot_timing
                    check_slot_clash
              log_unanswered_question ──▶ logs/unanswered_questions.jsonl
```

Three design decisions carry the quality:

1. **Facts that can be computed are never left to the model.** Counts, slots, rooms and
   email addresses come from CSV tools that return an authoritative `match_count` or
   record. `check_slot_clash` compares real meeting times, including courses that list
   explicit times instead of a slot code.
2. **Retrieval is hybrid and authority-aware.** Vector search is combined with
   IDF-weighted keyword coverage, so scanned or noisy pages that embed badly are still
   found; a passage containing every distinctive word of the question counts as
   evidence. Where a circular supersedes a regulation on a topic (from
   `doc_authority.csv`), the circular is ranked first and the base regulation demoted.
3. **Refusal is driven by evidence.** `search_academic_documents` returns
   `sufficient_evidence: false` when nothing close enough exists, and the prompts make
   that a hard stop. Out-of-scope topics are refused by the orchestrator before any
   specialist runs.

Email drafts are rendered **by code** from fixed templates that quote no rule, clause or
form number, so a draft cannot cite something that does not exist.

## Repository layout

```
academic_helpdesk/
  agent.py          agent graph (root_agent) and the single-agent baseline
  prompts.py        agent instructions (kept short: every model call re-sends them)
  runner.py         programmatic driver; returns the answer plus the full trace
  llm_client.py     waits out provider rate limits instead of failing the turn
  cli.py            interactive terminal client
  config.py         env-driven configuration
  rag/              store.py (search, re-rank), import_prebuilt.py, numpy_store.py,
                    extract.py (raw files -> markdown), chunking.py, ingest.py
  tools/            rag_tools, schedule_tools, contact_tools, email_tools,
                    escalation_tools, catalogue (CSV loading)
data1/
  chroma/           the pre-embedded index (390 chunks, 33 documents, MiniLM 384-d)
  structured/       courses.csv, timetable.csv, faculty.csv, doc_authority.csv
eval/               30-question evaluation set, harness, summariser, deterministic checks
web/                backend/service.py (FastAPI) and frontend/ (React)
report/REPORT.md    method and findings
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # then put your GROQ_API_KEY in .env
python -m academic_helpdesk.rag.import_prebuilt
```

`import_prebuilt` loads the 390 stored vectors from `data1/chroma` as they are and checks
that the query embedder (ChromaDB's bundled all-MiniLM-L6-v2) reproduces them (cosine
1.0000). Groq has no embeddings endpoint, which is why embeddings run locally.

The defaults need no `.env` beyond the key: `CORPUS_SOURCE=prebuilt`, local embeddings,
`groq/qwen/qwen3.8-27b`, `TOP_K=3`. To index your own files instead, put them in
`data1/raw/` (git-ignored), set `CORPUS_SOURCE=raw`, then run
`python -m academic_helpdesk.rag.extract` and `python -m academic_helpdesk.rag.ingest`.

The chat model is any LiteLLM string in `HELPDESK_MODEL`: `groq/qwen/qwen3.8-27b` (the
default here), `groq/openai/gpt-oss-20b`, or a local `ollama_chat/qwen3:8b`. Groq retires
model ids often; list the live ones with
`curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"`.

## Running

```powershell
python -m academic_helpdesk.cli --trace                      # interactive
python -m academic_helpdesk.cli --ask "What is the slot for Autonomous Systems?" --trace
python -m academic_helpdesk.cli --mode single                # single-agent baseline
python service.py                                            # web demo, from web\backend
```

On Groq's free tier a turn can take one to two minutes, because each turn makes several
model calls and the per-minute token limit is a few thousand tokens. The client waits as
long as Groq asks and retries; nothing is lost.

## Evaluation

```powershell
python eval/check_tools.py         # CSV tools, drafts, log: 48 assertions, no model
python eval/check_retrieval.py     # retrieval recall and refusal separability, no model
python eval/evidence_eval.py       # all 30 questions: is the right evidence handed to the model?
python eval/run_eval.py --runs 3 --mode multi --tag qwen27-multi   # scores the model's answers
python eval/make_report_assets.py  # tables and charts for the model runs
python eval/projection.py          # PROJECTED model results (expectations, not measurements)
```

The 30 questions (11 policy, 9 schedule, 5 email, 5 out of scope) are in
`eval/questions.json`, with reference answers read from the source documents and, for
schedule and email, derived from the CSVs by code.

**Measured results** (`evidence_eval.py`, no model involved): the right document or
record is found for 24 of 25 answerable questions, the required facts reach the model for
24 of 25 (the other is a deliberate limit case), and the evidence check gives the right
verdict for 15 of 16 questions that have one.

![Evidence handed to the model, by question category](eval/metrics/charts/evidence_by_category.png)

`eval/metrics/projected_*` (CSV, JSON and three charts) hold the *expected* model results. They are
projections made before the model runs and are labelled that way in every file; they are not
measurements.

Scoring the model's own answers (`run_eval.py`) takes hours on Groq's free tier and has
**not been completed**, so no model accuracy figure is reported. Method, per-question
results, defects found and limitations are in [report/REPORT.md](report/REPORT.md);
tables and charts are in [eval/metrics/](eval/metrics/).

## Unanswered-question log

Every refusal appends a line to `logs/unanswered_questions.jsonl` with the question, a
reason code (`out_of_scope`, `no_supporting_document`, `needs_personal_record`,
`ambiguous`) and `status: pending_human_review`. The `no_supporting_document` entries are
in-scope questions the corpus does not cover, which is the backlog of documents to add.

## Limitations

- The document index covers 33 documents (regulations, circulars, curricula, calendar,
  fees). A question they do not answer, for example a separate Open Elective total for
  B.Tech., gets an honest "not specified" or a refusal.
- Exam dates exist only in the calendar documents, not in the CSV tables.
- Office contact addresses in `contact_tools.py` are placeholders.
- No access to any individual student's record: attendance, grades and registration
  status questions are refused by design.
- Email drafts are drafts. Nothing is sent and no mail credentials exist.
- Conversation memory is in-process; restarting starts a new conversation.
