# 竞赛要求对照矩阵（COMPETITION_REQUIREMENTS_MATRIX）

> 竞赛要求 → FinTrace 对应模块 → 当前状态 → 开发 CARD → 验收标准 → Demo 中如何体现。
> 状态值：现有 = 已在仓库运行；部分 = 有基础需扩展；待建 = 由卡片新建。
> 目标阈值未标数值的一律为"待 baseline 测试后冻结"，**禁止随意填写 95%/98% 类数字**。

## A. 竞赛考察的核心能力

| 竞赛要求 | FinTrace 模块 | 当前状态 | CARD | 验收标准 | Demo 体现 |
|---|---|---|---|---|---|
| 信息检索 | Retrieval Engine（BM25 自研+可选向量） | 待建 | 06 | 同查询结果确定性一致；recall@5 目标待冻结 | 输入查询→带页码出处的命中列表 |
| 文档解析 | Document Intelligence Layer | 待建 | 01 | 真实年报 PDF 解析出结构化事实，字段带 page/bbox | 上传年报→解析→跳转原文页 |
| 数据结构化 | Parser 组合 + Normalization | 待建 | 01/02 | 提取 F1 目标待冻结；单位/期间规范化确定性测试 | 财务表格→结构化数据视图 |
| 财务数据处理 | Normalization + Analysis Engine | 部分（periods.py） | 02/03 | YTD→单季转换封闭算例全对；flow/stock 分离测试 | 单季 QoQ 指标展示 |
| 逻辑核验 | Validator 体系 + Checker + Graph 遍历 | 现有（validator）/待建（后两者） | 05/09 | 孤儿 claim/无支撑计算/缺失证据检测全覆盖 | 结论点击→证据链展开 |
| 程序化量化计算 | 确定性计算模块 | 部分（估值） | 03/08 | 手工算例精确匹配；勾稽测试 | 计算过程可展开复核 |
| 财务模型 | 相对估值+敏感性（初赛）/ DCF（决赛） | 部分（PE/PB/PS） | 08/16 | 敏感性矩阵单调性；假设全登记 | Bear/Base/Bull 矩阵 |
| 引用管理 | Evidence Ledger + 引用三型 | 现有（账本）/待建（三型） | 06/09 | quote 逐字校验通过 | 引用逐字对照展示 |
| 报告生成 | Investment Memo | 待建 | 10 | 每个数字可回溯（抽检自动化测试） | 备忘录→逐句点击回溯 |
| 文件访问记录 | events.jsonl | 部分（轨迹）/待建（文件级） | 07 | 全部文件访问事件含 sha256 | Audit Replay 时间线 |
| 工具调用记录 | 现有 ResearchState | 现有 | 07 | 与 manifest 关联 | Replay 中展开每次调用 |
| 计算过程记录 | calculations.json | 待建 | 07/09 | 每计算含公式+输入证据 | 点击数值看公式 |
| 来源可核验 | Evidence Ledger + Document Registry | 现有/待建 | 01 | 每事实带 document_id+page 或 snapshot_id | Claim→PDF 页跳转 |
| 执行过程可追溯 | Run Manifest + Audit Trail | 部分（指纹） | 07 | manifest 17 字段齐全；重放成功 | 选 run_id 回放 |
| 结果可复现 | 同输入+同配置→重执行 | 部分 | 07/12 | replay success rate 目标待冻结 | 现场重跑一次任务 |
| 事实/推论/观点区分 | Claim 三级模型 | 待建 | 09 | fact 100% 绑证据；inference 有 derived_from | 备忘录三级标注展示 |
| 风险和适用边界说明 | Memo 模板 + 估值边界 | 待建 | 10/08 | 边界段非空且模板化生成 | 备忘录风险/证伪段 |

## B. 技术要求（通知原文）

| 竞赛要求 | FinTrace 模块 | 当前状态 | CARD | 验收标准 | Demo 体现 |
|---|---|---|---|---|---|
| ≥1 个 LLM 核心推理引擎，鼓励国产 | src/llms provider 中立客户端 | 现有 | — | openai-compatible 接 DeepSeek/Qwen/GLM | 演示配国产模型 |
| 成果为结构化数据/表格/报告，非纯对话 | report/memo JSON+MD+xlsx | 现有（报告）/待建（memo） | 10/12 | Evidence Pack 目录结构完整 | 导出 Evidence Pack |
| 封闭/半封闭环境运行 | 快照+文档注册表，无出站依赖 | 现有 | 01 | 离线可跑全流程 | 断网演示 |
| 记录文件访问/工具调用/计算/结果 | events.jsonl + manifest | 待建 | 07 | 四类事件全覆盖 | Audit Replay |
| 源代码+依赖+运行说明可复现 | 仓库 + THIRD_PARTY_NOTICES | 现有 | — | 评审环境安装复现测试通过 | 视频中展示安装 |
| Prompt 模块 | Prompt Registry | 待建 | 14 | prompt_hash 入 manifest | 展示注册表 |
| Tool 模块 | cn_tools 注册表 | 现有 | 各卡 | status 信封契约测试 | 工具面板 |
| Skill 模块 | 仅在有真实功能价值时实现 | 待定 | 14 | 不建空壳目录 | — |
| MCP 模块 | 决赛可选，须有服务化真实需求 | 暂缓 | 20 | 不为 PPT 增加协议层 | — |
| 第三方清单（名称/版本/来源/许可证/用途） | THIRD_PARTY_NOTICES_PLAN.md | 待建 | 32 号文档 | 逐项核实后冻结 | 提交材料附清单 |

## C. 评分维度

| 评分项 | 主要支撑 | 量化证据 |
|---|---|---|
| 任务完成度 | 主链全流程 | benchmark task completion rate |
| 数据/计算准确性 | CARD-02/03 + 数值校验 | numeric exact match / calculation accuracy |
| 分析逻辑 | 诊断信号 + Claim 图谱 | unsupported claim 计数 = 0 |
| 证据完整性 | Evidence Ledger + Graph | evidence coverage 目标待冻结 |
| 结果稳定性 | 多次运行一致性 | multi-run consistency 指标 |
| 技术创新性 | 见 MASTER_PLAN 创新收敛（6 项） | 现场答辩叙事 |
| 金融专业性 | 口径/单位/重述/边界声明 | 失败注入演示 |
| 现场展示/答辩 | DEMO_FLOW.md | 5 分钟剧本 + 失败注入 |

## D. 演示即证据（要求矩阵的最终落点）

评分项的量化证据全部来自 CARD-11 三级基准（Synthetic / Real / Holdout）；Demo 中每一项能力都有对应的可点击回溯路径。**无法在 Demo 中展示的能力不算完成。**
