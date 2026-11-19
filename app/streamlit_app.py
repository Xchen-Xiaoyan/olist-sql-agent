"""Chat UI for the Olist data-analysis agent.  Run: streamlit run app/streamlit_app.py

Layout: a welcome screen (input under the heading, then example cards) until the first question; after that
a chat with the input pinned to the bottom. Styling lives in .streamlit/config.toml plus the CSS block below.
"""
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
from app.examples import BOUNDARY, EXAMPLES  # noqa: E402

GITHUB = "https://github.com/Xchen-Xiaoyan/olist-sql-agent"
DASHBOARD = "https://github.com/Xchen-Xiaoyan/olist-bi-dashboard"
MAX_QUESTIONS = 20
PLACEHOLDER = "例如：2018 年每个月的 GMV 趋势如何？"
METRIC_NOTE = "口径：金额单位为巴西雷亚尔（R$）；GMV、订单数、买家数只统计有效订单（不含取消和缺货）。"
NOT_IN_DATA = "这份数据不包含：利润与成本、营销投入、流量、用户年龄与性别、商品品牌，以及 2018 年 8 月之后的订单。"
BLUE = "#2563eb"

st.set_page_config(page_title="Olist Analytics · 电商数据分析助手", page_icon=":material/insights:",
                   layout="wide", initial_sidebar_state="auto")

# All custom CSS in one place. Selectors use data-testid attributes and st-key-<key> classes, which Streamlit
# exposes for this purpose, rather than generated class names.
st.html("""<style>
  [data-testid="stSidebar"] { width: 260px !important; min-width: 260px !important; }
  [data-testid="stMainBlockContainer"], [data-testid="stBottomBlockContainer"] {
    max-width: 1040px; padding-left: 2rem; padding-right: 2rem; }
  [data-testid="stMainBlockContainer"] { padding-top: 3rem; padding-bottom: 6rem; }
  .brand { display: flex; align-items: center; gap: 10px; margin: 4px 0 8px; }
  .brand .mark { width: 32px; height: 32px; border-radius: 8px; background: #2563eb; display: grid; place-items: center; }
  .brand b { display: block; font-size: 15px; color: #111827; line-height: 1.2; }
  .brand span { font-size: 12px; color: #6b7280; }
  .facts { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; font-size: 13px; margin: 8px 0 4px; }
  .facts dt { color: #6b7280; } .facts dd { margin: 0; color: #1f2937; }
  .hero h1 { font-size: 32px; font-weight: 650; letter-spacing: -0.01em; margin: 24px 0 8px; padding: 0; }
  .hero p { color: #4b5563; font-size: 16px; margin: 0 0 24px; }
  .muted { color: #6b7280; font-size: 13px; }
  .section-label { font-size: 13px; font-weight: 600; color: #4b5563; margin: 24px 0 8px; }
  /* Example cards: full-width, left-aligned, wrapping buttons */
  .st-key-examples button, .st-key-boundary button {
    justify-content: flex-start; text-align: left; align-items: flex-start; min-height: 76px;
    padding: 12px 16px; background: #ffffff; border: 1px solid #e5e7eb; }
  .st-key-examples button:hover, .st-key-boundary button:hover { border-color: #2563eb; background: #f8faff; }
  .st-key-examples button > div, .st-key-boundary button > div,
  .st-key-examples button > div > span, .st-key-boundary button > div > span {
    justify-content: flex-start; align-items: flex-start; width: 100%; }
  .st-key-examples button [data-testid="stIconMaterial"], .st-key-boundary button [data-testid="stIconMaterial"] {
    color: #2563eb; margin-top: 2px; }
  .st-key-examples button p, .st-key-boundary button p { white-space: normal; text-align: left; line-height: 1.5; }
  .st-key-boundary button { min-height: 60px; }
  button:focus-visible, a:focus-visible, textarea:focus-visible {
    outline: 2px solid #2563eb !important; outline-offset: 2px; }
  /* Streamlit sizes the textarea once on mount, sometimes before the layout settles (a 1-line input came out
     ~170px tall). Let the browser size it to its content instead; capped so long questions scroll. */
  [data-testid="stChatInput"] textarea { height: auto !important; field-sizing: content;
    min-height: 1.6rem; max-height: 12rem; }
  [data-testid="stChatInput"] > div { background: #ffffff; border-color: #d1d5db; }
  [data-testid="stChatInput"] > div:focus-within { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, .12); }
  [data-testid="stChatMessage"] { padding: 12px 0; background: transparent; }
  .answer-label { font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase;
                  letter-spacing: .04em; margin-bottom: 4px; }
  @media (max-width: 640px) {
    [data-testid="stMainBlockContainer"], [data-testid="stBottomBlockContainer"] {
      padding-left: 1rem; padding-right: 1rem; }
    [data-testid="stMainBlockContainer"] { padding-top: 1.5rem; }
    .hero h1 { font-size: 26px; margin-top: 8px; }
  }
</style>""")


@st.cache_resource
def load_agent() -> Agent:
    # Answers are cached on disk, so the example questions replay instantly and cost no quota.
    return Agent(get_llm(cache=ROOT / "cache" / "demo.sqlite"), Database())


def md(text: str) -> str:
    """Escape $ so 'R$ 1,000 ... R$ 2,000' is not rendered as LaTeX."""
    return text.replace("$", r"\$")


# ---------------- state and callbacks ----------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("asked", 0)


def on_submit():
    text = (st.session_state.get("q") or "").strip()
    if text:
        st.session_state.pending = text


def fill(question: str):
    """Put an example into the input box for the user to edit and send."""
    st.session_state.q = question
    st.session_state.focus_input = True


def send(question: str):
    st.session_state.pending = question


def reset():
    for k in ("messages", "pending", "running", "q"):
        st.session_state.pop(k, None)


@st.dialog("开始新对话？", width="small")
def confirm_reset():
    st.write("当前对话的内容会被清空。")
    a, b = st.columns(2)
    if a.button("清空并开始", type="primary", use_container_width=True):
        reset()
        st.rerun()
    if b.button("取消", use_container_width=True):
        st.rerun()


# ---------------- result rendering ----------------
def draw_chart(df, spec):
    kind, x, y, title = spec["chart_type"], spec["x"], spec["y"], spec.get("title", "")
    if kind == "pie":
        fig = px.pie(df, names=x, values=y, title=title, color_discrete_sequence=px.colors.qualitative.Safe)
    else:
        fn = {"bar": px.bar, "line": px.line, "scatter": px.scatter}.get(kind, px.bar)
        fig = fn(df, x=x, y=y, title=title, color_discrete_sequence=[BLUE])
        if kind == "line":
            fig.update_traces(mode="lines+markers")
    fig.update_layout(template="plotly_white", height=340, margin=dict(l=8, r=8, t=44, b=8),
                      title=dict(font=dict(size=14), x=0, xanchor="left"), font=dict(size=12))
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


def show_process(r):
    steps = r["steps"]
    n_sql = sum(s["type"] == "sql" for s in steps)
    n_err = sum(bool(s.get("error")) for s in steps)
    with st.expander("查看 SQL 与分析过程", icon=":material/code:"):
        facts = [f"{n_sql} 次查询"] + ([f"修正 {n_err} 次查询错误"] if n_err else [])
        facts += [f"模型调用 {r['llm_calls']} 次", f"用时 {r['wall']:.1f} 秒" + ("（缓存）" if r["wall"] < 0.5 else "")]
        st.caption(" · ".join(facts))
        for i, s in enumerate(steps, 1):
            if s["type"] == "sql":
                st.markdown(f"**{i}. 查询**" + (f" — {s['purpose']}" if s.get("purpose") else ""))
                st.code(s["sql"], language="sql")
                if s.get("error"):
                    st.markdown(f":red[数据库报错，Agent 据此改写查询：] `{s['error'][:240]}`")
                else:
                    st.caption(f"返回 {s.get('rows', 0)} 行")
            elif s["type"] == "chart":
                st.markdown(f"**{i}. 画图** — {s.get('chart_type')}：{s.get('x')} × {s.get('y')}")
            elif s["type"] == "nudge":
                st.markdown(f"**{i}. 自检** — 还没有查询结果就准备作答，被要求先查数据")
            elif s["type"] == "clarify":
                st.markdown(f"**{i}. 反问** — 问题没有说明用什么标准")
            elif s["type"] == "decline":
                st.markdown(f"**{i}. 说明数据边界** — 需要的数据不在库里")


def render(msg, key, is_last):
    r = msg["result"]
    status = r["status"]
    if status == "clarify":
        with st.container(border=True):
            st.markdown("**需要先确认一下**")
            st.markdown(md(r["answer"]))
            if r["options"]:
                if is_last:
                    cols = st.columns(len(r["options"]))
                    for i, (c, opt) in enumerate(zip(cols, r["options"])):
                        c.button(opt, key=f"{key}-opt{i}", on_click=send, args=(opt,), use_container_width=True)
                else:
                    st.caption("可选：" + "、".join(r["options"]))
    elif status == "decline":
        with st.container(border=True):
            st.markdown(":material/block: **当前数据无法回答这个问题**")
            st.markdown(md(r["answer"]))
            st.caption(NOT_IN_DATA)
    elif status == "error":
        with st.container(border=True):
            st.markdown(":material/error: **这次没有完成分析**")
            st.caption(r["answer"])
            if is_last:
                st.button("重试", key=f"{key}-retry", icon=":material/refresh:", on_click=send, args=(msg["question"],))
        return
    elif status in ("answer", "no_sql"):
        st.markdown(md(r["answer"]))
        if status == "no_sql":
            st.caption("提示：这个回答没有基于数据库查询结果，请谨慎参考。")
    else:  # max_steps
        st.markdown(":material/warning: 分析步数用完了还没有得出结论。可以把问题拆小一些，或换个问法再试。")

    df = r["df"]
    if status == "answer" and df is not None:
        if df.empty:
            st.caption("查询没有返回任何数据行。")
        else:
            if r["chart"]:
                draw_chart(df, r["chart"])
            if len(df) > 1 or df.shape[1] > 1:
                st.dataframe(df, use_container_width=True, hide_index=True,
                             height=min(35 * (len(df) + 1) + 3, 320))
                st.download_button("下载 CSV", df.to_csv(index=False).encode("utf-8-sig"), file_name="result.csv",
                                   key=f"{key}-dl", icon=":material/download:", type="tertiary")
        st.caption(METRIC_NOTE)
    if r["steps"]:
        show_process(r)


def history_for_agent():
    """Earlier turns as plain text, so follow-ups like '那 2017 年呢?' or a clarification choice have context."""
    out = []
    for m in st.session_state.messages[-8:]:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["result"]["status"] != "error":
            r = m["result"]
            text = r["answer"] + (f"\n(Options offered: {', '.join(r['options'])})" if r["options"] else "")
            if r["sql"]:
                text += f"\n(SQL used: {r['sql']})"
            out.append({"role": "assistant", "content": text})
    return out


def ask(question):
    """Run the agent for the question that was just added as the last user message."""
    history = history_for_agent()[:-1]
    with st.chat_message("assistant", avatar=":material/insights:"):
        progress = {"sql": 0}
        with st.status("正在分析问题…", expanded=False) as status:
            # Labels follow real agent events: each finished query, each error, the chart.
            def on_step(s):
                if s["type"] == "sql":
                    progress["sql"] += 1
                    status.update(label=f"第 {progress['sql']} 次查询出错，正在修正…" if s.get("error") else
                                  f"已完成第 {progress['sql']} 次查询，正在分析结果…")
                elif s["type"] == "chart":
                    status.update(label="已生成图表，正在整理结论…")
            try:
                res = load_agent().run(question, history=history, on_step=on_step)
                result = {"status": res.status, "answer": res.answer, "options": res.options, "sql": res.sql,
                          "df": res.df, "chart": res.chart, "steps": res.steps, "llm_calls": res.llm_calls,
                          "wall": res.wall}
                status.update(label="分析完成", state="complete")
            except Exception as e:  # noqa: BLE001 - free-tier outages should not crash the page
                status.update(label="模型暂时不可用", state="error")
                result = {"status": "error", "options": [], "sql": None, "df": None, "chart": None, "steps": [],
                          "answer": f"Gemini 免费额度繁忙或已用完，请稍后重试。（{str(e)[:100]}）"}
    st.session_state.messages.append({"role": "assistant", "question": question, "result": result})
    st.session_state.asked += 1


# ---------------- sidebar ----------------
with st.sidebar:
    st.html("""<div class="brand">
      <div class="mark"><img alt="" width="18" height="18" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19V5M4 19h16'/%3E%3Cpath d='M8 15l3.5-4 3 2.5L19 8'/%3E%3C/svg%3E"></div>
      <div><b>Olist Analytics</b><span>电商数据分析助手</span></div></div>""")
    st.caption("用自然语言探索订单、销售、配送与客户体验。")
    st.html("""<dl class="facts">
      <dt>数据源</dt><dd>Olist 巴西电商公开数据</dd>
      <dt>时间范围</dt><dd>2017.01–2018.08</dd>
      <dt>有效订单</dt><dd>约 9.8 万笔</dd></dl>""")
    st.link_button("Power BI 看板", DASHBOARD, icon=":material/dashboard:", type="tertiary")
    st.link_button("GitHub 与评测报告", GITHUB, icon=":material/code:", type="tertiary")
    with st.expander("关于数据与分析"):
        st.markdown(
            "**口径**  \n"
            "- 有效订单：排除取消（canceled）和缺货（unavailable）的订单\n"
            "- GMV = 商品金额 + 运费，单位为巴西雷亚尔（R$）\n"
            "- 买家按 `customer_unique_id` 去重；准时率只看已送达订单\n"
            "- 与 Power BI 看板使用同一套指标定义\n\n"
            "**它怎么工作**  \n"
            "Agent 先理解问题，自己写 SQL 查询数据库；查询出错会读报错并改写；"
            "需要时画图，最后用文字给出结论。问题没说清用什么标准时会先反问，"
            "数据里没有的会直接说明。\n\n"
            "**技术栈**  \n"
            "Gemini（工具调用）· DuckDB · Text-to-SQL · Streamlit · Plotly")
    st.divider()
    if st.button("新建对话", icon=":material/add:", use_container_width=True,
                 disabled=not st.session_state.messages or "running" in st.session_state):
        confirm_reset()
    st.caption(f"每次访问最多可提问 {MAX_QUESTIONS} 次，已用 {st.session_state.asked} 次。")

# ---------------- main ----------------
# A submitted question takes two runs. This run only records it and reruns straight away, so the page switches
# to the chat layout at once (old welcome elements would otherwise stay greyed out until the agent finishes).
# The next run renders the chat and runs the agent under it.
if (new_q := st.session_state.pop("pending", None)) is not None:
    if st.session_state.asked >= MAX_QUESTIONS:
        st.session_state.limit_hit = True
    else:
        st.session_state.messages.append({"role": "user", "content": new_q})
        st.session_state.running = new_q
    st.rerun()
running = st.session_state.get("running")
chatting = bool(st.session_state.messages)


def composer(pinned: bool):
    st.chat_input(PLACEHOLDER, key="q", on_submit=on_submit, submit_mode="disable", max_chars=500,
                  disabled=st.session_state.asked >= MAX_QUESTIONS or running is not None)


if not chatting:
    with st.container():
        st.html("""<div class="hero"><h1>从一个问题，开始理解业务</h1>
          <p>探索销售趋势、品类表现、配送效率与客户评价。</p></div>""")
        with st.container(key="composer"):
            composer(pinned=False)
        st.html('<div class="muted">支持中文与英文提问 · Enter 发送，Shift + Enter 换行<br>'
                '基于公开历史数据分析；缺少的数据会明确说明。</div>')
        st.html('<div class="section-label">可以从这些问题开始</div>')
        with st.container(key="examples"):
            # One st.columns per row keeps the reading order when columns stack on small screens.
            for row in range(0, len(EXAMPLES), 2):
                for c, (i, ex) in zip(st.columns(2), list(enumerate(EXAMPLES))[row:row + 2]):
                    c.button(f"**{ex['topic']}**  \n{ex['q']}", key=f"ex{i}", icon=ex["icon"],
                             on_click=fill, args=(ex["q"],), use_container_width=True)
        with st.expander("试试能力边界：Agent 什么时候会反问或拒答"):
            with st.container(key="boundary"):
                cols = st.columns(2)
                for i, ex in enumerate(BOUNDARY):
                    cols[i].button(f"**{ex['q']}**  \n{ex['topic']}", key=f"bd{i}", icon=ex["icon"],
                                   on_click=fill, args=(ex["q"],), use_container_width=True)
        st.html('<div class="muted" style="margin-top:32px">Text-to-SQL Agent · Gemini 工具调用 · DuckDB</div>')
else:
    for i, m in enumerate(st.session_state.messages):
        is_last = i == len(st.session_state.messages) - 1 and running is None
        if m["role"] == "user":
            with st.chat_message("user", avatar=":material/person:"):
                st.markdown(md(m["content"]))
        else:
            with st.chat_message("assistant", avatar=":material/insights:"):
                render(m, f"h{i}", is_last)
    if st.session_state.pop("limit_hit", False):
        st.warning(f"每次访问最多 {MAX_QUESTIONS} 个问题（免费额度有限），刷新页面可重新开始。")
    composer(pinned=True)  # top level, so Streamlit pins it to the bottom; disabled while a question runs
    if running is not None:
        ask(running)
        st.session_state.pop("running", None)
        st.rerun()

if st.session_state.pop("focus_input", False):
    # Move the cursor into the input after an example fills it, so the user can edit or press Enter.
    st.html("""<script>
      setTimeout(() => { const t = window.parent.document.querySelector('[data-testid="stChatInput"] textarea')
        || document.querySelector('[data-testid="stChatInput"] textarea');
        if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); } }, 120);
    </script>""", unsafe_allow_javascript=True)
