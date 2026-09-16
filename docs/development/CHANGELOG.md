# CHANGELOG.md — 开发文档体系变更记录

> 版本：v2.0 → v3.0 Competition Edition ｜ 变更日期：2026-09-16
> 本轮为**架构级文档重构**：不写代码，只重构 `docs/development/` 全部开发计划。变更目标是"以北京市大学生金融人工智能竞赛获奖为目标"重排系统设计。

---

## 1. 变更总览

| 维度 | v2.0 | v3.0 |
|---|---|---|
| 竞赛定位 | 覆盖全部七个赛题 | 赛题2主方向 + 赛题5第二核心 + 赛题6输出 + 赛题4工具 + 赛题7内评 |
| 主链 | Provider→工具→研报（偏数据管道） | 真实文档→Document Intelligence→Normalization→Evidence→确定性工具→诊断→Claim→核查→估值→图谱→备忘录→Validator→Evidence Pack→Audit Replay |
| 文档结构 | MASTER_PLAN + 16 卡 | MASTER_PLAN + 3 顶层文档（ARCHITECTURE_V2 / COMPETITION_REQUIREMENTS_MATRIX / DEMO_FLOW）+ 21 卡 + THIRD_PARTY_NOTICES_PLAN + CHANGELOG |
| 卡片字段 | 不统一 | 20 个统一字段（目标→竞赛阶段），agent 可独立执行 |
| 金融计算假设 | YTD 直接 QoQ、DCF=股价、区间交并集、A/B/C/D 总分、多空加权评分 | YTD 强制单季换算、EV 桥、分方法展示+dispersion、零权重诊断、零评分对照 |
| 工程取向 | 多 Agent / MCP / Skill / 全量拆分前端为卖点 | 去名词化：Multi-Agent 降 P2（强制消融）、MCP 降 P3（入场合条件）、Skill 去空壳、前端最小增量 |

## 2. 逐项修改与理由

### 2.1 竞赛定位收敛

**修改**：放弃"覆盖七赛题"叙事。赛题1（数据结构化提取）升级为系统级 **Document Intelligence Layer**；赛题3（产业链）降 P3 决赛可选。
**理由**：竞赛评分考察"任务完成度、数据准确性、可追溯"，而不是功能广度。堆功能挤占 P0 开发窗口，且每个浅功能都会在答辩中被追问穿。

### 2.2 主链重定义

**修改**：主链起点从"provider 数据"改为"真实金融文档"，终点从"生成研报"延伸到"Evidence Pack + Audit Replay"。
**理由**：评委可现场验证的入口是上传真实 PDF，出口是可离线复核的证据包——首尾都是"可核验"的物理载体。

### 2.3 金融逻辑硬伤修正（v2 五处错误）

| v2 错误 | v3 修正 | 落点 |
|---|---|---|
| 对 YTD 累计值直接 `compute_qoq` | 强制前置 `convert_ytd_to_single_quarter()`（100/230/390/540→100/130/160/150）；flow/stock 区分差分语义 | CARD-02/03 |
| 同比统一 `(cur-prev)/abs(prev)` | 盈利状态迁移五分支：正常/扭亏为盈/由盈转亏/亏损扩大收窄/零基期禁百分比 | CARD-03 |
| DCF 估值结果直接当股价 | EV 桥：EV−净债务−少数股东权益+非经营资产=Equity Value，再除稀释股本 | CARD-16（降 P2 决赛） |
| DCF 与相对估值区间取交/并集 | 分别展示 DCF/PE/PB/PS 区间 + 报告 method dispersion | CARD-08/16 |
| 多空评分 `Σ(argument×(1+0.5×evidence_count))` 与 A/B/C/D 加权总分 | 全部删除；多空只输出结构化对照（六产物），质量评估改零权重多维诊断 | CARD-19/17 |

**理由**：金融专业性是评分项，也是答辩必被追问项。无依据的公式比没有公式更糟。

### 2.4 新增模块（v3 七个新卡）

| 新卡 | 模块 | 理由 |
|---|---|---|
| CARD-01 | Document Intelligence Layer（原 CARD-11 质押/中标范围扩大为 8 类输入 + page/bbox + 反向跳转） | "从报告数字跳回 PDF 页"是竞赛最重要展示能力 |
| CARD-02 | Financial Normalization（单位/币种/期间/口径/版本） | 单位与口径错误是真实研报高频错误，也是 v2 完全缺失的一层 |
| CARD-04 | Accounting Scope / Restatement Detection | 更正公告/重述下直接同比是错误，必须 block/use_adjusted/warning 三选一 |
| CARD-07 | Run Manifest + events.jsonl | 可复现的物理基础（17 字段 + 只追加审计流） |
| CARD-09 | Claim-Evidence Graph | 系统核心创新：结论→计算→证据→PDF 页逐层可溯 + 孤儿检测 |
| CARD-12 | Evidence Pack + Audit Replay | 提交成果物 + 历史任务重放 UI |
| CARD-13 | Source Conflict Resolver | 真实材料必然多版本冲突，静默覆盖不可接受 |

### 2.5 优先级重排（去过度工程化）

| 模块 | v2 | v3 | 理由 |
|---|---|---|---|
| Multi-Agent 编排 | P0 主架构 | P2（CARD-18，强制消融四问） | 无指标收益不为技术名词买单；主链单 Agent 已闭环 |
| MCP Server | P0/P1 | P3（CARD-20，入场合条件） | 初赛不考 MCP；仅为 PPT 出现"MCP"而加协议层是负资产 |
| Skill 体系 | 独立卡片建 skills 目录 | 并入 CARD-14 Prompt Registry（Skill 必须有真实功能价值） | 竞赛通知提到 Skill ≠ 必须有空壳目录 |
| workbench 全量拆分 | CARD-01（工程重构） | CARD-15 最小增量 11 页 | 前端大规模重写挤占竞赛窗口且无评分收益 |
| DCF | P0 | P2 决赛 | 相对估值 + 敏感性已支撑初赛；DCF 做错不如不做 |
| Benchmark | 末尾补 | P0 贯穿（CARD-11，三级测试集 24 指标） | 指标与阈值随模块同步建立，不是事后装饰 |
| 产业链 | P1 | P3（CARD-21，重设四量数学） | 线性加总公式无金融意义；初赛核心链路不受影响 |

### 2.6 检索与证据逻辑修正

**修改**：`Corpus 建索引时给所有 chunk 创建 Evidence` → 只有被 Claim 引用的 chunk 才入 Evidence Ledger；引用区分 quote/paraphrase/inference 三型。
**理由**：chunk≠evidence。把索引条目登记为证据会稀释证据体系，导致"证据覆盖率"指标失真。

### 2.7 Claim 三级提升到句子级

**修改**：fact/inference/opinion 从 Section 级标注提升为 Claim 级（claim_type/evidence_ids/derived_from/validation_status）。
**理由**：竞赛明确考察"事实、推论、观点区分"——段落级标注回答不了"这句话依赖哪些事实"。

### 2.8 新增顶层文档

- `COMPETITION_REQUIREMENTS_MATRIX.md`：竞赛要求→模块→状态→卡片→验收→Demo 体现的逐行映射；阈值纪律"待 baseline 冻结，禁止编造 95%/98%"。
- `ARCHITECTURE_V2.md`：竞赛版端到端架构、7 个核心数据模型、模块路径规划。
- `DEMO_FLOW.md`：5 分钟 Demo 主故事（11 步）+ 8 处错误注入清单 + 7 个失败注入场景 + 答辩预演。
- `THIRD_PARTY_NOTICES_PLAN.md`：依赖合规计划（License 一律待核实，禁止复制未核实信息；AGPL 隔离为可选依赖）。

### 2.9 卡片统一为 20 字段

目标 / 对应竞赛评分点 / 为什么需要 / 输入 / 输出 / 数据模型 / API 契约 / 金融逻辑 / Edge Cases / Failure Mode / Validator rules / Unit tests / Integration tests / Benchmark / Demo method / 验收标准 / 依赖 / 复杂度 / 优先级 / 初赛决赛阶段。
**理由**：让另一个 coding agent 拿单卡即可独立实现，不需要回看全局猜业务逻辑。

## 3. 旧卡 → 新卡映射表

| v2 旧卡 | v3 去向 | 处置说明 |
|---|---|---|
| 01_workbench_split | CARD-15（demo_ui） | 全量拆分 → 最小增量 11 页，禁止重写 |
| 02_unified_task_system | CARD-07（部分）+ 现有服务层保留 | 任务记录职责由 Run Manifest 承接；进程内任务系统不再扩展 |
| 03_snapshot_catalog | 不单列卡 | snapshot 能力保留，契约并入 MASTER_PLAN 统一契约节 |
| 04_fundamentals | CARD-03（financial_analysis） | 指标体系重写：14 指标 + 4 类诊断信号 + 状态迁移 |
| 05_dcf_valuation | CARD-16（P2 决赛） | EV 桥修正后降级 |
| 06_report_checker | CARD-05（report_checker） | 结构化 JSON 输入 → 自然语言草稿 + LLM Claim 提取升级 |
| 07_report_scorer | CARD-17（quality_diagnostics） | 加权总分删除，改零权重 10 维诊断 |
| 08_multiagent_orchestrator | CARD-18（P2） | 强制消融四问 |
| 09_bull_bear_debate | CARD-19（P3） | bull/bear score 公式删除，改六产物对照 |
| 10_buy_side_memo | CARD-10 | 解除 Multi-Agent 强依赖，输入改为分析/估值/检索/核查/信号 |
| 11_document_parser | CARD-01（document_intelligence） | 质押/中标窄范围 → 8 类输入 Document Intelligence Layer |
| 12_industry_chain | CARD-21（P3） | 线性加总 → cost_share/pass_through/exposure/elasticity 四量 |
| 13_benchmark_ablation | CARD-11（P0 贯穿） | 提前到第一模块起建，三级测试集 24 指标 |
| 14_skill_prompt_assets | CARD-14（prompt_registry） | PromptSpec 五字段；Skill 去空壳 |
| 15_mcp_server | CARD-20（P3） | 入场合条件 + 版本固定 + offline fallback |
| 16_retrieval | CARD-06（retrieval） | chunk/evidence 分离 + 引用三型 |
| （无旧卡） | CARD-02/04/07/08/09/12/13 | 新增：规范化 / 口径检测 / Run Manifest / 相对估值增强 / 证据图谱 / 证据包重放 / 冲突消解 |

## 4. 时间线与纪律变化

- 六窗口排期：9/16–9/22 文档智能与基建 → 9/23–9/29 规范化与诊断 → 9/30–10/6 研报核查 → 10/7–10/11 估值/图谱/备忘录 → 10/12–10/15 benchmark/失败注入/Evidence Pack → 10/16–10/18 冻结与提交。
- **10-15 起硬性 Code Freeze**：此后禁止新功能，仅 bug fix、计划书、5 分钟视频、安装复现。
- 新增红线：初赛窗口内禁止因 P2/P3 功能导致 P0 不稳定（写入 MASTER_PLAN 十一条红线）。

## 5. 未变更事项（明确保留）

Evidence Ledger、Validator、Point-in-Time/available_at、Snapshot Provider、确定性 Python 金融计算、fail-closed 原则、复现信息记录、Agent Tool Contract、离线测试体系、FastAPI + Streamlit 技术栈，全部原样保留并继续作为系统底座。
