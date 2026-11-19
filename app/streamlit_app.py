"""Chat UI for the Olist data-analysis agent.  Run: streamlit run app/streamlit_app.py"""
import os
import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
# Streamlit Cloud keeps the key in st.secrets; the LLM wrapper reads it from the environment.
try:
    for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODELS", "LLM_PROVIDER"):
        if k in st.secrets and not os.getenv(k):
            os.environ[k] = st.secrets[k]
except FileNotFoundError:
    pass

from agent.core import Agent  # noqa: E402
from agent.db import Database  # noqa: E402
from agent.llm import get_llm  # noqa: E402
from app.examples import EXAMPLES  # noqa: E402

GITHUB = "https://github.com/Xchen-Xiaoyan/olist-sql-agent"
MAX_QUESTIONS = 20

st.set_page_config(page_title="Olist 数据分析 Agent", page_icon="📊", layout="wide")
st.markdown("""<style>
  .block-container {padding-top: 2rem; max-width: 1100px;}
  div[data-testid="stExpander"] details summary p {font-size: 0.9rem; color: #64748b;}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def load_agent() -> Agent:
    # Answers are cached on disk, so the example questions replay instantly and cost no quota.
    return Agent(get_llm(cache=ROOT / "cache" / "demo.sqlite"), Database())


def draw_chart(df, spec):
    kind, x, y, title = spec["chart_type"], spec["x"], spec["y"], spec.get("title", "")
    fn = {"bar": px.bar, "line": px.line, "scatter": px.scatter}.get(kind)
    fig = px.pie(df, names=x, values=y, title=title) if kind == "pie" else fn(df, x=x, y=y, title=title)
    if kind == "line":
        fig.update_traces(mode="lines+markers")
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10), title_font_size=15)
    st.plotly_chart(fig, use_container_width=True)


def show_steps(steps):
    n_sql = sum(s["type"] == "sql" for s in steps)
    n_err = sum(bool(s.get("error")) for s in steps)
    label = f"🔍 分析过程 · {n_sql} 次查询" + (f" · 自动修正 {n_err} 次错误" if n_err else "")
    with st.expander(label):
        for i, s in enumerate(steps, 1):
            if s["type"] == "sql":
                st.markdown(f"**步骤 {i} · 查询**" + (f" — {s['purpose']}" if s.get("purpose") else ""))
                st.code(s["sql"], language="sql")
                if s.get("error"):
                    st.error(f"数据库报错,Agent 据此改写查询:{s['error'][:300]}")
                else:
                    st.caption(f"返回 {s.get('rows', 0)} 行")
            elif s["type"] == "chart":
                st.markdown(f"**步骤 {i} · 画图** — {s.get('chart_type')}: {s.get('x')} × {s.get('y')}")
            elif s["type"] == "nudge":
                st.markdown(f"**步骤 {i} · 自检** — 还没有查询结果就想作答,被要求先查数据")
            elif s["type"] in ("clarify", "decline"):
                st.markdown(f"**步骤 {i} · {'反问' if s['type'] == 'clarify' else '拒答'}**")


def md(text: str) -> str:
    """Escape $ so 'R$ 1,000 ... R$ 2,000' is not rendered as LaTeX."""
    return text.replace("$", r"\$")


def render(msg, key):
    r = msg["result"]
    if r["status"] == "clarify":
        st.info("🤔 " + md(r["answer"]))
        if msg is st.session_state.messages[-1]:
            cols = st.columns(max(1, len(r["options"])))
            for i, (c, opt) in enumerate(zip(cols, r["options"])):
                if c.button(opt, key=f"{key}-opt{i}", use_container_width=True):
                    st.session_state.pending = opt
                    st.rerun()
    elif r["status"] == "decline":
        st.warning("🚫 " + md(r["answer"]))
    elif r["status"] in ("answer", "no_sql"):
        st.markdown(md(r["answer"]))
    else:
        st.error("这次没有得出结论(步数用完或模型出错),换个问法试试。")
    if r["chart"] and r["df"] is not None:
        draw_chart(r["df"], r["chart"])
    if r["df"] is not None and r["status"] == "answer":
        with st.expander(f"📋 结果数据 · {len(r['df'])} 行"):
            st.dataframe(r["df"], use_container_width=True, hide_index=True)
            st.download_button("下载 CSV", r["df"].to_csv(index=False).encode("utf-8-sig"),
                               file_name="result.csv", key=f"{key}-dl")
    if r["steps"]:
        show_steps(r["steps"])


def history_for_agent():
    """Earlier turns as plain text, so follow-ups like '那 2017 年呢?' or a clarification choice have context."""
    out = []
    for m in st.session_state.messages[-8:]:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        else:
            r = m["result"]
            text = r["answer"] + (f"\n(Options offered: {', '.join(r['options'])})" if r["options"] else "")
            if r["sql"]:
                text += f"\n(SQL used: {r['sql']})"
            out.append({"role": "assistant", "content": text})
    return out


def ask(question):
    history = history_for_agent()
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.status("分析中…", expanded=False) as status:
            def on_step(s):
                if s["type"] == "sql":
                    status.update(label="出错了,正在改写查询…" if s.get("error") else
                                  f"查询中:{s.get('purpose') or '运行 SQL'}")
            try:
                res = load_agent().run(question, history=history, on_step=on_step)
                status.update(label=f"完成 · 用时 {res.wall:.1f} 秒", state="complete")
            except Exception as e:  # noqa: BLE001 - free-tier outages should not crash the page
                status.update(label="模型暂时不可用", state="error")
                st.error(f"Gemini 免费额度繁忙或用完了,请稍后再试。({str(e)[:120]})")
                st.session_state.messages.pop()
                return
        msg = {"role": "assistant", "result": {
            "status": res.status, "answer": res.answer, "options": res.options, "sql": res.sql,
            "df": res.df, "chart": res.chart, "steps": res.steps}}
        st.session_state.messages.append(msg)
        render(msg, f"m{len(st.session_state.messages)}")
    st.session_state.asked += 1


# ---------------- page ----------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("asked", 0)

with st.sidebar:
    st.markdown("### 📊 Olist 数据分析 Agent")
    st.caption("用自然语言问电商经营问题,Agent 自己写 SQL、查数据库、出错自动修正、画图并给出结论;"
               "问题不清楚会反问,数据里没有的会直接说明。")
    st.markdown("**数据** · 巴西电商 Olist 公开数据集,2017-01 至 2018-08,约 9.8 万笔有效订单")
    st.markdown("**口径** · 与 [Power BI 看板](https://xchen-xiaoyan.github.io/projects/olist-bi.html) 一致")
    st.markdown(f"[GitHub 代码与评测报告]({GITHUB})")
    if st.button("清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("Olist 数据分析 Agent")
st.caption("Text-to-SQL agent · 工具调用 · 自动纠错 · 反问与拒答 · Gemini + DuckDB")

if not st.session_state.messages:
    st.markdown("**试试这些问题:**")
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES):
        if cols[i % 3].button(ex, key=f"ex{i}", use_container_width=True):
            st.session_state.pending = ex
            st.rerun()

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            render(m, f"h{i}")

typed = st.chat_input("问一个关于订单、GMV、品类、卖家、配送、评分、复购的问题…")
question = typed or st.session_state.pop("pending", None)
if question:
    if st.session_state.asked >= MAX_QUESTIONS:
        st.warning(f"每次访问最多 {MAX_QUESTIONS} 个问题(免费额度有限),刷新页面可重新开始。")
    else:
        ask(question)
