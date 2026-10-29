"""Model-free evaluation: does the agent get the evidence it needs, for every question?

    python eval/evidence_eval.py

For each of the 30 questions this runs the retrieval or tool step the agent depends
on -- exactly the code the agent calls -- and checks the output against the question's
required facts. It needs no chat model, so it is deterministic, instant and free.

What it measures is a CEILING, not a model score: if the facts a question needs are
not in the evidence handed to the model, no model can answer it correctly; if they are,
the model still has to use them. Model answers are scored separately by run_eval.py.

Writes eval/metrics/evidence_eval.csv, evidence_eval.json and two charts.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import make_report_assets as viz  # noqa: E402
from run_eval import _contains  # noqa: E402
from academic_helpdesk import config  # noqa: E402
from academic_helpdesk.tools.contact_tools import lookup_course_instructor  # noqa: E402
from academic_helpdesk.tools.email_tools import draft_student_email  # noqa: E402
from academic_helpdesk.tools.rag_tools import search_academic_documents  # noqa: E402
from academic_helpdesk.tools.schedule_tools import (  # noqa: E402
    check_slot_clash,
    find_courses,
    get_slot_timing,
    lookup_course,
)

OUT = HERE / "metrics"
CHARTS = OUT / "charts"

PASS, PARTIAL, FAIL, NA = "pass", "partial", "fail", "na"


def blob(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def draft(kind, code, **kw):
    a = dict(reason="", from_date="", to_date="", days=0, exam_type="", exam_date="", attendance="")
    a.update(kw)
    return draft_student_email(
        kind, code, a["reason"], a["from_date"], a["to_date"], a["days"],
        a["exam_type"], a["exam_date"], a["attendance"], "", "", "", "",
    )


# The tool call a correct agent makes for each CSV or email question, and what its
# result must show. Arguments are what the agent's instructions lead it to pass.
def tool_cases() -> dict:
    return {
        "Q12": (lambda: lookup_course("Autonomous Systems"),
                lambda r: "IDL4010" in blob(r) and "11:00" in blob(r)),
        "Q13": (lambda: find_courses("Humanities", 400, "elective", ""),
                lambda r: r["match_count"] == 7 and "HSL4110" in blob(r)),
        "Q14": (lambda: lookup_course("CSL7570"),
                lambda r: "Sidharth Ranjan" in blob(r) and r["matches"][0]["slot"] == "F"),
        "Q15": (lambda: find_courses("Computer Science and Engineering", 400, "", ""),
                lambda r: r["match_count"] == 9 and "CSL4100" in blob(r)),
        "Q16": (lambda: check_slot_clash("HSL4010", "HSL4070"), lambda r: r["clash"] is True),
        "Q17": (lambda: get_slot_timing("A"), lambda r: "09:00" in blob(r) and "Monday" in blob(r)),
        "Q18": (lambda: get_slot_timing("G"), lambda r: r["course_count"] == 7),
        "Q19": (lambda: lookup_course("Computational Game Theory"),
                lambda r: r["matches"][0]["credits"] == 3 and r["matches"][0]["room"] == "LHC 204"),
        "Q20": (lambda: find_courses("Electrical Engineering", 0, "", ""),
                lambda r: r["match_count"] == 3 and "EEL4010" in blob(r)),
        "Q21": (lambda: draft("sick_leave", "CSL7570", days=2),
                lambda r: r["to"] == "sranjan@iitj.ac.in" and "CSL7570" in r["subject"] and r["status"] == "draft_not_sent"),
        "Q22": (lambda: draft("makeup_exam", "CSL4100", exam_type="Major", exam_date="2026-11-20", reason="illness"),
                lambda r: r["to"] == "romibanerjee@iitj.ac.in" and "20 November 2026" in r["body"]),
        "Q23": (lambda: draft("attendance_condonation", "IDL4010", attendance="68%", reason="illness"),
                lambda r: r["to"] == "anoopj@iitj.ac.in" and "68%" in r["body"]),
        "Q24": (lambda: draft("sick_leave", "HSL4010", from_date="2026-08-03", to_date="2026-08-05"),
                lambda r: r["to"] == "hari@iitj.ac.in" and "03 August 2026" in r["body"] and "05 August 2026" in r["body"]),
        "Q25": (lambda: lookup_course_instructor("ECL4010"),
                lambda r: r["instructor_email"] == "srivatsa@iitj.ac.in"),
    }


def evaluate(questions: list[dict]) -> list[dict]:
    tools = tool_cases()
    rows = []
    for q in questions:
        row = {"id": q["id"], "category": q["category"], "question": q["question"],
               "evidence_found": NA, "facts_present": NA, "verdict_correct": NA, "note": ""}
        expected_docs = [d for d in q["groundedness_doc_ids"] if not d.endswith(".csv")]

        if q["id"] in tools:  # CSV / email questions: the tool is the evidence
            call, check = tools[q["id"]]
            try:
                result = call()
                ok = bool(check(result))
            except Exception as exc:  # a tool that crashes is a failure, with the reason kept
                ok, row["note"] = False, f"{type(exc).__name__}: {exc}"
            row["evidence_found"] = row["facts_present"] = PASS if ok else FAIL
        elif q["answer_type"] == "refusal":  # out of scope: the evidence check should say "no"
            result = search_academic_documents(q["question"], "")
            if result["sufficient_evidence"]:
                row["verdict_correct"] = PARTIAL
                row["note"] = "evidence check passes; refusal relies on the orchestrator's scope rule"
            else:
                row["verdict_correct"] = PASS
        else:  # document questions: retrieval, then the passages the model would see
            result = search_academic_documents(q["question"], "")
            hits = result["results"]
            retrieved = [h["doc_id"] for h in hits]
            text = " ".join(h["passage"] for h in hits)
            row["evidence_found"] = PASS if any(d in retrieved for d in expected_docs) else FAIL
            facts = all(_contains(text, req) for req in q.get("must_contain", []))
            if q.get("refusal_acceptable"):
                row["facts_present"] = PARTIAL
                row["note"] = "limit case: the corpus does not state this; an honest 'not specified' is correct"
            else:
                row["facts_present"] = PASS if facts else FAIL
            row["verdict_correct"] = PASS if result["sufficient_evidence"] else FAIL
        rows.append(row)
    return rows


# ------------------------------------------------------------------ summaries
def share(rows: list[dict], key: str) -> tuple[float, int]:
    scored = [r for r in rows if r[key] != NA]
    good = sum(1 for r in scored if r[key] == PASS)
    return (round(100 * good / len(scored), 1) if scored else 0.0, len(scored))


def summarise(rows: list[dict]) -> dict:
    out = {"overall": {}, "by_category": {}}
    for key in ("evidence_found", "facts_present", "verdict_correct"):
        out["overall"][key] = dict(zip(("pct", "n"), share(rows, key)))
    for cat in sorted({r["category"] for r in rows}):
        sub = [r for r in rows if r["category"] == cat]
        out["by_category"][cat] = {k: dict(zip(("pct", "n"), share(sub, k)))
                                   for k in ("evidence_found", "facts_present", "verdict_correct")}
    return out


# ---------------------------------------------------------------------- charts
STATUS = {PASS: (viz.GOOD, "✓"), PARTIAL: (viz.WARN, "~"), FAIL: (viz.CRIT, "✕"), NA: (viz.NEUTRAL, "–")}
COLS = [("evidence_found", "Right document\nor record found"),
        ("facts_present", "Required facts\nin the evidence"),
        ("verdict_correct", "Evidence verdict\nright (answer / refuse)")]
CATS = ["policy", "schedule", "email", "out_of_scope"]


def chart_summary(summary: dict) -> Path:
    fig, ax = viz.figure(10, 5.6, "What the agent is given, by question category",
                         "Share of questions whose evidence is right; no model involved. Each category shows the checks that apply.")
    viz.style(ax)
    n = len(COLS)
    width = 0.8 / n
    for i, (key, label) in enumerate(COLS):
        xs, vals = [], []
        for g, cat in enumerate(CATS):
            cell = summary["by_category"][cat][key]
            if cell["n"]:
                xs.append(g + (i - (n - 1) / 2) * width)
                vals.append(cell["pct"])
        bars = ax.bar(xs, vals, width=width * 0.86, color=viz.SERIES[i], label=label.replace("\n", " "), zorder=3)
        for bar, v in zip(bars, vals):
            ax.annotate(f"{v:.0f}%", (bar.get_x() + bar.get_width() / 2, v), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom", fontsize=9, color=viz.INK)
    counts = {c: max(summary["by_category"][c][k]["n"] for k, _ in COLS) for c in CATS}
    names = {"policy": "Rules & calendar", "schedule": "Timetable", "email": "Email", "out_of_scope": "Must refuse"}
    ax.set_xticks(range(len(CATS)))
    ax.set_xticklabels([f"{names[c]}\n({counts[c]})" for c in CATS], color=viz.INK)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3, frameon=False, fontsize=9.5,
              labelcolor=viz.INK_2, handlelength=1.2)
    fig.subplots_adjust(top=0.82, bottom=0.14, left=0.07, right=0.97)
    path = CHARTS / "evidence_by_category.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def chart_grid(rows: list[dict]) -> Path:
    fig, ax = viz.figure(8.6, 11.2, "Evidence check for every question",
                         "Model-free: does the retrieval or tool step hand over what the question needs?")
    ax.set_facecolor(viz.SURFACE)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    for x, (key, _) in enumerate(COLS):
        for y, r in enumerate(rows):
            colour, mark = STATUS[r[key]]
            ax.add_patch(plt.Rectangle((x + 0.04, y + 0.06), 0.92, 0.88, color=colour, zorder=2))
            ax.text(x + 0.5, y + 0.52, mark, ha="center", va="center", fontsize=9, zorder=3,
                    color=viz.INK if colour in (viz.WARN, viz.NEUTRAL) else "white", fontweight="bold")
    ax.set_xlim(0, len(COLS))
    ax.set_ylim(len(rows), 0)
    ax.set_xticks([x + 0.5 for x in range(len(COLS))])
    ax.set_xticklabels([label for _, label in COLS], fontsize=8.5, color=viz.INK_2)
    ax.xaxis.tick_top()
    ax.set_yticks([y + 0.5 for y in range(len(rows))])
    ax.set_yticklabels([f"{r['id']}  {r['category'].replace('_', ' ')}" for r in rows], fontsize=8.5, color=viz.INK_2)
    previous = None
    for y, r in enumerate(rows):
        if previous and r["category"] != previous:
            ax.axhline(y, color=viz.SURFACE, linewidth=5, zorder=4)
        previous = r["category"]
    fig.legend(handles=[Patch(color=viz.GOOD, label="✓ yes"), Patch(color=viz.WARN, label="~ depends on the model / limit case"),
                        Patch(color=viz.CRIT, label="✕ no"), Patch(color=viz.NEUTRAL, label="– not applicable")],
               loc="lower center", ncol=4, frameon=False, fontsize=9, labelcolor=viz.INK_2, bbox_to_anchor=(0.5, 0.005))
    fig.subplots_adjust(top=0.86, bottom=0.07, left=0.24, right=0.97)
    path = CHARTS / "evidence_grid.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def main() -> int:
    spec = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    rows = evaluate(spec["questions"])
    summary = summarise(rows)

    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    with (OUT / "evidence_eval.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "evidence_eval.json").write_text(
        json.dumps({"question_set": spec["set_name"], "corpus": config.CORPUS_SOURCE, "summary": summary, "rows": rows},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    made = [chart_summary(summary), chart_grid(rows)]

    print(f"{'Q':<5}{'category':<14}{'found':<9}{'facts':<9}{'verdict':<9}note")
    for r in rows:
        print(f"{r['id']:<5}{r['category']:<14}{r['evidence_found']:<9}{r['facts_present']:<9}{r['verdict_correct']:<9}{r['note']}")
    print("\noverall:", {k: f"{v['pct']}% of {v['n']}" for k, v in summary["overall"].items()})
    print("wrote", ", ".join(p.name for p in made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
