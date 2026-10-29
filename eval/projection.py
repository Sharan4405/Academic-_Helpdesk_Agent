"""PROJECTED model results -- expectations, NOT measurements.

    python eval/projection.py

The model-answer evaluation (run_eval.py) had not completed when the report was
written. This script records what that evaluation is *expected* to show, so the
expectation is explicit, reproducible and easy to compare against the real runs.

Nothing here was measured on a model. Every output says so: the CSV and JSON carry
``measured = false``, and every chart is titled "Projected" and hatched.

How the ranges were formed (details in report/REPORT.tex, Table "Basis of the projection"):
  * the evidence ceiling is MEASURED (eval/evidence_eval.py): no model can exceed the
    evidence it is given;
  * the share of that ceiling each model converts is a JUDGEMENT: highest for the
    largest model (gpt-oss-120b), lowest for the smallest (gpt-oss-20b), highest for
    tool-answered categories and lowest for questions that need a passage read and cited;
  * groundedness is expected 5 to 15 points below accuracy, because the scorer needs the
    exact document identifier in the answer.

Replace this file's numbers with measurements by running run_eval.py and
make_report_assets.py; if a measurement falls outside its range, revise the projection.

Writes eval/metrics/projected_results.csv, projected_results.json and three charts.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import make_report_assets as viz  # noqa: E402

OUT = HERE / "metrics"
CHARTS = OUT / "charts"

STATUS = "projected (not measured)"

# Questions per category in eval/questions.json.
N = {"Rules & calendar": 11, "Timetable": 9, "Email": 5, "Must refuse": 5}
CATS = list(N)

# Projected accuracy, percent, as (low, high).
MODELS = {
    "Qwen3.8-27B": {"Rules & calendar": (65, 80), "Timetable": (80, 95), "Email": (85, 100), "Must refuse": (80, 100)},
    "gpt-oss-120B": {"Rules & calendar": (70, 85), "Timetable": (85, 98), "Email": (90, 100), "Must refuse": (80, 100)},
    "gpt-oss-20B": {"Rules & calendar": (60, 75), "Timetable": (70, 90), "Email": (75, 95), "Must refuse": (60, 100)},
}
# Projected number of questions (of 30) whose verdict changes between repetitions.
CHANGES = {"Qwen3.8-27B": (2, 5), "gpt-oss-120B": (1, 4), "gpt-oss-20B": (3, 8)}
GROUNDED_DISCOUNT = (5, 15)  # points below accuracy


def overall(ranges: dict) -> tuple[int, int]:
    total = sum(N.values())
    low = sum(N[c] * ranges[c][0] for c in CATS) / total
    high = sum(N[c] * ranges[c][1] for c in CATS) / total
    return round(low), round(high)


def grounded(acc: tuple[int, int]) -> tuple[int, int]:
    return max(0, acc[0] - GROUNDED_DISCOUNT[1]), acc[1] - GROUNDED_DISCOUNT[0]


def write_tables() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, payload = [], {"measured": False, "status": STATUS, "models": {}}
    for model, ranges in MODELS.items():
        acc = overall(ranges)
        grd = grounded(acc)
        for cat in CATS:
            lo, hi = ranges[cat]
            rows.append([model, cat, N[cat], lo, hi, STATUS])
        rows.append([model, "Overall", sum(N.values()), acc[0], acc[1], STATUS])
        payload["models"][model] = {
            "accuracy_pct": {c: list(ranges[c]) for c in CATS} | {"Overall": list(acc)},
            "groundedness_pct_overall": list(grd),
            "questions_changing_between_runs": list(CHANGES[model]),
        }
    with (OUT / "projected_results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model", "category", "questions", "accuracy_low_pct", "accuracy_high_pct", "status"])
        writer.writerows(rows)
    (OUT / "projected_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def footer(fig) -> None:
    fig.text(0.04, 0.02, "PROJECTION, NOT A MEASUREMENT: ranges are expectations made before the model runs. "
             "Bars: range midpoint; whiskers: projected low-high.", fontsize=8.5, color=viz.CRIT, va="bottom")


def chart_by_category() -> Path:
    fig, ax = viz.figure(10, 5.8, "Projected accuracy by model and category",
                         "Expected, not measured. Hatched bars mark projected values.")
    viz.style(ax)
    groups = CATS + ["Overall"]
    n = len(MODELS)
    width = 0.8 / n
    for i, (model, ranges) in enumerate(MODELS.items()):
        pts = [ranges[c] for c in CATS] + [overall(ranges)]
        mids = [(lo + hi) / 2 for lo, hi in pts]
        errs = [(hi - lo) / 2 for lo, hi in pts]
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        ax.bar(xs, mids, width=width * 0.86, color=viz.SERIES[i], label=model, hatch="//", edgecolor=viz.SURFACE,
               linewidth=0.6, zorder=3, yerr=errs, error_kw={"ecolor": viz.INK_2, "elinewidth": 1.1, "capsize": 3}, alpha=0.9)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([f"{g}\n({N[g]})" if g in N else f"{g}\n({sum(N.values())})" for g in groups], color=viz.INK)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=n, frameon=False, fontsize=9.5, labelcolor=viz.INK_2)
    footer(fig)
    fig.subplots_adjust(top=0.80, bottom=0.17, left=0.07, right=0.97)
    path = CHARTS / "projected_accuracy_by_category.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def chart_overall() -> Path:
    fig, ax = viz.figure(8.5, 5.6, "Projected overall accuracy and groundedness",
                         "Expected, not measured. Groundedness is projected 5-15 points below accuracy.")
    viz.style(ax)
    models = list(MODELS)
    for j, (label, colour, getter) in enumerate((("Accuracy", viz.SERIES[0], overall),
                                                  ("Groundedness", viz.SERIES[1], lambda r: grounded(overall(r))))):
        pts = [getter(MODELS[m]) for m in models]
        xs = [i + (j - 0.5) * 0.36 for i in range(len(models))]
        ax.bar(xs, [(lo + hi) / 2 for lo, hi in pts], width=0.32, color=colour, label=label, hatch="//",
               edgecolor=viz.SURFACE, linewidth=0.6, zorder=3, alpha=0.9,
               yerr=[(hi - lo) / 2 for lo, hi in pts], error_kw={"ecolor": viz.INK_2, "elinewidth": 1.1, "capsize": 3})
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, color=viz.INK)
    ax.set_ylim(0, 105)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=9.5, labelcolor=viz.INK_2)
    footer(fig)
    fig.subplots_adjust(top=0.80, bottom=0.17, left=0.08, right=0.97)
    path = CHARTS / "projected_overall.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def shade(mid: float) -> str:
    return "#bfe6bf" if mid >= 90 else "#f6e8a6" if mid >= 80 else "#f6cfa8" if mid >= 70 else "#f1b9b9"


def chart_matrix() -> Path:
    fig, ax = viz.figure(9.5, 3.9, "Projected accuracy matrix (low-high %)",
                         "Expected, not measured. Cell shading by range midpoint.")
    ax.set_facecolor(viz.SURFACE)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    cols = CATS + ["Overall"]
    for y, (model, ranges) in enumerate(MODELS.items()):
        pts = [ranges[c] for c in CATS] + [overall(ranges)]
        for x, (lo, hi) in enumerate(pts):
            ax.add_patch(plt.Rectangle((x + 0.03, y + 0.05), 0.94, 0.9, color=shade((lo + hi) / 2), zorder=2))
            ax.text(x + 0.5, y + 0.5, f"{lo}-{hi}%", ha="center", va="center", fontsize=11, color=viz.INK, zorder=3)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(MODELS), 0)
    ax.set_xticks([x + 0.5 for x in range(len(cols))])
    ax.set_xticklabels([f"{c}\n({N[c] if c in N else sum(N.values())})" for c in cols], fontsize=9, color=viz.INK_2)
    ax.xaxis.tick_top()
    ax.set_yticks([y + 0.5 for y in range(len(MODELS))])
    ax.set_yticklabels(list(MODELS), fontsize=10, color=viz.INK)
    ax.legend(handles=[Patch(color="#bfe6bf", label=">= 90"), Patch(color="#f6e8a6", label="80-89"),
                       Patch(color="#f6cfa8", label="70-79"), Patch(color="#f1b9b9", label="< 70")],
              loc="lower center", ncol=4, frameon=False, fontsize=8.5, labelcolor=viz.INK_2,
              bbox_to_anchor=(0.5, -0.2), title="range midpoint", title_fontsize=8.5)
    fig.text(0.04, 0.02, "PROJECTION, NOT A MEASUREMENT.", fontsize=8.5, color=viz.CRIT, va="bottom")
    fig.subplots_adjust(top=0.70, bottom=0.2, left=0.16, right=0.98)
    path = CHARTS / "projected_matrix.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def main() -> int:
    payload = write_tables()
    CHARTS.mkdir(parents=True, exist_ok=True)
    made = [chart_by_category(), chart_overall(), chart_matrix()]
    print(f"[{STATUS}]")
    for model, d in payload["models"].items():
        a, g = d["accuracy_pct"]["Overall"], d["groundedness_pct_overall"]
        print(f"  {model:<14} accuracy {a[0]}-{a[1]}%  groundedness {g[0]}-{g[1]}%  "
              f"changes {d['questions_changing_between_runs'][0]}-{d['questions_changing_between_runs'][1]} of 30")
    print("wrote projected_results.csv, projected_results.json,", ", ".join(p.name for p in made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
