"""The data-analysis agent (tool-calling loop) and a single-shot text-to-SQL baseline for comparison."""
import re
import time
from dataclasses import dataclass, field

import pandas as pd

from .db import Database, SQLError
from .llm import ChatLLM
from .schema import SCHEMA_DOC

MAX_STEPS = 8
PREVIEW_ROWS = 20

TOOLS = [
    {"name": "run_sql",
     "description": "Run one read-only DuckDB SELECT query and get back the row count and the first rows. "
                    "On error you get the database error message; fix the query and call again.",
     "parameters": {"type": "object", "properties": {
         "sql": {"type": "string", "description": "A single DuckDB SELECT (or WITH ... SELECT) statement."},
         "purpose": {"type": "string", "description": "One short phrase: what this query checks or computes."}},
         "required": ["sql"]}},
    {"name": "make_chart",
     "description": "Draw a chart from the result of the most recent successful run_sql. Use it for trends over "
                    "time or comparisons across more than 3 groups.",
     "parameters": {"type": "object", "properties": {
         "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "scatter"]},
         "x": {"type": "string", "description": "Column for the x axis (or pie labels)."},
         "y": {"type": "string", "description": "Numeric column for the y axis (or pie values)."},
         "title": {"type": "string"}},
         "required": ["chart_type", "x", "y", "title"]}},
    {"name": "ask_clarification",
     "description": "Ask the user a question instead of guessing, when the request does not say which metric to "
                    "use (for example 'best', 'performance', 'how are we doing').",
     "parameters": {"type": "object", "properties": {
         "question": {"type": "string"},
         "options": {"type": "array", "items": {"type": "string"}, "description": "2-4 concrete choices."}},
         "required": ["question"]}},
    {"name": "decline",
     "description": "Say the question cannot be answered from this database (the needed data does not exist).",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}},
]

AGENT_SYSTEM = f"""You are a data analyst agent for the Olist e-commerce database. You answer business questions by
querying the database with the run_sql tool.

{SCHEMA_DOC}
## How to work
1. If the question does not say which metric it means ("best seller", "performance", "how are we doing"), call
   ask_clarification with 2-4 concrete options. Do not ask when the metric is stated or defined above.
2. If the data needed is not in the database (see "Not in the data"), call decline. Do not answer with a proxy.
3. Look before you filter: if the question names a city, category or other text value that is not spelled out
   above, first run a lookup query for the stored values (e.g. SELECT DISTINCT city FROM dim_customer WHERE city
   ILIKE '%paulo%'), then filter with the exact value(s) that match. City names are stored lowercase without
   accents; LIKE patterns can also catch other cities ('sao paulo das missoes'), so prefer exact matches.
4. Write the DuckDB SQL and call run_sql. Read the result critically: on an error, an empty result, or numbers
   that look wrong, fix the query and run it again.
5. Before your final query, check it against this list and fix anything that fails:
   - GMV, orders, buyers, AOV, reviews: is the is_valid filter applied?
   - Does the measure match the question (a count of items/orders vs a sum of money vs an average vs a rate)?
   - Delivery metrics: restricted to delivered orders?
6. Your LAST run_sql call must be the query whose result answers the question, returning only the rows asked for
   (e.g. LIMIT 5 for a top 5). Round nothing in SQL except where asked.
7. For a trend or a comparison across several groups, call make_chart after that query.
8. Then reply with the final answer in the same language as the question: 1-4 sentences with the key numbers,
   rates as percentages, plus any assumption you made. Do not include SQL in the reply."""

BASELINE_SYSTEM = f"""You translate business questions about the Olist e-commerce database into DuckDB SQL.

{SCHEMA_DOC}
Reply with exactly one DuckDB SELECT query inside a ```sql code block, returning only the rows asked for, and nothing else.
If the question does not say which metric it means ("best seller", "performance", "how are we doing"), reply
instead with one line: CLARIFY: <your question>.
If the data needed is not in the database, reply instead with one line: DECLINE: <reason>."""


@dataclass
class Result:
    question: str
    status: str = "answer"          # answer | clarify | decline | no_sql | error | max_steps
    answer: str = ""
    sql: str | None = None          # last successful query
    df: pd.DataFrame | None = None
    chart: dict | None = None
    options: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    sql_errors: int = 0
    seconds: float = 0.0            # model time + SQL time (excludes rate-limit waits; survives cache replays)
    wall: float = 0.0

    @property
    def recovered(self) -> bool:
        """Hit at least one SQL error and still ended with a successful query."""
        return self.sql_errors > 0 and self.sql is not None and self.status == "answer"


def preview(df: pd.DataFrame) -> str:
    head = df.head(PREVIEW_ROWS).copy()
    for c in head.select_dtypes("float"):
        head[c] = head[c].map(lambda v: (round(v, 2) if abs(v) >= 1 else float(f"{v:.4g}")) if pd.notna(v) else v)
    more = " (truncated at the row cap)" if df.attrs.get("truncated") else ""
    shown = f", first {PREVIEW_ROWS} shown" if len(df) > PREVIEW_ROWS else ""
    note = ""
    if df.empty:
        note = "\nThe query returned no rows. Check filter values against the schema (exact spelling, dates)."
    elif df.isna().all().any():
        note = f"\nColumn(s) {', '.join(df.columns[df.isna().all()])} are entirely NULL. Check the logic."
    return f"{len(df)} rows{more}{shown}:\n{head.to_csv(index=False)}{note}"


class Agent:
    def __init__(self, llm: ChatLLM, db: Database | None = None, max_steps: int = MAX_STEPS):
        self.llm, self.db, self.max_steps = llm, db or Database(), max_steps

    def run(self, question: str, history: list[dict] | None = None, on_step=None) -> Result:
        """history: earlier [{"role": "user"|"assistant", "content": str}] turns, for follow-up questions."""
        res, t0 = Result(question), time.time()
        messages = [*(history or []), {"role": "user", "content": question}]
        nudged = False
        for _ in range(self.max_steps):
            out = self.llm.chat(AGENT_SYSTEM, messages, TOOLS)
            res.llm_calls += 1
            res.seconds += out.get("elapsed", 0.0)
            messages.append({"role": "assistant", "content": out["content"], "tool_calls": out["tool_calls"],
                             "raw": out.get("raw")})
            if not out["tool_calls"]:
                if res.sql is None and not nudged:
                    # Self-check: a data answer with no query behind it is a guess. Push back once.
                    nudged = True
                    messages.append({"role": "user", "content": "You have not run a successful query yet. Run "
                                     "run_sql to get the numbers, or call ask_clarification or decline."})
                    res.steps.append({"type": "nudge"})
                    continue
                res.answer = (out["content"] or "").strip()
                res.status = "answer" if res.sql else "no_sql"
                break
            stop = False
            for call in out["tool_calls"]:
                content, step = self._tool(call, res)
                res.steps.append(step)
                if on_step:
                    on_step(step)
                messages.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                                 "content": content})
                if call["name"] in ("ask_clarification", "decline"):
                    stop = True
            if stop:
                break
        else:
            res.status = "max_steps"
        res.wall = time.time() - t0
        return res

    def _tool(self, call: dict, res: Result) -> tuple[str, dict]:
        name, args = call["name"], call["args"]
        if name == "run_sql":
            sql = str(args.get("sql", ""))
            step = {"type": "sql", "sql": sql, "purpose": args.get("purpose", "")}
            t0 = time.time()
            try:
                df = self.db.query(sql)
                res.seconds += time.time() - t0
            except SQLError as e:
                res.seconds += time.time() - t0
                res.sql_errors += 1
                return f"ERROR: {e}", step | {"error": str(e)}
            res.sql, res.df = sql, df
            return preview(df), step | {"rows": len(df)}
        if name == "make_chart":
            step = {"type": "chart", **args}
            if res.df is None:
                return "ERROR: run a query first.", step | {"error": "no data"}
            missing = [args.get(k) for k in ("x", "y") if args.get(k) not in res.df.columns]
            if missing:
                return (f"ERROR: column(s) {missing} not in the last result; columns are "
                        f"{list(res.df.columns)}."), step | {"error": f"missing {missing}"}
            res.chart = {k: args.get(k) for k in ("chart_type", "x", "y", "title")}
            return "Chart created.", step
        if name == "ask_clarification":
            res.status, res.answer = "clarify", str(args.get("question", ""))
            res.options = [str(o) for o in args.get("options", [])][:4]
            return "Question shown to the user.", {"type": "clarify", **args}
        if name == "decline":
            res.status, res.answer = "decline", str(args.get("reason", ""))
            return "Shown to the user.", {"type": "decline", **args}
        return f"ERROR: unknown tool {name}", {"type": "unknown", "name": name}


def run_baseline(llm: ChatLLM, db: Database, question: str) -> Result:
    """Single shot: one LLM call writes one SQL query, executed once, no feedback."""
    res, t0 = Result(question), time.time()
    out = llm.chat(BASELINE_SYSTEM, [{"role": "user", "content": question}], [])
    res.llm_calls, res.seconds = 1, out.get("elapsed", 0.0)
    text = (out["content"] or "").strip()
    if m := re.match(r"\s*(CLARIFY|DECLINE)\s*:\s*(.*)", text, re.S | re.I):
        res.status, res.answer = m.group(1).lower(), m.group(2).strip()
    else:
        m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
        sql = (m.group(1) if m else text).strip()
        res.steps.append({"type": "sql", "sql": sql})
        t1 = time.time()
        try:
            res.df, res.sql = db.query(sql), sql
            res.seconds += time.time() - t1
        except SQLError as e:
            res.status, res.sql_errors = "error", 1
            res.steps[-1]["error"] = str(e)
    res.wall = time.time() - t0
    return res
