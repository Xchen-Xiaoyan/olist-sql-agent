"""Run the eval set through the agent or the single-shot baseline and grade it.

  python eval/run_eval.py --system agent --provider gemini --model gemini-3.5-flash-lite
  python eval/run_eval.py --system baseline --provider ollama --model qwen2.5:7b

Results go to eval/results/<system>__<model>.jsonl (one line per question; reruns skip finished ids).
"""
import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from agent.core import Agent, run_baseline  # noqa: E402
from agent.db import Database  # noqa: E402
from agent.llm import get_llm  # noqa: E402
from eval.compare import matches, text_matches  # noqa: E402
from eval.questions import Q  # noqa: E402

RESULTS = ROOT / "eval" / "results"


def grade(q: dict, res, db: Database) -> tuple[bool, bool]:
    """Return (correct, exact).

    exact:   the final query's result table matches the gold table (strict execution accuracy).
    correct: exact, or the written answer states the gold values. The agent often returns a fuller table
             (all months, both years) and states the answer in text; that is a correct answer for a user.
    """
    if q["cat"] == "clarify":
        ok = res.status == "clarify"
        return ok, ok
    if q["cat"] == "decline":
        # Refusing outright is right; so is querying, finding nothing, and saying so.
        empty = res.df is not None and (res.df.empty or res.df.isna().all().all())
        ok = res.status == "decline" or (res.status == "answer" and empty)
        return ok, ok
    if res.status != "answer":
        return False, False
    golds = [db.query(sql) for sql in [q["sql"], *q.get("alt", [])]]
    exact = any(matches(res.df, g, q.get("tol", 1e-3)) for g in golds)
    return exact or any(text_matches(res.answer, g) for g in golds), exact


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["agent", "baseline"], required=True)
    ap.add_argument("--provider", choices=["gemini", "ollama"], required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--ids", help="comma-separated subset")
    args = ap.parse_args()

    kw = {"model": args.model} | ({"fallbacks": []} if args.provider == "gemini" else {})
    llm = get_llm(args.provider, cache=ROOT / "cache" / f"{args.provider}.sqlite", **kw)
    db = Database()
    agent = Agent(llm, db)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{args.system}__{args.model.replace(':', '-')}.jsonl"
    done = {json.loads(line)["id"] for line in out.open(encoding="utf-8")} if out.exists() else set()
    todo = [q for q in Q if q["id"] not in done and (not args.ids or q["id"] in args.ids.split(","))]
    print(f"{out.name}: {len(done)} done, {len(todo)} to run")

    def one(q):
        t0 = time.time()
        try:
            res = agent.run(q["q"]) if args.system == "agent" else run_baseline(llm, db, q["q"])
            ok, exact = grade(q, res, db)
            rec = {"id": q["id"], "cat": q["cat"], "q": q["q"], "correct": ok, "exact": exact, "status": res.status,
                   "answer": res.answer[:600], "sql": res.sql, "llm_calls": res.llm_calls,
                   "sql_errors": res.sql_errors, "recovered": res.recovered, "seconds": round(res.seconds, 2),
                   "steps": [{k: (v[:400] if isinstance(v, str) else v) for k, v in s.items()} for s in res.steps]}
        except Exception as e:  # noqa: BLE001 - a backend failure is recorded, not fatal; rerun to retry
            print(f"  {q['id']} FAILED: {e}")
            traceback.print_exc(limit=1)
            return None
        print(f"  {q['id']:4s} {'OK ' if ok else 'BAD'} {res.status:9s} calls={res.llm_calls} "
              f"err={res.sql_errors} {time.time() - t0:5.1f}s")
        return rec

    with ThreadPoolExecutor(args.workers) as ex, out.open("a", encoding="utf-8") as f:
        for rec in ex.map(one, todo):
            if rec:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                f.flush()


if __name__ == "__main__":
    main()
