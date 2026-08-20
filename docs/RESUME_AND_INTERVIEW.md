# FinTrace-CN 简历与面试准备

## 项目定位

基于开源金融 Agent 二次开发的 A 股可信研究系统。个人工作重点是 A 股数据规范、Point-in-Time、Evidence Ledger、确定性估值、Validator、Agent 评测及工作台，而不是上游已删除的美股流水线。

## 简历表述

- 设计 A 股 Point-in-Time 研究链路，通过版本化快照、available_at 截止约束与 Evidence Ledger，实现核心事实、报告期、单位及计算依赖的可追溯。
- 将 LLM 工具编排与财务计算解耦，使用 Python 实现 FY/Q1/H1/9M/TTM 转换、PE/PB/PS 同行估值和 Research Gate，在工具失败、证据缺失或估值方法不适用时阻断确定性结论。
- 建立覆盖 Provider 契约、负面案例、API、Streamlit 与四组消融的离线测试体系，并交付 FastAPI/Streamlit 工作台和可验证 Markdown 报告。

测试数量和成功率只填写当前 CI 或本机最终验证的真实结果。dry-run/mock 指标不得写成真实 LLM 效果。

## 90 秒项目介绍

金融 Agent 最大风险不是语言不流畅，而是把错误数字说得很可信。FinTrace-CN 的核心是把信任边界拆开：Provider 只提供带时点和来源的事实；Python 计算 TTM 和估值；Evidence Ledger 保存每个结果的输入依赖；Validator 决定结论是否能显示；LLM 只负责工具选择和受约束叙事。项目同时提供成功与证据缺失的阻断 Demo，证明系统会 fail closed，而不是补造数字。

## 必须掌握

- research_as_of、published_at、available_at 与 look-ahead bias；
- 累计财报转单季度，TTM = 当期累计 + 上年全年 - 上年同期累计；
- RAW/QFQ/HFQ 与市值计算；
- Evidence fact/calculation/input_ids 和重算；
- PE/PB/PS、亏损同行、IQR 和银行方法边界；
- Provider typed error、重试、缓存、fallback 与熔断；
- ReAct 工具循环、JSON Schema、最大步数、成本和工具轨迹；
- tool F1、参数正确率、证据覆盖、E2E、拦截率与泄漏率；
- mock 消融与真实模型评测的结论边界；
- Streamlit rerun、缓存、session state，以及本地线程池任务的生产限制。

## 高频追问

1. 为什么不用纯确定性工作流，Agent 的必要性在哪里？
2. Evidence ID 能否被模型伪造，系统如何建立可信交集？
3. Validator 通过是否等于数据和投资结论绝对正确？
4. 财报更正、Schema 漂移、限流和超时分别如何处理？
5. 为什么同行估值使用 RAW 价格？
6. 为什么银行不使用通用 EV/EBITDA？
7. 如何证明测试与 Demo 没有依赖本机缓存或真实密钥？
8. 为什么没有使用 RAG 或向量数据库？
9. 当前本地 JSON 任务系统为什么不适合多实例部署？
10. 哪些代码来自上游，哪些是你新增且能从零解释的？

## Demo 顺序

先展示成功案例的 Evidence DAG，再切换到缺总股本案例展示 Validator 阻断。最后展示 Agent 消融页面并主动说明 dry-run 与真实模型评测的区别。全程避免讨论涨跌预测和收益承诺。
