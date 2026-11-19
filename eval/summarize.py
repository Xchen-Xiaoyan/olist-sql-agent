"""Summarize eval/results/*.jsonl into the markdown tables used in eval/REPORT.md."""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.questions import Q  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
DATA_CATS = ["simple", "join", "time", "metric", "complex", "explore"]


def load():
    runs = {}
    for f in sorted(RESULTS.glob("*.jsonl")):
        system, model = f.stem.split("__")
        runs[(system, model)] = [json.loads(line) for line in f.open(encoding="utf-8")]
    return runs


def pct(rows, cond=lambda r: r["correct"]):
    return f"{sum(bool(cond(r)) for r in rows) / len(rows):.0%}" if rows else "-"


def main():
    runs = load()
    order = sorted(runs, key=lambda k: (k[1], k[0] != "baseline"))
    n_data = sum(q["cat"] in DATA_CATS for q in Q)
    head = f"| Model | System | Answer correct ({n_data}) | Exact table | " + " | ".join(DATA_CATS) + " | Clarify (5) | Decline (5) |"
    print(head)
    print("|" + "---|" * (head.count("|") - 1))
    for key in order:
        rs = runs[key]
        data = [r for r in rs if r["cat"] in DATA_CATS]
        cells = [pct(data), pct(data, lambda r: r.get("exact", r["correct"]))]
        cells += [pct([r for r in rs if r["cat"] == c]) for c in DATA_CATS]
        cells += [pct([r for r in rs if r["cat"] == "clarify"]), pct([r for r in rs if r["cat"] == "decline"])]
        print(f"| {key[1]} | {key[0]} | " + " | ".join(cells) + f" |   <!-- n={len(rs)} -->")

    print("\n| Model | System | Answered with an error-free SQL first try | Hit a SQL error | Recovered after error |"
          " Wrongly asked/declined on data Qs | LLM calls / Q | Median s | p90 s |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key in order:
        rs = runs[key]
        data = [r for r in rs if r["cat"] in DATA_CATS]
        err = [r for r in data if r["sql_errors"]]
        rec = [r for r in err if r["recovered"] and r["correct"]]
        over = [r for r in data if r["status"] in ("clarify", "decline")]
        secs = sorted(r["seconds"] for r in rs)
        p90 = secs[int(0.9 * (len(secs) - 1))] if secs else 0
        print(f"| {key[1]} | {key[0]} | {len(data) - len(err)}/{len(data)} | {len(err)} | "
              f"{len(rec)}/{len(err)} correct | {len(over)} | {statistics.mean(r['llm_calls'] for r in rs):.1f} | "
              f"{statistics.median(secs):.1f} | {p90:.1f} |")

    print("\nFailures (data questions):")
    for key in order:
        bad = [r["id"] for r in runs[key] if not r["correct"]]
        print(f"  {key[0]:8s} {key[1]:24s} {', '.join(bad)}")


if __name__ == "__main__":
    main()
