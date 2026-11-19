"""Ask the agent one question from the command line: python scripts/try.py "question" [gemini|ollama]"""
import json
import sys

from dotenv import load_dotenv

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
load_dotenv()
from agent.core import Agent  # noqa: E402
from agent.llm import get_llm  # noqa: E402

q = sys.argv[1]
agent = Agent(get_llm(sys.argv[2] if len(sys.argv) > 2 else None))
r = agent.run(q, on_step=lambda s: print("  step:", json.dumps(s, ensure_ascii=False)[:300]))
print(f"[{r.status}] {r.llm_calls} LLM calls, {r.sql_errors} SQL errors, {r.seconds:.1f}s")
print(r.answer)
if r.df is not None:
    print(r.df.head(10).to_string())
print("chart:", r.chart)
