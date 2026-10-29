"""Single-point ESTIMATES of model results -- assumptions, NOT measurements.

    python eval/estimates.py

The model-answer evaluation (run_eval.py) had not completed when the report was
written. To show what a results table will look like, report/REPORT.tex (Section
"Single-point model estimates (not measured)") assumes an integer number of correct
answers per model and category and converts them to percentages as 100k/n.

These counts are illustrative assumptions. They are neither observed results nor
statistically calibrated predictions, and they do not establish a ranking of the
models. Every output carries ``measured = false`` / "estimated (not measured)", and
every chart says so in its title and footer.

The counts below are the ones printed in the report; keep the two in step. To replace
them with measurements, run run_eval.py and make_report_assets.py; measured values
always take precedence.

Writes eval/metrics/estimated_results.csv, estimated_results.json and three charts.
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
STATUS = "estimated (not measured)"

# Questions per category in eval/questions.json.
N = {"Rules & calendar": 11, "Timetable": 9, "Email": 5, "Must refuse": 5}
CATS = list(N)
TOTAL = sum(N.values())

# Assumed number of correct answers per model and category (illustrative).
CORRECT = {
    "Qwen3.8-27B": {"Rules & calendar": 8, "Timetable": 8, "Email": 5, "Must refuse": 4},
    "gpt-oss-120B": {"Rules & calendar": 9, "Timetable": 8, "Email": 5, "Must refuse": 4},
    "gpt-oss-20B": {"Rules & calendar": 7, "Timetable": 7, "Email": 4, "Must refuse": 4},
}
# Assumed answers that are both correct and correctly cited (of 30), and assumed number of
# questions whose verdict changes between repetitions.
GROUNDED = {"Qwen3.8-27B": 22, "gpt-oss-120B": 23, "gpt-oss-20B": 19}
CHANGES = {"Qwen3.8-27B": 3, "gpt-oss-120B": 2, "gpt-oss-20B": 5}


def pct(k: int, n: int) -> float:
    return round(100 * k / n, 1)


def model_total(model: str) -> int:
    return sum(CORRECT[model].values())


def write_tables() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    payload = {"measured": False, "status": STATUS,
               "note": "Illustrative assumed counts; not experimental results and not calibrated predictions.",
               "models": {}}
    for model, counts in CORRECT.items():
        for cat in CATS:
            rows.append([model, cat, N[cat], counts[cat], pct(counts[cat], N[cat]), STATUS])
        rows.append([model, "Overall", TOTAL, model_total(model), pct(model_total(model), TOTAL), STATUS])
        payload["models"][model] = {
            "assumed_correct": counts | {"Overall": model_total(model)},
            "accuracy_pct": {c: pct(counts[c], N[c]) for c in CATS} | {"Overall": pct(model_total(model), TOTAL)},
            "assumed_correct_and_cited_of_30": GROUNDED[model],
            "groundedness_pct": pct(GROUNDED[model], TOTAL),
            "assumed_questions_changing_between_runs": CHANGES[model],
        }
    with (OUT / "estimated_results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model", "category", "questions", "assumed_correct", "accuracy_pct", "status"])
        writer.writerows(rows)
    (OUT / "estimated_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def footer(fig) -> None:
    fig.text(0.04, 0.02, "ESTIMATES, NOT MEASUREMENTS: hypothetical correct-answer counts divided by question counts; "
             "no ranking is established.", fontsize=8.5, color=viz.CRIT, va="bottom")


def label_bars(ax, bars, values) -> None:
    for bar, value in zip(bars, values):
        ax.annotate(f"{value:g}%", (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8.5, color=viz.INK)


def chart_by_category() -> Path:
    fig, ax = viz.figure(10, 5.8, "Estimated accuracy by model and category",
                         "Illustrative assumed counts, not measured. Hatched bars mark estimates.")
    viz.style(ax)
    groups = CATS + ["Overall"]
    n = len(CORRECT)
    width = 0.8 / n
    for i, (model, counts) in enumerate(CORRECT.items()):
        vals = [pct(counts[c], N[c]) for c in CATS] + [pct(model_total(model), TOTAL)]
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        bars = ax.bar(xs, vals, width=width * 0.86, color=viz.SERIES[i], label=model, hatch="//",
                      edgecolor=viz.SURFACE, linewidth=0.6, zorder=3, alpha=0.9)
        label_bars(ax, bars, vals)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([f"{g}\n({N.get(g, TOTAL)})" for g in groups], color=viz.INK)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=n, frameon=False, fontsize=9.5, labelcolor=viz.INK_2)
    footer(fig)
    fig.subplots_adjust(top=0.80, bottom=0.17, left=0.07, right=0.97)
    path = CHARTS / "estimated_accuracy_by_category.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def chart_overall() -> Path:
    fig, ax = viz.figure(8.5, 5.6, "Estimated overall accuracy and groundedness",
                         "Illustrative assumed counts out of 30, not measured. Groundedness also requires correct citations.")
    viz.style(ax)
    models = list(CORRECT)
    for j, (label, colour, getter) in enumerate((("Accuracy", viz.SERIES[0], model_total),
                                                  ("Groundedness", viz.SERIES[1], GROUNDED.get))):
        vals = [pct(getter(m), TOTAL) for m in models]
        xs = [i + (j - 0.5) * 0.36 for i in range(len(models))]
        bars = ax.bar(xs, vals, width=0.32, color=colour, label=label, hatch="//", edgecolor=viz.SURFACE,
                      linewidth=0.6, zorder=3, alpha=0.9)
        label_bars(ax, bars, vals)
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, color=viz.INK)
    ax.set_ylim(0, 105)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=9.5, labelcolor=viz.INK_2)
    footer(fig)
    fig.subplots_adjust(top=0.80, bottom=0.17, left=0.08, right=0.97)
    path = CHARTS / "estimated_overall.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def shade(value: float) -> str:
    return "#bfe6bf" if value >= 90 else "#f6e8a6" if value >= 80 else "#f6cfa8" if value >= 70 else "#f1b9b9"


def chart_matrix() -> Path:
    fig, ax = viz.figure(9.8, 3.9, "Estimated accuracy matrix (assumed correct / questions)",
                         "Illustrative, not measured. Cell shading by percentage.")
    ax.set_facecolor(viz.SURFACE)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    cols = CATS + ["Overall"]
    for y, (model, counts) in enumerate(CORRECT.items()):
        cells = [(counts[c], N[c]) for c in CATS] + [(model_total(model), TOTAL)]
        for x, (k, n) in enumerate(cells):
            ax.add_patch(plt.Rectangle((x + 0.03, y + 0.05), 0.94, 0.9, color=shade(pct(k, n)), zorder=2))
            ax.text(x + 0.5, y + 0.5, f"{k}/{n}  ({pct(k, n):g}%)", ha="center", va="center", fontsize=10.5,
                    color=viz.INK, zorder=3)
    ax.set_xlim(0, len(cols))
    ax.set_ylim(len(CORRECT), 0)
    ax.set_xticks([x + 0.5 for x in range(len(cols))])
    ax.set_xticklabels([f"{c}\n({N.get(c, TOTAL)})" for c in cols], fontsize=9, color=viz.INK_2)
    ax.xaxis.tick_top()
    ax.set_yticks([y + 0.5 for y in range(len(CORRECT))])
    ax.set_yticklabels(list(CORRECT), fontsize=10, color=viz.INK)
    ax.legend(handles=[Patch(color="#bfe6bf", label=">= 90%"), Patch(color="#f6e8a6", label="80-89%"),
                       Patch(color="#f6cfa8", label="70-79%"), Patch(color="#f1b9b9", label="< 70%")],
              loc="lower center", ncol=4, frameon=False, fontsize=8.5, labelcolor=viz.INK_2, bbox_to_anchor=(0.5, -0.22))
    fig.text(0.04, 0.02, "ESTIMATES, NOT MEASUREMENTS.", fontsize=8.5, color=viz.CRIT, va="bottom")
    fig.subplots_adjust(top=0.70, bottom=0.2, left=0.16, right=0.98)
    path = CHARTS / "estimated_matrix.png"
    fig.savefig(path, facecolor=viz.SURFACE)
    plt.close(fig)
    return path


def main() -> int:
    payload = write_tables()
    CHARTS.mkdir(parents=True, exist_ok=True)
    made = [chart_by_category(), chart_overall(), chart_matrix()]
    print(f"[{STATUS}]")
    for model, d in payload["models"].items():
        print(f"  {model:<14} accuracy {d['assumed_correct']['Overall']}/30 = {d['accuracy_pct']['Overall']}%  "
              f"grounded {d['assumed_correct_and_cited_of_30']}/30 = {d['groundedness_pct']}%  "
              f"changes {d['assumed_questions_changing_between_runs']}")
    print("wrote estimated_results.csv, estimated_results.json,", ", ".join(p.name for p in made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
