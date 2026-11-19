"""Pre-run the demo's example questions so they replay instantly from cache/demo.sqlite (no quota used).

Run after changing the prompt, tools or model: python scripts/warm_demo_cache.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from agent.core import Agent  # noqa: E402
from agent.llm import get_llm  # noqa: E402
from app.examples import ALL_QUESTIONS  # noqa: E402

agent = Agent(get_llm(cache=ROOT / "cache" / "demo.sqlite"))
for q in ALL_QUESTIONS:
    r = agent.run(q)
    print(f"[{r.status:7s}] {r.llm_calls} calls, {r.sql_errors} errors, chart={bool(r.chart)} | {q}")
