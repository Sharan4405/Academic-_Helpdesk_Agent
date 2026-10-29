"""Turn evaluation result files into publishable metrics and charts.

    python eval/make_report_assets.py                  # newest result per model+mode
    python eval/make_report_assets.py a.json b.json    # specific result files

Writes to eval/metrics/:
    summary.csv         one row per configuration, metrics averaged over its runs
    metrics_per_run.csv one row per configuration and run
    per_question.csv    every question, run and configuration, with the verdicts
    consistency.csv     questions whose verdict changed between runs
    metrics.json        everything above, machine-readable
    charts/*.png        overall metrics, accuracy by category, per-question grid

Charts follow the project's palette rules: categorical hues in a fixed order
(blue, orange, aqua -- validated for colour-blind separation), status marks that
carry a symbol as well as a colour, direct value labels, recessive grid.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = Path(__file__).parent
RESULTS = HERE / "results"
OUT = HERE / "metrics"
CHARTS = OUT / "charts"

# Surface and ink (reference palette, light mode).
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
# Categorical slots 1-3, in fixed order; validated all-pairs for colour-blind separation.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
# Status colours (fixed): always paired with a symbol.
GOOD, WARN, CRIT, NEUTRAL = "#0ca30c", "#fab219", "#d03b3b", "#c3c2b7"

METRICS = [
    ("accuracy_pct", "Accuracy"),
    ("groundedness_pct_answerable", "Groundedness"),
    ("correct_refusal_pct", "Correct refusal"),
    ("routing_pct", "Routing"),
]
CATEGORY_LABELS = {
    "policy": "Rules & calendar\n(11)",
    "schedule": "Timetable\n(9)",
    "email": "Email\n(5)",
    "out_of_scope": "Must refuse\n(5)",
}
MODEL_NAMES = {"qwen/qwen3.8-27b": "Qwen3.8 27B", "openai/gpt-oss-20b": "gpt-oss 20B"}


def model_name(model: str) -> str:
    return MODEL_NAMES.get(model.split("/", 1)[-1] if model.startswith("groq/") else model, model)


def label_of(payload: dict) -> str:
    base = f"{model_name(payload['model'])} · {payload['mode']}-agent"
    return f"{base} [partial: {payload['answered']} answered]" if payload.get("partial") else base


def load(paths: list[Path]) -> list[dict]:
    payloads = []
    for p in paths:
        payload = {"path": p, **json.loads(p.read_text(encoding="utf-8"))}
        if "per_run_summary" not in payload:  # a checkpoint from a run still in progress
            from run_eval import consistency, summarise

            runs = [r for r in payload["results"] if r]
            payload.update(
                partial=True,
                answered=sum(len(r) for r in runs),
                runs=len(runs),
                per_run_summary=[summarise(r) for r in runs],
                consistency=consistency(runs),
                results=runs,
                timestamp=payload.get("timestamp", "9999"),
            )
        payloads.append(payload)
    newest: dict[str, dict] = {}
    for payload in sorted(payloads, key=lambda p: p["timestamp"]):
        newest[label_of(payload)] = payload  # later runs of the same configuration win
    # stable, meaningful order: multi-agent first, then by model name
    return sorted(newest.values(), key=lambda p: (p["mode"] != "multi", label_of(p)))


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 1) if values else 0.0


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


# --------------------------------------------------------------------- tables
def build_tables(payloads: list[dict]) -> dict:
    summary, per_run, per_question, consistency = [], [], [], []
    metric_keys = [k for k, _ in METRICS] + [
        "false_refusal_pct",
        "hallucinated_citation_count",
        "unanswered_logged_on_refusal_pct",
        "error_count",
    ]
    for payload in payloads:
        label = label_of(payload)
        runs = payload["per_run_summary"]
        summary.append(
            {
                "configuration": label,
                "model": payload["model"],
                "mode": payload["mode"],
                "runs": payload["runs"],
                "questions": runs[0]["n_questions"],
                **{k: mean([r[k] for r in runs]) for k in metric_keys},
                "accuracy_min": min(r["accuracy_pct"] for r in runs),
                "accuracy_max": max(r["accuracy_pct"] for r in runs),
                "by_category": {
                    c: {
                        "n": runs[0]["by_category"][c]["n"],
                        "accuracy_pct": mean([r["by_category"][c]["accuracy_pct"] for r in runs]),
                        "groundedness_pct": mean([r["by_category"][c]["groundedness_pct"] for r in runs]),
                        "routing_pct": mean([r["by_category"][c]["routing_pct"] for r in runs]),
                    }
                    for c in runs[0]["by_category"]
                },
            }
        )
        for i, run in enumerate(runs, 1):
            per_run.append({"configuration": label, "run": i, **{k: run[k] for k in metric_keys}})
        for i, rows in enumerate(payload["results"], 1):
            for r in rows:
                per_question.append(
                    {
                        "configuration": label,
                        "run": i,
                        "id": r["id"],
                        "category": r["category"],
                        "accurate": r["accurate"],
                        "grounded": r["grounded"],
                        "refused": r["refused"],
                        "route_correct": r["route_correct"],
                        "expected_route": r["expected_route"],
                        "actual_route": r["actual_route"],
                        "logged_unanswered": r["logged_unanswered"],
                        "invented_citations": ";".join(r["hallucinated_doc_ids"]),
                        "tools_called": ";".join(r["tools_called"]),
                        "error": r["error"],
                    }
                )
        for item in payload["consistency"].get("unstable_questions", []):
            consistency.append(
                {
                    "configuration": label,
                    "id": item["id"],
                    "accurate_per_run": item["accurate_per_run"],
                    "grounded_per_run": item["grounded_per_run"],
                    "route_per_run": item["route_per_run"],
                }
            )
    return {
        "summary": summary,
        "per_run": per_run,
        "per_question": per_question,
        "consistency": consistency,
    }


def write_tables(tables: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    flat_cols = [
        "configuration", "model", "mode", "runs", "questions", "accuracy_pct",
        "groundedness_pct_answerable", "correct_refusal_pct", "false_refusal_pct",
        "routing_pct", "hallucinated_citation_count", "unanswered_logged_on_refusal_pct",
        "error_count", "accuracy_min", "accuracy_max",
    ]
    write_csv(OUT / "summary.csv", flat_cols, [[s[c] for c in flat_cols] for s in tables["summary"]])
    run_cols = list(tables["per_run"][0].keys())
    write_csv(OUT / "metrics_per_run.csv", run_cols, [[r[c] for c in run_cols] for r in tables["per_run"]])
    q_cols = list(tables["per_question"][0].keys())
    write_csv(OUT / "per_question.csv", q_cols, [[r[c] for c in q_cols] for r in tables["per_question"]])
    write_csv(
        OUT / "consistency.csv",
        ["configuration", "id", "accurate_per_run", "grounded_per_run", "route_per_run"],
        [[c["configuration"], c["id"], c["accurate_per_run"], c["grounded_per_run"], c["route_per_run"]]
         for c in tables["consistency"]],
    )
    (OUT / "metrics.json").write_text(json.dumps(tables, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------- charts
def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, length=0, labelsize=10)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def figure(width: float, height: float, title: str, subtitle: str):
    fig, ax = plt.subplots(figsize=(width, height), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.04, 0.965, title, fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.915, subtitle, fontsize=10, color=INK_2, va="top")
    return fig, ax


def grouped_bars(ax, groups: list[str], series: list[tuple[str, list[float]]]) -> None:
    n = len(series)
    width = 0.8 / n
    for i, (name, values) in enumerate(series):
        xs = [g + (i - (n - 1) / 2) * width for g in range(len(groups))]
        bars = ax.bar(xs, values, width=width * 0.86, color=SERIES[i], label=name, zorder=3)
        for bar, value in zip(bars, values):
            ax.annotate(
                f"{value:.0f}%" if value == int(value) else f"{value:.1f}%",
                (bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 3), textcoords="offset points",
                ha="center", va="bottom", fontsize=9, color=INK,
            )
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups, color=INK)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{t}%" for t in (0, 25, 50, 75, 100)])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=n, frameon=False,
              fontsize=9.5, labelcolor=INK_2, handlelength=1.2)


def legend_name(summary: dict) -> str:
    return f"{summary['configuration']} ({summary['runs']} run{'s' if summary['runs'] > 1 else ''})"


def chart_overall(summaries: list[dict]) -> Path:
    fig, ax = figure(
        10, 5.6, "Evaluation results by configuration",
        "30 questions per run; each bar is the mean over that configuration's runs.",
    )
    style(ax)
    grouped_bars(
        ax,
        [lbl for _, lbl in METRICS],
        [(legend_name(s), [s[k] for k, _ in METRICS]) for s in summaries],
    )
    fig.subplots_adjust(top=0.82, bottom=0.10, left=0.07, right=0.97)
    path = CHARTS / "overall_metrics.png"
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def chart_categories(summaries: list[dict]) -> Path:
    cats = [c for c in CATEGORY_LABELS if c in summaries[0]["by_category"]]
    fig, ax = figure(
        10, 5.6, "Accuracy by question category",
        "Share of questions answered correctly (mean over runs); question counts in brackets.",
    )
    style(ax)
    grouped_bars(
        ax,
        [CATEGORY_LABELS[c] for c in cats],
        [(legend_name(s), [s["by_category"][c]["accuracy_pct"] for c in cats]) for s in summaries],
    )
    fig.subplots_adjust(top=0.82, bottom=0.14, left=0.07, right=0.97)
    path = CHARTS / "accuracy_by_category.png"
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def chart_grid(payloads: list[dict]) -> Path:
    columns = []  # (header, rows keyed by id)
    for payload in payloads:
        for i, rows in enumerate(payload["results"], 1):
            suffix = f" · run {i}" if payload["runs"] > 1 else ""
            columns.append((f"{label_of(payload)}{suffix}", {r["id"]: r for r in rows}))
    ids = sorted({qid for _, rows in columns for qid in rows})
    category = {r["id"]: r["category"] for _, rows in columns for r in rows.values()}

    fig, ax = figure(
        max(8.0, 2.0 + 1.35 * len(columns)), 11.2, "Result for every question",
        "One column per run. A mark and a colour for each verdict, so nothing relies on colour alone.",
    )
    ax.set_facecolor(SURFACE)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)

    def verdict(row):
        if row is None:
            return NEUTRAL, "–"
        if row["error"]:
            return NEUTRAL, "!"
        if row["accurate"] and row["grounded"]:
            return GOOD, "✓"
        if row["accurate"]:
            return WARN, "~"
        return CRIT, "✕"

    for x, (_, rows) in enumerate(columns):
        for y, qid in enumerate(ids):
            colour, mark = verdict(rows.get(qid))
            ax.add_patch(plt.Rectangle((x + 0.04, y + 0.06), 0.92, 0.88, color=colour, zorder=2))
            ax.text(x + 0.5, y + 0.52, mark, ha="center", va="center", fontsize=9,
                    color=INK if colour in (WARN, NEUTRAL) else "white", fontweight="bold", zorder=3)

    ax.set_xlim(0, len(columns))
    ax.set_ylim(len(ids), 0)
    ax.set_xticks([x + 0.5 for x in range(len(columns))])
    ax.set_xticklabels([h.replace(" · ", "\n", 1).replace(" · run", "\nrun") for h, _ in columns],
                       fontsize=8.5, color=INK_2)
    ax.xaxis.tick_top()
    ax.set_yticks([y + 0.5 for y in range(len(ids))])
    ax.set_yticklabels([f"{qid}  {category[qid].replace('_', ' ')}" for qid in ids], fontsize=8.5, color=INK_2)
    previous = None
    for y, qid in enumerate(ids):  # separators between categories
        if previous and category[qid] != previous:
            ax.axhline(y, color=SURFACE, linewidth=5, zorder=4)
        previous = category[qid]

    fig.legend(
        handles=[
            Patch(color=GOOD, label="✓ correct and cited"),
            Patch(color=WARN, label="~ correct, citation not matched"),
            Patch(color=CRIT, label="✕ wrong"),
            Patch(color=NEUTRAL, label="! error"),
        ],
        loc="lower center", ncol=4, frameon=False, fontsize=9, labelcolor=INK_2,
        bbox_to_anchor=(0.5, 0.005),
    )
    fig.subplots_adjust(top=0.84, bottom=0.07, left=0.20, right=0.98)
    path = CHARTS / "per_question_grid.png"
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def main() -> int:
    # finished results; if none yet, fall back to the checkpoints of runs in progress
    paths = [Path(a) for a in sys.argv[1:]] or sorted(RESULTS.glob("eval-*.json")) or sorted(RESULTS.glob("partial-*.json"))
    if not paths:
        print("No result files in eval/results/. Run eval/run_eval.py first.")
        return 1
    payloads = load(paths)
    tables = build_tables(payloads)
    write_tables(tables)
    CHARTS.mkdir(parents=True, exist_ok=True)
    made = [chart_overall(tables["summary"]), chart_categories(tables["summary"]), chart_grid(payloads)]
    print(f"{len(payloads)} configuration(s):")
    for s in tables["summary"]:
        print(f"  {s['configuration']:<28} runs={s['runs']}  accuracy={s['accuracy_pct']}%  "
              f"grounded={s['groundedness_pct_answerable']}%  refusal={s['correct_refusal_pct']}%")
    print("Wrote", OUT.relative_to(HERE.parent), "and", ", ".join(p.name for p in made))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
