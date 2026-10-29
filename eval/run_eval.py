"""Evaluation harness for the Academic Helpdesk.

Metrics
-------
accuracy        answerable questions whose answer contains the required facts and
                none of the forbidden ones; refusal questions that were refused.
groundedness    answers that cite at least one of the expected sources and cite
                no document identifier that does not exist in the corpus.
refusal         correct refusals on out-of-scope questions, and the false-refusal
                rate on answerable ones.
routing         share of questions delegated to the expected specialist agent.
consistency     with --runs > 1, the questions whose verdict changed between runs.

Usage
-----
    python eval/run_eval.py --runs 1
    python eval/run_eval.py --runs 3 --mode multi --model ollama_chat/qwen3:8b
    python eval/run_eval.py --mode single --tag baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from academic_helpdesk import config  # noqa: E402
from academic_helpdesk.rag import store  # noqa: E402
from academic_helpdesk.runner import HelpdeskSession, Turn  # noqa: E402

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

# Document ids in this corpus are slugs such as "reg_2019" or "amend_attendance_2024".
SLUG_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")
CSV_RE = re.compile(r"\b(?:courses|faculty|timetable)\.csv\b")
# Snake_case words that are not document ids (tool and field names, status values).
NOT_A_DOC = {"draft_not_sent", "course_code", "match_count", "sick_leave", "makeup_exam"}

REFUSAL_MARKERS = (
    "i do not know",
    "i don't know",
    "do not know",
    "cannot answer",
    "can't answer",
    "outside what the academic helpdesk",
    "outside the scope",
    "not covered by",
    "unable to answer",
    "no access",
    "cannot access",
)


def known_doc_ids() -> set[str]:
    """Every doc_id present in the loaded vector store."""
    metas = store.get_collection().get(include=["metadatas"])["metadatas"]
    return {m["doc_id"] for m in metas if m.get("doc_id")}


def sources_section(answer: str) -> str:
    match = re.search(r"sources?:(.*)$", answer, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


def _norm(text: str) -> str:
    """Lower-case and fold typographic variants (no-break spaces, special hyphens, dashes)."""
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[‐-―−]", "-", text)
    return re.sub(r"\s+", " ", text)


def _contains(text: str, requirement) -> bool:
    low = _norm(text)
    if isinstance(requirement, list):
        return any(_norm(option) in low for option in requirement)
    return _norm(requirement) in low


def _is_refusal(text: str) -> bool:
    low = _norm(text)
    return any(marker in low for marker in REFUSAL_MARKERS)


def score(question: dict, turn, corpus_ids: set[str]) -> dict:
    answer = turn.answer or ""
    expected_sources = [s.lower() for s in question.get("groundedness_doc_ids", [])]
    wants_refusal = question["answer_type"] == "refusal"

    low_answer = answer.lower()
    cited_docs = {d for d in corpus_ids if d.lower() in low_answer}
    cited_csvs = {m.lower() for m in CSV_RE.findall(answer)}
    # A citation the corpus does not contain: a slug in the Sources list that is
    # neither a document id nor a known non-document name.
    known = {d.lower() for d in corpus_ids}
    hallucinated = sorted(
        {t for t in SLUG_RE.findall(sources_section(answer).lower()) if t not in known and t not in NOT_A_DOC}
    )

    refused = _is_refusal(answer)
    logged = "log_unanswered_question" in turn.tool_names

    if wants_refusal:
        accurate = refused and not turn.error
        grounded = refused and not cited_docs  # a refusal must not cite anything
        refusal_correct = refused
        false_refusal = False
    else:
        missing = [r for r in question.get("must_contain", []) if not _contains(answer, r)]
        forbidden = [r for r in question.get("must_not_contain", []) if _contains(answer, r)]
        if question.get("refusal_acceptable") and refused:
            # A question the corpus only partly answers: an honest refusal is correct.
            accurate = bool(answer) and not forbidden and not turn.error
        else:
            accurate = bool(answer) and not missing and not forbidden and not refused
        cited_any = any(
            src in cited_csvs or src.upper() in cited_docs or src.lower() in answer.lower()
            for src in expected_sources
        )
        grounded = accurate and (cited_any or (refused and bool(question.get("refusal_acceptable")))) and not hallucinated
        refusal_correct = False
        false_refusal = refused and not question.get("refusal_acceptable")
        missing_facts = missing
        forbidden_facts = forbidden

    result = {
        "id": question["id"],
        "category": question["category"],
        "answer_type": question["answer_type"],
        "question": question["question"],
        "answer": answer,
        "accurate": bool(accurate),
        "grounded": bool(grounded),
        "refused": refused,
        "refusal_correct": refusal_correct,
        "false_refusal": false_refusal,
        "logged_unanswered": logged,
        "cited_doc_ids": sorted(cited_docs),
        "cited_csvs": sorted(cited_csvs),
        "hallucinated_doc_ids": hallucinated,
        "retrieved_doc_ids": turn.retrieved_doc_ids,
        "expected_route": question.get("expected_route", ""),
        "actual_route": turn.delegated_to or "none",
        "route_correct": (turn.delegated_to or "none") == question.get("expected_route", ""),
        "tools_called": turn.tool_names,
        "error": turn.error,
    }
    if not wants_refusal:
        result["missing_facts"] = missing_facts
        result["forbidden_facts_present"] = forbidden_facts
    return result


def summarise(results: list[dict]) -> dict:
    answerable = [r for r in results if r["answer_type"] != "refusal"]
    refusals = [r for r in results if r["answer_type"] == "refusal"]

    def pct(numerator: int, denominator: int) -> float:
        return round(100.0 * numerator / denominator, 1) if denominator else 0.0

    by_category: dict[str, dict] = {}
    for category in sorted({r["category"] for r in results}):
        rows = [r for r in results if r["category"] == category]
        by_category[category] = {
            "n": len(rows),
            "accuracy_pct": pct(sum(r["accurate"] for r in rows), len(rows)),
            "groundedness_pct": pct(sum(r["grounded"] for r in rows), len(rows)),
            "routing_pct": pct(sum(r["route_correct"] for r in rows), len(rows)),
        }

    return {
        "n_questions": len(results),
        "accuracy_pct": pct(sum(r["accurate"] for r in results), len(results)),
        "groundedness_pct_answerable": pct(
            sum(r["grounded"] for r in answerable), len(answerable)
        ),
        "correct_refusal_pct": pct(sum(r["refusal_correct"] for r in refusals), len(refusals)),
        "false_refusal_pct": pct(sum(r["false_refusal"] for r in answerable), len(answerable)),
        "routing_pct": pct(sum(r["route_correct"] for r in results), len(results)),
        "hallucinated_citation_count": sum(len(r["hallucinated_doc_ids"]) for r in results),
        "unanswered_logged_on_refusal_pct": pct(
            sum(r["logged_unanswered"] for r in refusals), len(refusals)
        ),
        "error_count": sum(1 for r in results if r["error"]),
        "by_category": by_category,
    }


def consistency(runs: list[list[dict]]) -> dict:
    if len(runs) < 2:
        return {"runs": len(runs), "unstable_questions": []}

    verdicts: dict[str, list[tuple[bool, bool, str]]] = defaultdict(list)
    for run in runs:
        for row in run:
            verdicts[row["id"]].append((row["accurate"], row["grounded"], row["actual_route"]))

    unstable = []
    for qid, series in verdicts.items():
        if len(set(series)) > 1:
            unstable.append(
                {
                    "id": qid,
                    "accurate_per_run": [v[0] for v in series],
                    "grounded_per_run": [v[1] for v in series],
                    "route_per_run": [v[2] for v in series],
                }
            )
    unstable.sort(key=lambda u: u["id"])
    return {
        "runs": len(runs),
        "stable_pct": round(100.0 * (len(verdicts) - len(unstable)) / len(verdicts), 1),
        "unstable_questions": unstable,
    }


# Substrings that mark an error as worth retrying rather than recording. Hosted
# providers with free tiers (Groq especially) rate-limit a 90-question run, and
# losing the whole run to one 429 is the difference between an evaluation that
# completes overnight and one that never completes.
TRANSIENT_MARKERS = (
    "rate limit",
    "ratelimit",
    "429",
    "too many requests",
    "timeout",
    "timed out",
    "502",
    "503",
    "504",
    "529",
    "overloaded",
    "service unavailable",
    "connection reset",
    "connection error",
    "temporarily unavailable",
)


def is_transient(exc: BaseException) -> bool:
    blob = f"{type(exc).__name__} {exc}".lower()
    return any(marker in blob for marker in TRANSIENT_MARKERS)


async def ask_with_retry(
    question_text: str,
    mode: str,
    model: str | None,
    max_retries: int,
    label: str,
) -> Turn:
    """Ask once, retrying transient provider errors with exponential backoff.

    A fresh session per attempt keeps a half-finished turn from leaking into the
    retry. Non-transient errors are returned as a failed Turn immediately -- a
    malformed tool call is a result worth recording, not a thing to retry.
    """
    delay = 2.0
    for attempt in range(1, max_retries + 2):
        session = HelpdeskSession(mode=mode, model_name=model)
        try:
            return await session.ask(question_text)
        except Exception as exc:  # noqa: BLE001 - provider errors are opaque
            if not is_transient(exc) or attempt > max_retries:
                return Turn(error=f"{type(exc).__name__}: {exc}")
            wait = delay + random.uniform(0, 0.5 * delay)
            print(
                f"    {label} transient error ({type(exc).__name__}), "
                f"retry {attempt}/{max_retries} in {wait:.1f}s"
            )
            await asyncio.sleep(wait)
            delay = min(delay * 2, 60.0)
    return Turn(error="retries exhausted")


async def run_once(
    questions: list[dict],
    mode: str,
    model: str | None,
    corpus_ids: set[str],
    run_no: int,
    delay: float = 0.0,
    max_retries: int = 4,
    checkpoint=None,
) -> list[dict]:
    results = []
    for index, question in enumerate(questions, 1):
        label = f"run{run_no} {question['id']}"
        # A fresh session per question keeps the runs independent and stops an
        # earlier delegation from biasing the next route.
        turn = await ask_with_retry(
            question["question"], mode, model, max_retries, label
        )
        row = score(question, turn, corpus_ids)
        results.append(row)
        if checkpoint:
            checkpoint(results)  # an interrupted run keeps everything finished so far
        flag ="ERR " if turn.error else ("ok " if row["accurate"] else "MISS")
        print(
            f"  run{run_no} [{index:2d}/{len(questions)}] {question['id']} {flag} "
            f"route={row['actual_route']:<16} grounded={row['grounded']}"
            + (f"  {turn.error[:60]}" if turn.error else "")
        )
        if delay and index < len(questions):
            await asyncio.sleep(delay)
    return results


def write_report(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(label: str, summary: dict) -> None:
    print(f"\n=== {label} ===")
    for key in (
        "n_questions",
        "accuracy_pct",
        "groundedness_pct_answerable",
        "correct_refusal_pct",
        "false_refusal_pct",
        "routing_pct",
        "hallucinated_citation_count",
        "unanswered_logged_on_refusal_pct",
        "error_count",
    ):
        print(f"  {key:38s} {summary[key]}")
    print("  by category:")
    for category, stats in summary["by_category"].items():
        print(
            f"    {category:14s} n={stats['n']:2d}  acc={stats['accuracy_pct']:5.1f}  "
            f"grounded={stats['groundedness_pct']:5.1f}  routing={stats['routing_pct']:5.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Academic Helpdesk")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--mode", choices=["multi", "single"], default="multi")
    parser.add_argument("--model", default=None, help="LiteLLM model string")
    parser.add_argument("--limit", type=int, default=0, help="first N questions only")
    parser.add_argument("--only", default="", help="comma-separated question ids")
    parser.add_argument("--tag", default="", help="label for the output filename")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="seconds to wait between questions; use ~2-3 on a free hosted tier",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="retries per question on rate-limit/transient provider errors",
    )
    args = parser.parse_args()

    spec = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = spec["questions"]
    if args.only:
        wanted = {q.strip().upper() for q in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    corpus_ids = known_doc_ids()
    model_label = args.model or config.CHAT_MODEL
    print(
        f"Evaluating {len(questions)} questions | mode={args.mode} | model={model_label} "
        f"| runs={args.runs}"
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", model_label)
    partial_path = RESULTS_DIR / f"partial-{args.mode}-{safe}-{args.tag or 'run'}.json"

    runs: list[list[dict]] = []

    def checkpoint(current: list[dict]) -> None:
        write_report(
            partial_path,
            {
                "complete": False,
                "mode": args.mode,
                "model": model_label,
                "runs_planned": args.runs,
                "runs_finished": len(runs),
                "results": runs + [current],
            },
        )

    for run_no in range(1, args.runs + 1):
        runs.append(
            asyncio.run(
                run_once(
                    questions,
                    args.mode,
                    args.model,
                    corpus_ids,
                    run_no,
                    delay=args.delay,
                    max_retries=args.max_retries,
                    checkpoint=checkpoint,
                )
            )
        )

    summaries = [summarise(run) for run in runs]
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "model": model_label,
        "runs": args.runs,
        "question_set": spec["set_name"],
        "per_run_summary": summaries,
        "consistency": consistency(runs),
        "results": runs,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = f"-{args.tag}" if args.tag else ""
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "_", model_label)
    out_path = RESULTS_DIR / f"eval-{args.mode}-{safe_model}{tag}-{stamp}.json"
    write_report(out_path, payload)
    partial_path.unlink(missing_ok=True)  # the finished file supersedes the checkpoint

    for i, summary in enumerate(summaries, 1):
        print_summary(f"run {i} | {args.mode} | {model_label}", summary)

    if args.runs > 1:
        cons = payload["consistency"]
        print(f"\nConsistency over {cons['runs']} runs: {cons['stable_pct']}% stable")
        for item in cons["unstable_questions"]:
            print(
                f"  {item['id']}: accurate={item['accurate_per_run']} "
                f"grounded={item['grounded_per_run']} route={item['route_per_run']}"
            )

    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
