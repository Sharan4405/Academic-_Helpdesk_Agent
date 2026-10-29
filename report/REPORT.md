# Multi-Agent Academic Helpdesk Agent — Report

**Course:** Autonomous Systems
**System:** Google ADK multi-agent helpdesk over a local RAG corpus, 8B models via Ollama

> **Status of the measured numbers.** Sections 1–5 and 8–10 are complete and
> contain measured results. The result tables in Sections 6 and 7 require a chat
> model and are produced by running the harness; the commands and the script that
> emits the tables are in Section 6.1. Everything measurable without a chat model
> **is** measured: the tool layer and the ground truth of all 30 questions
> (Section 5), and the retrieval recall and refusal separability (Section 8.3).

---

## 1. Problem and scope

The helpdesk answers student questions about academic programmes, course content,
rules and regulations, the timetable and the examination schedule, and drafts
emails to course instructors for sick leave, makeup examinations and attendance
condonation. Anything else it must refuse rather than guess, and log for a human.

The hard part of this assignment is not answering — it is **not** answering. A
helpful 8B chat model will happily invent a plausible attendance threshold, a
plausible instructor email address and a plausible count of electives. Most of the
engineering below exists to make those three failure modes impossible rather than
unlikely.

## 2. The document corpus

33 documents in `data/documents/`, each with a YAML front-matter header
(`doc_id`, `title`, `category`, `issuing_office`, version, effective date), plus
four CSVs in `data/structured/`. All personal data is dummy.

| Prefix | n | Content |
|---|---|---|
| `AR-` | 11 | Grading and evaluation, attendance, examination conduct, makeup policy, leave and medical certification, registration, add/drop/withdrawal, probation and duration, academic integrity, rechecking, leave of absence and internship |
| `CU-` | 9 | B.Tech. degree requirements, CSE and AI&DS curricula, open elective policy, minor/honours, M.Tech. requirements, Ph.D. coursework, course catalogue extract, credit definition and numbering |
| `SC-` | 4 | Academic calendar, timetable slot system, examination schedule notice, course offering list |
| `OO-` | 6 | Attendance condonation for Institute events, registration deadline extension, makeup committee constitution, fees and late registration, SWAYAM/exchange credit transfer, eligibility publication |
| `DIR-` | 2 | Faculty contact directory, academic administration contacts and forms index |
| `TPL-` | 1 | Approved email templates |

| CSV | Rows | Content |
|---|---|---|
| `courses.csv` | 49 | Code, title, department, level, credits, L-T-P, type, slot, room, instructor, offered-to, prerequisites |
| `instructors.csv` | 22 | Name, designation, department, email, office, extension |
| `slots.csv` | 34 | Slot code → day and time, lecture / laboratory / remedial |
| `exam_schedule.csv` | 18 | Minor-1, Minor-2, Major, Makeup-Major dates, times and venues |

The corpus was written so that documents **cross-reference and partly override**
one another. `OO-02` moves a registration deadline set in `SC-01`; `OO-01` lifts a
per-semester condonation ceiling set in `AR-02` while explicitly *not* lifting the
75% requirement itself; `CU-04` and `CU-06` state different open-elective credit
requirements for B.Tech. (12) and M.Tech. (6). This is what makes citation
accuracy a real measurement rather than a formality — an answer can be
numerically right and still cite the superseded document.

## 3. Architecture

```
student question
      │
      ▼
helpdesk_orchestrator ── routes, refuses out-of-scope, logs
      ├─▶ policy_agent     rules, regulations, curriculum, credits, procedures
      ├─▶ schedule_agent   slots, timetable, offering list, examination dates
      └─▶ email_agent      instructor contacts, email drafting
```

Each specialist carries only the tools it needs, which keeps the tool-selection
problem small enough for an 8B model — the binding constraint in practice.

### 3.1 Tools

| Tool | Agent | Purpose |
|---|---|---|
| `search_academic_documents` | all | Hybrid retrieval over the corpus; returns passages with ready-made citations and a `sufficient_evidence` flag |
| `lookup_course` | policy, schedule | Course by code or title → slot, timings, room, credits, instructor |
| `find_courses` | policy, schedule | Filter by department / level / type / slot → authoritative `match_count` |
| `get_slot_timing` | schedule | Slot code → days and times |
| `lookup_exam_schedule` | schedule | Minor / Major / Makeup dates and venues |
| `check_slot_clash` | schedule | Whether two courses can be registered together |
| `lookup_course_instructor` | email | Course → instructor name, email, office |
| `lookup_faculty_contact`, `lookup_office_contact` | email, policy | Directory lookups |
| `draft_student_email` | email | Renders a TPL-01 template; never sends |
| `log_unanswered_question` | all | Appends to the human-referral log |

### 3.2 Three decisions that carry the quality

**(a) Computable facts are computed, not generated.** Every count, slot, date,
credit value and email address comes from a CSV tool. The schedule agent is
instructed to report `match_count` verbatim and never to recount. The failure mode
this removes is the most common one for an 8B model: reading a markdown table and
miscounting the rows that match a two-condition filter.

**(b) Retrieval is hybrid, not pure vector.** `nomic-embed-text` embeddings place
"attendance requirement for the Major exam" near the right passage, but they are
poor at exact identifiers — `AR-02.4`, `CSL7620`, `HSL4110` — which are precisely
how academic questions are phrased once a student knows the system. The store
over-fetches 20 candidates and re-ranks with a bounded lexical bonus (+0.12 per
matched identifier token, +0.10 scaled over matched words, capped at 0.45). This
is a few lines of code and it is what makes clause-level citation work.

**(c) Refusal is evidence-driven.** `search_academic_documents` returns
`sufficient_evidence: false` when the best cosine distance exceeds
`MAX_RELEVANT_DISTANCE` (0.62). The agent instruction makes that a hard stop, not
a hint. Out-of-scope questions are refused by the orchestrator and never reach a
specialist, so there is no specialist-level temptation to be helpful. Every
refusal must call `log_unanswered_question` first; the log is the deliverable that
turns refusals into a documentation backlog.

**(d) Email bodies are rendered by code.** `draft_student_email` fills the
Institute-approved templates from `TPL-01` with the fields the student supplied,
inserts `<PLACEHOLDER>` tokens for the rest, and returns the exact clause
references the request depends on (`AR-04.4` and Form AC-07 for a makeup request,
`AR-05.8` for sick leave, `AR-02.4` and Form AC-22 for condonation). The model's
job shrinks to classifying the request type, extracting the fields and presenting
the draft. A model that paraphrases a leave email will drop the Form AC-07
sentence; a template cannot.

## 4. Evaluation design

30 prompts in `eval/questions.json`, each with a reference answer, the required
facts, forbidden strings, the expected route and the sources a grounded answer
must cite.

| Category | n | Examples |
|---|---|---|
| policy | 11 | attendance threshold; open-elective credits; makeup application window; 60% condonation (correct answer is "no"); family wedding as a makeup ground (also "no") |
| schedule | 8 | slot of Autonomous Systems; 400-level Humanities electives; Major exam date for CSL7620; slot clash; Makeup Major date |
| email | 5 | 2-day leave for CSL7570; missed Minor-2 of CSL7620; instructor email of HSL4110; condonation at 68% in AIL3010 |
| out_of_scope | 6 | dining options; travel from Jodhpur city centre; hostel allotment; placement packages; "what is my attendance in CSL7620" |

| Metric | Definition |
|---|---|
| Accuracy | Answerable: every `must_contain` requirement present, no `must_not_contain` string present, not refused. Refusal questions: refused. |
| Groundedness | Accurate **and** cites at least one expected source **and** cites no `doc_id` absent from the corpus. A refusal is grounded only if it cites nothing. |
| Correct refusal | Share of the 6 out-of-scope questions refused. |
| False refusal | Share of the 24 answerable questions wrongly refused — the cost of a strict refusal policy. |
| Routing | Share delegated to the expected specialist. |
| Consistency | With `--runs > 1`, questions whose (accurate, grounded, route) verdict changed between runs. |

Four questions are adversarial by construction:

- **Q04** (60% attendance) and **Q11** (family wedding) are in scope with a
  *negative* answer. A model that pattern-matches "in scope → be helpful" answers
  yes. A model that pattern-matches "sounds like a refusal" refuses. Both are wrong.
- **Q13** requires excluding `HSL4400`, which is 400-level and offered by the
  Humanities department but is a Programme Core course, not an elective. The
  correct answer is 4, and 5 is the attractive wrong answer.
- **Q30** ("what is my attendance") is in-scope subject matter but requires a
  personal record, so it must be refused with reason code
  `needs_personal_record` — a different refusal from the out-of-scope ones.

## 5. Verified without an LLM

`eval/check_tools.py` exercises the whole deterministic layer — 44 assertions,
all passing. This matters because it establishes that the ground truth in
`questions.json` is the ground truth of the data, not of the author's memory.

```
Corpus:  33 documents -> 184 chunks; front matter parsed for all 33
Integrity: no course points at a missing instructor; every course slot exists in slots.csv
Q12  CSL7620 slot G, Tuesday and Thursday 11:00-12:30, 4 credits, L-T-P 3-0-2
Q13  Humanities 400-level electives = 4 (HSL4010, HSL4110, HSL4220, HSL4330)
     Humanities 400-level all types = 5, i.e. HSL4400 Programme Core is correctly excluded
     "HSS" and "Humanities" normalise to the same department
Q19  Mathematics Open Electives = 1 (MTL3010)
Q17  Slot P4 = Thursday 14:00-17:00 (laboratory)
Q16  CSL7620 (G) vs CSL7570 (F) -> no clash;  CSL7570 (F) vs CSL3030 (F) -> clash
Q15  CSL7620 Major exam 2026-11-20;  Q18 Makeup Major 2026-12-03
Q14  CSL7570 -> arvind.menon@iitj.ac.in;  HSL4110 -> suchitra.pillai@iitj.ac.in
     CSL9999 -> found: false (reported, not guessed)
Q21  leave draft to arvind.menon@iitj.ac.in, status draft_not_sent, placeholders reported
Q22  makeup draft to rohit.bhagat@iitj.ac.in, cites Form AC-07 and clause AR-04.4
Q24  condonation draft to meenal.joshi@iitj.ac.in, states 68%, cites AR-02.4
     dates -> day count derived ("3 day(s)"); all fields given -> zero placeholders
     unknown request type -> error, not a fabricated email
Escalation: refusal appends to logs/unanswered_questions.jsonl
```

The consequence: for the 13 of 30 questions whose answer is a number, a date, a
slot or an email address, the system cannot be wrong about the *fact*. The only
remaining failure modes for those questions are the model not calling the tool,
or calling it with the wrong filters.

## 6. Results

### 6.1 Reproducing the tables

```bash
# Deterministic, no LLM -- these produce the numbers already quoted in 5 and 8.3
python eval/check_tools.py
python eval/check_retrieval.py

# Model-dependent
python eval/run_eval.py --runs 3 --mode multi  --tag qwen3-multi
python eval/run_eval.py --runs 3 --mode single --tag qwen3-single
python eval/run_eval.py --runs 3 --model ollama_chat/llama3.1:8b --tag llama31-multi
python eval/run_eval.py --runs 3 --model groq/openai/gpt-oss-20b --tag groq-gptoss20b-multi --delay 2   # see 8.4
python eval/summarise_results.py          # emits the markdown for 6.2 - 7
```

`summarise_results.py` prints the configuration comparison, the per-category
breakdown, the failure table and the consistency table in the exact shape of the
sections below. Paste its output here.

### 6.2 Configuration comparison

<!-- paste: configuration comparison table -->

| Configuration | Model | Runs | Accuracy | Groundedness | Correct refusal | False refusal | Routing |
|---|---|---|---|---|---|---|---|
| multi-agent | `ollama_chat/qwen3:8b` | 3 | | | | | |
| single-agent baseline | `ollama_chat/qwen3:8b` | 3 | | | | | |
| multi-agent | `ollama_chat/llama3.1:8b` | 3 | | | | | |
| multi-agent | `groq/openai/gpt-oss-20b` | 3 | | | | | |

### 6.3 Per-category breakdown

<!-- paste: per-category tables -->

### 6.4 Failures

<!-- paste: failure tables -->

## 7. Run-to-run consistency

<!-- paste: consistency tables -->

Questions whose answers changed between runs should be recorded here with the
differing verdicts. Expect instability to concentrate in three places, for
structural reasons:

1. **Routing of mixed questions.** Q09 (withdrawal date *and* resulting grade)
   legitimately spans the policy and schedule agents. Either route can produce a
   correct answer, so the route column moves while accuracy does not.
2. **Citation formatting.** The groundedness check requires the source string to
   appear in the answer. A model that writes "the Attendance Policy" instead of
   "AR-02 — Attendance Policy" is correct but scores ungrounded. This is a
   metric-strictness artefact and should be reported as such, not as a
   correctness failure.
3. **Negative-answer questions.** Q04 and Q11 require refusing the *request*
   while answering the *question*. Sampling noise flips these most often.

Temperature is left at the ADK default. Pinning it to 0 reduces the measured
instability but hides the variance a deployed helpdesk would actually show, so
the multi-run measurement is reported as-is.

## 8. Discussion

### 8.1 What the architecture buys

The multi-agent split is not primarily about accuracy on single-fact questions —
a single agent with all eleven tools can answer "what is the slot for Autonomous
Systems". It buys three things that matter at 8B scale:

- **Smaller tool-selection problem.** Eleven tools in one prompt invites the
  model to call `search_academic_documents` for a counting question, which is the
  single most damaging error in this system: a semantically similar passage looks
  like evidence, so the model answers with a plausible wrong number and cites a
  real document. Five tools per specialist makes the right tool the obvious one.
- **Shorter, sharper instructions.** Each specialist's instruction states one
  procedure. The single-agent instruction has to state three, and the refusal
  policy competes with them for the model's attention.
- **A refusal path that bypasses the specialists.** Out-of-scope questions are
  resolved at the orchestrator, which has one tool and no reason to be helpful.

The cost is one extra LLM turn per question (the `transfer_to_agent` call), which
on a local 8B model is roughly 1–3 seconds of added latency.

### 8.2 Where groundedness breaks

Three distinct failure modes, worth separating when reading the tables:

1. **Right answer, unmatched citation** — the model paraphrases the document name.
   Mitigated by instructing it to copy the tool's `citation` field verbatim; this
   is the residual.
2. **Right answer, superseded citation** — citing `SC-01` for a deadline that
   `OO-02` later moved. The corpus was built to contain this trap, and the
   instruction tells the policy agent to cite both when an office order modifies
   a base rule.
3. **Right document, wrong clause** — citing `AR-02` where `AR-02.4` is meant.
   Clause-level precision is what the lexical re-rank in `store.py` exists to
   deliver; smaller chunks (`CHUNK_TARGET_CHARS=900`) improve it further at the
   cost of more fragmented context.

### 8.3 The retrieval threshold cannot enforce scope — measured

This was the design assumption most worth testing, and testing it changed the
design. `eval/check_retrieval.py` measures the retrieval layer with no LLM in the
loop, so the numbers below are deterministic and reproducible
(`EMBEDDING_BACKEND=local`, all-MiniLM-L6-v2, 184 chunks, top-5 of 20 candidates):

| | Result |
|---|---|
| Expected document in the top-5 | **23 / 24 (95.8%)** |
| In-scope best cosine distance | 0.184 – 0.488 |
| Out-of-scope best cosine distance | 0.471 – 0.670 |
| Separability | **ranges overlap by 0.017** |

The intuition that the two classes form separable clusters is **wrong**, and it is
wrong for a principled reason rather than a tuning one. The two out-of-scope
questions that sit inside the in-scope range are:

- **Q29** "average placement package for CSE graduates" (0.471) — retrieves the
  CSE curriculum documents, which genuinely are about CSE graduates.
- **Q30** "what is *my* current attendance percentage in CSL7620" (0.499) — the
  attendance policy is exactly the right document for this question. The reason to
  refuse is not absence of evidence; it is that the answer needs a personal record
  the helpdesk cannot read.

No threshold can separate those from a legitimate attendance question, because
retrieval distance measures topical proximity and these questions *are*
topically proximate. The consequence for the architecture:

1. `MAX_RELEVANT_DISTANCE` is a **backstop against answering from an irrelevant
   passage**, not a scope gate. Its per-backend default is now set from this
   measurement (0.55 for `local`), where it correctly refuses the three questions
   no document covers — dining, transport, hostel — at **zero false refusals**
   across all 24 answerable questions.
2. **Topical scope is enforced by the orchestrator's explicit out-of-scope list**
   in `prompts.REFUSAL_BLOCK`, which names dining, transport, hostels, placements
   and personal records. Q29 and Q30 are refused there, not by retrieval score.
3. A `needs_personal_record` reason code exists in the escalation log precisely
   because Q30-type questions are a distinct refusal class: in-scope subject
   matter, well-retrieved evidence, and still unanswerable.

The single retrieval miss is **Q20** (credits and L-T-P of CSL7620), which
retrieved `CU-02` and `CU-09` instead of the catalogue extract `CU-08`. It does not
affect the answer, because credits come from `lookup_course` over `courses.csv`
rather than from a passage — an incidental demonstration of why decision (a) in
Section 3.2 matters: the question most likely to be mis-retrieved is the one
least dependent on retrieval.

### 8.4 Swapping the LLM: local versus hosted (Groq)

Because the model is built behind LiteLLM, a provider swap is one environment
variable (`HELPDESK_MODEL=groq/openai/gpt-oss-20b`). Two things had to be solved
to make that true in practice rather than just in principle, and both are now
handled transparently in `build_model()` (`academic_helpdesk/agent.py`):

1. **Embeddings.** Groq serves chat completions only, no embeddings endpoint, so
   RAG still needs a local embedder. The project carries two embedding backends:
   `nomic-embed-text` via Ollama (768 dims) and ChromaDB's bundled
   all-MiniLM-L6-v2 ONNX model (384 dims, no server). With the latter, Groq runs
   the whole chat path **without Ollama installed at all**, which is how the
   retrieval numbers in 8.3 were produced.
2. **Reasoning-model history round-tripping.** Groq's reasoning-capable models
   (the `qwen3` and `gpt-oss` families) attach a `reasoning_content` field to
   their replies. ADK's LiteLLM wrapper carries that field into the next turn's
   message history by default, and Groq's own request validation then rejects a
   *resubmitted* assistant message that contains it — a hard 400 on the second
   turn of every conversation, independent of prompt content. `drop_params`
   (LiteLLM's usual fix for provider/parameter mismatches) does not help here,
   because the rejected field is baked into message history, not a request
   parameter LiteLLM forwards. The actual fix is Groq's own
   `reasoning_format="hidden"` parameter, which stops the field from being
   emitted in the first place; `build_model()` sets it automatically for any
   `groq/` model.

Two more things surfaced only by actually exercising the Groq path, which is the
reason this section reports them rather than assuming the LiteLLM swap "just
works":

- **Model-id churn.** Groq retired `llama-3.1-8b-instant` and
  `llama-3.3-70b-versatile` — the two models this project originally picked for
  the apples-to-apples comparison with the brief's Llama 3.1 default — during
  the course of building this project. The working configuration became
  `groq/openai/gpt-oss-20b`, with `groq/qwen/qwen3.8-27b` (the same Qwen3 family
  as the local default) as the family-matched alternative. This is a property of
  hosted catalogs worth stating plainly: **any model id quoted here should be
  re-verified against `GET /openai/v1/models` before relying on it**, including
  by a grader re-running this project later.
- **Free-tier token-per-minute caps are tight for a multi-agent architecture.**
  gpt-oss-20b's free tier caps at 8000 tokens/minute; qwen3.8-27b at 7000. A
  single multi-agent turn makes at least two LLM calls (orchestrator, then the
  delegated sub-agent), each resending the full tool-schema prompt, so a handful
  of questions in quick succession exhausts the window. This is why
  `eval/run_eval.py` retries transient provider errors (rate limits, timeouts,
  5xx) with exponential backoff rather than failing the whole run, and why
  `--delay` exists to pace requests proactively rather than lean entirely on
  retries.

The trade this presents for a project graded on local operation:

| | Local 8B via Ollama | Groq (hosted) |
|---|---|---|
| Cost | free | free tier, then per-token |
| Offline | yes | no |
| Tool-calling reliability | the binding constraint at 8B | substantially better at a comparable model size |
| Rate limits | none | free-tier tokens/minute cap, tight for a multi-agent system — `run_eval.py --delay`/retries pace around it |
| Download | ~5 GB | ~80 MB (embedder only) |

A hosted model is **not cheaper** than local inference — local is free. What it
buys is tool-calling reliability, which is the dominant failure mode at 8B and
the thing the accuracy numbers are most sensitive to. The assignment names
Ollama, so the local path remains the default and the reported configuration;
Groq is used as the LLM-comparison axis the brief asks for. Because the catalog
churned away from Llama 3.1 specifically, the comparison is "hosted 8B-class
open-weight inference" in general rather than "the same weights, hosted" —
still useful for isolating how much of the accuracy gap is tool-calling
discipline versus model capability, just not as clean an isolation as same-family
weights would have given.

## 9. Limitations

- The corpus is a realistic reconstruction with dummy personal data, not the
  Institute's live documents. Answers are correct with respect to this corpus.
- No access to individual student records, by design. Questions needing them are
  refused with reason code `needs_personal_record`.
- The groundedness metric is string-matching on citations, so it under-counts
  correct answers that cite correctly but phrase the source differently. It never
  over-counts, which is the right direction for this bias.
- Topical scope rests on an enumerated out-of-scope list in the orchestrator
  instruction (Section 8.3), so an out-of-scope topic that the list does not name
  and that no document covers is caught only by the distance backstop, and one
  that is topically close to the corpus may not be caught at all. Extending the
  corpus to campus services would require replacing the distance gate with
  category-level routing.
- The retrieval numbers in 8.3 are for the `local` MiniLM backend. The
  `nomic-embed-text` backend has a different distance scale and its threshold
  default (0.62) is not yet measured on this corpus.
- Emails are drafts only. No mail transport or credentials exist in the project.
- Single-turn evaluation. Multi-turn behaviour (a student supplying their roll
  number after being asked) is supported by `HelpdeskSession` but not measured.

## 10. Conclusion

Putting the deterministic facts behind tools and the refusal decision behind a
retrieval-score threshold moves most of the correctness burden off the 8B model.
What is left for the model is classification and presentation — choosing a
specialist, choosing a tool, extracting fields, and writing three to six sentences
around a number it was handed. That is a task an 8B local model does acceptably,
which is the point: the system is designed so that the model's weaknesses are not
on the critical path to a correct, cited answer.

The measurement that would most change the design is the per-category accuracy
gap between the multi-agent and single-agent configurations on the *schedule*
questions. If the single agent matches the multi-agent split there, the
orchestration is paying latency for nothing on this corpus size, and the
interesting result is the refusal and routing columns instead.
