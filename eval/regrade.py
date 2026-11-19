"""Re-grade saved results after changing the grader or the gold SQL, by re-running each saved final query.

Results store the agent's final SQL, and queries are deterministic, so no LLM calls are needed.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.core import Result  # noqa: E402
from agent.db import Database, SQLError  # noqa: E402
from eval.questions import Q  # noqa: E402
from eval.run_eval import grade  # noqa: E402

db, qs = Database(), {q["id"]: q for q in Q}
for f in sorted((ROOT / "eval" / "results").glob("*.jsonl")):
    rows, changed = [json.loads(line) for line in f.open(encoding="utf-8")], 0
    for r in rows:
        res = Result(r["q"], status=r["status"], answer=r["answer"], sql=r["sql"])
        if r["sql"]:
            try:
                res.df = db.query(r["sql"])
            except SQLError:
                res.df = None
        ok, exact = grade(qs[r["id"]], res, db)
        changed += ok != r["correct"] or exact != r.get("exact")
        r["correct"], r["exact"] = ok, exact
    f.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")
    print(f"{f.name}: {changed} changed")
