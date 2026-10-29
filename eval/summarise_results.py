"""Turn evaluation result JSONs into the markdown tables used in report/REPORT.md.

    python eval/summarise_results.py                       # every file in eval/results
    python eval/summarise_results.py eval/results/a.json eval/results/b.json

Paste the output into the corresponding sections of report/REPORT.md.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"

METRICS = [
    ("accuracy_pct", "Accuracy"),
    ("groundedness_pct_answerable", "Groundedness"),
    ("correct_refusal_pct", "Correct refusal"),
    ("false_refusal_pct", "False refusal"),
    ("routing_pct", "Routing"),
]


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 1) if values else 0.0


def load(paths: list[Path]) -> list[dict]:
    payloads = []
    for path in paths:
        try:
            payloads.append({"path": path, **json.loads(path.read_text(encoding="utf-8"))})
        except Exception as exc:
            print(f"<!-- skipped {path.name}: {exc} -->")
    return payloads


def configuration_table(payloads: list[dict]) -> None:
    print("### Configuration comparison\n")
    header = "| Configuration | Model | Runs | " + " | ".join(l for _, l in METRICS) + " |"
    print(header)
    print("|---" * (4 + len(METRICS)) + "|")
    for payload in payloads:
        summaries = payload["per_run_summary"]
        cells = [str(mean([s[key] for s in summaries])) for key, _ in METRICS]
        label = "multi-agent" if payload["mode"] == "multi" else "single-agent baseline"
        print(
            f"| {label} | `{payload['model']}` | {payload['runs']} | " + " | ".join(cells) + " |"
        )
    print()


def category_table(payload: dict) -> None:
    label = "multi-agent" if payload["mode"] == "multi" else "single-agent"
    print(f"### Per-category -- {label}, `{payload['model']}`\n")
    print("| Category | n | Accuracy | Groundedness | Routing |")
    print("|---|---|---|---|---|")
    categories = payload["per_run_summary"][0]["by_category"].keys()
    for category in categories:
        rows = [s["by_category"][category] for s in payload["per_run_summary"]]
        print(
            f"| {category} | {rows[0]['n']} | {mean([r['accuracy_pct'] for r in rows])} "
            f"| {mean([r['groundedness_pct'] for r in rows])} "
            f"| {mean([r['routing_pct'] for r in rows])} |"
        )
    print()


def failure_table(payload: dict) -> None:
    label = "multi-agent" if payload["mode"] == "multi" else "single-agent"
    print(f"### Failures -- {label}, `{payload['model']}`, run 1\n")
    rows = [r for r in payload["results"][0] if not r["accurate"] or not r["grounded"]]
    if not rows:
        print("No failures in run 1.\n")
        return
    print("| Q | Category | Accurate | Grounded | What went wrong |")
    print("|---|---|---|---|---|")
    for row in rows:
        notes = []
        if row.get("missing_facts"):
            notes.append(f"missing {row['missing_facts']}")
        if row.get("forbidden_facts_present"):
            notes.append(f"forbidden {row['forbidden_facts_present']}")
        if row["hallucinated_doc_ids"]:
            notes.append(f"invented citation {row['hallucinated_doc_ids']}")
        if row["false_refusal"]:
            notes.append("refused an answerable question")
        if row["answer_type"] == "refusal" and not row["refused"]:
            notes.append("answered an out-of-scope question")
        if not row["route_correct"]:
            notes.append(f"routed to {row['actual_route']}, expected {row['expected_route']}")
        if row["error"]:
            notes.append(f"error: {row['error']}")
        if row["accurate"] and not row["grounded"]:
            notes.append("correct but citation not matched")
        print(
            f"| {row['id']} | {row['category']} | {row['accurate']} | {row['grounded']} "
            f"| {'; '.join(notes) or 'see JSON'} |"
        )
    print()


def consistency_table(payload: dict) -> None:
    cons = payload["consistency"]
    if cons["runs"] < 2:
        return
    label = "multi-agent" if payload["mode"] == "multi" else "single-agent"
    print(f"### Run-to-run consistency -- {label}, `{payload['model']}`\n")
    print(f"{cons['stable_pct']}% of questions gave the same verdict in all {cons['runs']} runs.\n")
    if not cons["unstable_questions"]:
        print("No question changed verdict between runs.\n")
        return
    print("| Q | Accurate per run | Grounded per run | Route per run |")
    print("|---|---|---|---|")
    for item in cons["unstable_questions"]:
        print(
            f"| {item['id']} | {item['accurate_per_run']} | {item['grounded_per_run']} "
            f"| {item['route_per_run']} |"
        )
    print()


def main() -> int:
    paths = [Path(a) for a in sys.argv[1:]] or sorted(RESULTS_DIR.glob("*.json"))
    if not paths:
        print("No result files. Run: python eval/run_eval.py --runs 3")
        return 1

    payloads = load(paths)
    if not payloads:
        return 1

    configuration_table(payloads)
    for payload in payloads:
        category_table(payload)
        failure_table(payload)
        consistency_table(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
