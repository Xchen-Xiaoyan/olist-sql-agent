# 简历条目

所有数字都来自 [eval/REPORT.md](../eval/REPORT.md)，面试时可以逐条追问到具体的题和 SQL。

## 中文（AI 应用 / 数据分析 / 数据科学岗）

**电商数据分析 Agent（Text-to-SQL）** | 个人项目 | Python, Gemini/Ollama Function Calling, DuckDB, Streamlit

- 搭建基于工具调用的数据分析 Agent：模型调用"执行 SQL、画图、反问、拒答"4 个工具，SQL 报错时根据数据库报错自动改写重试（最多 8 步），先查库里实际存的值再过滤，并按指标口径清单自检；只读执行，加超时和行数上限。
- 自建 60 题评测集（7 类题型，每题附标准 SQL），对比单次生成 SQL 与 Agent 两种方式：Gemini 3.5 flash-lite 答对率 96% → 98%，SQL 报错后 5/5 自动修正；本地 qwen2.5 7B 答对率 52% → 66%，多表关联题 50% → 90%。
- 评测发现小模型加工具后"该不该反问"的判断变差（反问准确率 100% → 40%），据此线上使用 Gemini，并提出先做意图分类的改进；设计"结果表 + 文字答案"两级判分，人工复核误判后收紧规则并全部重判。

精简版（一行）：
- 搭建 Text-to-SQL 数据分析 Agent（工具调用、报错自动修正、反问与拒答），自建 60 题评测集对比单次生成：本地 7B 模型答对率 52% → 66%，强模型 SQL 报错 5/5 自动修正。

## English

**E-commerce Data Analysis Agent (Text-to-SQL)** | Python, Gemini/Ollama function calling, DuckDB, Streamlit

- Built a tool-calling analytics agent: run_sql / make_chart / ask_clarification / decline tools, a self-correction loop that feeds database errors back to the model (up to 8 steps), value lookup before filtering, and a metric-definition checklist; read-only execution with timeouts and row caps.
- Wrote a 60-question benchmark with gold SQL across 7 categories and compared single-shot text-to-SQL with the agent: Gemini 3.5 flash-lite 96% → 98% answer accuracy with 5/5 SQL errors self-corrected; local qwen2.5 7B 52% → 66% (multi-table joins 50% → 90%).
- Found that tool use made the small model worse at deciding when to ask (clarification 100% → 40%), so the demo runs on Gemini; built two-level grading (result table + written answer) and tightened it after auditing false positives by hand.

## 面试可以讲的故事

1. **"先证明 Agent 有没有用"**：强模型单次生成已经 96% 了，Agent 只多对 1 题，在 50 道题上不显著。我没有夸大，而是去找它真正的价值：出错能自己改、过程可查看。然后发现弱模型才是提升最大的地方。
2. **"评分规则本身也要测"**：一开始 Agent 的分数比 Baseline 还低。查下来发现是判分太死板：Agent 列出了全部月份，再在文字里点出答案，却被判错。加了"看文字答案"的判分后，又人工复核出 3 个误判（数值差 0.3% 被放过、日期里的"1"被当成答案），于是再次收紧规则并全部重判。
3. **"负面结果"**：小模型加上工具后反而不会反问了，它会自己挑一个指标作答，或者把工具调用写成文字。这决定了线上选用哪个模型，也指出了下一步改进（先做意图分类）。
4. **"在免费额度里做工程"**：gemini-3.5-flash 免费额度每天只有 20 次，没法用来评测，于是改用 flash-lite 加本地 Ollama。另外做了限速（每分钟 14 次）、按对话缓存（重跑评测不耗额度）、断点续跑，延迟只统计模型调用时间，不含限速等待。
