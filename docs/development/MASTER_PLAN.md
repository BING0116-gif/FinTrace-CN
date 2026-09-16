# FinTrace-CN 竞赛版开发总指挥（MASTER PLAN v3.0）

> 本文档是 FinTrace-CN 面向 2026 年北京市大学生金融人工智能竞赛的唯一进度真相源（single source of truth）。
> 所有模块开发以 `docs/development/cards/` 下的任务卡（CARD）为执行单元。执行任何卡片前，必须先阅读本文档第 8、9、10、11 节。
> 上位规则：`AGENTS.md`（工作区级，永远优先于本文档）。

- 版本：v3.2（编码前冻结版，全量替代 v3.1）
- 制定日期：2026-09-16
- 双赛：华北五省计算机设计大赛 + 北京市大学生金融人工智能竞赛（叙事定位见 DUAL_COMPETITION_POSITIONING.md）
- 初赛提交截止：2026-10-18（项目计划书 PDF + ≤5 分钟视频）
- **Code Freeze：2026-10-15 之后禁止加入任何重大新功能，只允许 bug fix 与材料准备**
- 决赛：2026-11 月底

**v3.2 修订说明**：把创新体系正式 CARD 化并融入现有架构。核心变更：①创新能力与现有 CARD 逐项重叠检查（优先扩展、禁止重复建设）；②创新一升级为 **ACME**（Accounting-Constrained Multimodal Evidence Engine，六类约束族，CARD-22）；③创新二改名 **Financial Claim Passport**（对外"金融AI结论护照"，新增 `verify_claim()` 五态验证，CARD-23）；④Thesis Fragility 升级为确定性图算法引擎（CARD-24）；⑤Temporal Revalidation 升级（version lineage + 三态区分 + 增量重算，CARD-25）；⑥FinFuzz 明确为测试框架并集成 Benchmark（CARD-26 + CARD-11）；⑦Controlled Environment Guard 并入 CARD-01（不单独做卡）；⑧Cross-source reconciliation 扩展 CARD-13、dependency semantics/Thesis 扩展 CARD-09；⑨新增 DUAL_COMPETITION_POSITIONING.md。全部创新卡升级为 22 字段。

---

## 0. 主链（整个文档体系的核心，先看这里）

```text
真实金融文档（年报 / 半年报 / 季报 / 公告 / 研报草稿）+ Snapshot Provider
  ↓ ① Document Intelligence     文档注册 / 解析 / 证据定位 / Controlled Environment Guard（CARD-01）
  ↓ ② Financial Normalization   单位 / 币种 / 期间 / 口径 / flow-stock 语义（CARD-02）
  ↓ ③ ACME Constraint Layer     六类约束族：检测+定位+阻断（CARD-22，创新一）
  ↓ ④ Evidence                  point-in-time，带文档页码 / bbox / available_at
  ↓ ⑤ Deterministic Financial Tools   确定性 Python 金融计算
  ↓ ⑥ Financial Diagnostics     YTD→单季化 / 盈利状态迁移 / 诊断信号
  ↓ ⑦ Claim Extraction + Report Checking   fact/inference/opinion 三级，13 类错误核查
  ↓ ⑧ Valuation                  相对估值 + Bear/Base/Bull 敏感性
  ↓ ⑨ Financial Claim Passport  关键结论 → FPO → verify_claim() 五态（CARD-23，创新二）
  ↓ ⑩ Claim-Evidence / Thesis Graph   结论 → 计算 → 证据 → PDF 页 + 依赖语义（CARD-09）
  ↓ ⑪ Fragility Engine          关键依赖 / 最小割集 / Monitoring Plan（CARD-24，创新三）
  ↓ ⑫ Investment Memo            买方投资备忘录
  ↓ ⑬ Validator（fail-closed）   证据不足 / 冲突 / 口径不一致 → 降级或阻断
  ↓ ⑭ Temporal Revalidation     version lineage + 三态 + 增量重算（CARD-25，创新三）
  ↓ ⑮ Evidence Pack + Audit Replay     可交付证据包 / 可重放审计
（系统外部）FinFuzz 对整个 Pipeline 对抗评测（CARD-26 + CARD-11）
```

**核心价值主张**：任何重要金融数字都有来源，任何重要结论都有证据链，所有计算均可复核；当证据不足、数据冲突或口径不一致时，系统主动降级或阻断结论。FinTrace 不只证明"正确的时候能跑"，更证明"**错误的时候知道自己不能下结论**"。

## 1. 竞赛定位（收敛，不再追求全覆盖）

> **双赛同构**：同一套代码同时参加华北五省计算机设计大赛与北京市大学生金融人工智能竞赛，叙事不同但功能同一。定位细节见 `DUAL_COMPETITION_POSITIONING.md`。本节按北京赛赛题映射（主基线），华北五省按"AI Agent + 多模态 + 约束推理 + 图算法 + 增量计算 + 对抗测试"主线包装。

| 角色 | 赛题 |
|---|---|
| 主方向 | 赛题2 上市公司财务报告分析 |
| 第二核心 | 赛题5 研究报告纠错核查 |
| 最终业务输出 | 赛题6 买方投资备忘录编制 |
| 重要金融工具 | 赛题4 自动化估值建模（初赛=相对估值+敏感性；DCF 决赛） |
| 内部评价机制 | 赛题7 研究报告质量评估（诊断维度制，非虚构权重评分） |
| 升级为系统能力 | 赛题1 → Document Intelligence Layer（全系统数据入口，不独立卖点） |
| 暂缓 | 赛题3 产业链 → P3 决赛可选，不得影响初赛核心链路 |

**禁止**：为了"多 Agent、MCP、Skill、DCF"等技术名词过度工程化；为了覆盖七个赛题堆功能。

## 2. 必须保留的现有资产（不得推翻）

1. Evidence Ledger（证据账本）
2. Validator 体系（financial / research gate / report）
3. Point-in-Time / available_at 设计
4. Snapshot Provider（版本化快照）
5. 确定性 Python 金融计算（相对估值 PE/PB/PS + IQR 离群剔除）
6. fail-closed 原则
7. 复现信息（prompt / model / git commit / snapshot 指纹）
8. Agent Tool Contract（status: ok|error 信封）
9. 测试体系（离线、不依赖 .env / 网络 / 墙钟）
10. `benchmarks/cn_agent_v1.json` + benchmark/real_benchmark/ablation 基础设施

## 3. LLM 边界契约（所有卡片共同遵守）

LLM **可以**：理解任务；制定研究计划；选择工具；从自然语言提取结构化 Claim；检索和综合证据；生成推论；组织报告。

LLM **不允许**：凭空创造金融数据；自己完成最终财务算术并作为事实来源；绕过 deterministic calculation；自行创建未经来源绑定的 Evidence；绕过 Validator；修改验证结果；将 inference 冒充 fact。

## 4. 优先级定义与竞赛阶段

- **P0**：直接影响竞赛核心闭环和现场真实输入能力 → 初赛版
- **P1**：显著提高金融专业度、技术深度和展示效果 → 初赛版（时间不足时按第 5 节顺序裁剪）
- **P2**：决赛增强项
- **P3**：锦上添花，不能影响主链交付

**初赛版锁定范围**（10-18 前必须稳定）：真实文档输入、财务解析、Evidence、财务分析、研报纠错、相对估值、Investment Memo、Validator、Audit Trail、Real Benchmark、稳定 Demo + **创新 P0**：ACME 基础约束族（CARD-22）、Financial Claim Passport + verify_claim（CARD-23）、REQUIRED dependency propagation（CARD-09）。

**决赛版增强**（11 月中旬后）：DCF、Multi-Agent、OCR 强化、复杂 Retrieval、MCP、Industry Chain、完整质量评估、Fragility/Temporal 完整实现、FinFuzz 完整 operator 集。

## 5. 开发时间表（严格执行，10-15 起 Code Freeze）

**排期原则**：全部 26 卡自估 88+ 人日（v3.2 核算，见下）；学生非全职 ≈ 21 个工作日到 10-15。以下排期是**砍超载窗口后的可行版本**——原窗口 5（8–10 人日）已按 4 条并行 Track 摊薄。

**v3.2 新增**：22/23 为 P0 创新核心卡，必须进入初赛关键路径；24/25/26 为 P1 创新增强卡，按并行工作流穿插；11 含 FinFuzz 集成与全创新 ablation。

| 窗口 | 内容 | 卡片 | 说明 |
|---|---|---|---|
| 9/16–9/22（7d） | Document Registry、PDF/表格解析、证据定位、Run Manifest、**Controlled Environment Guard** | **01, 07**（11 同步启动） | Guard 并入 01，不单独排卡 |
| 9/23–9/29（7d） | Financial Normalization（**桥接现有引擎，不重写**）、YTD→单季/TTM 推导、YoY/QoQ、诊断引擎、Accounting Scope、**ACME 基础约束族（F1–F4）** + **Retrieval 基础** | 02, 03, 04, **06**, **22（F1–F4）** | 22 只需 01/02；F5/F6（跨源/跨模态）放入 9/30–10/6 或与 13 联动 |
| 9/30–10/6（7d） | 自然语言研报 → Claim Extractor → Deterministic Checker → 纠错报告、**ACME F5/F6** | 05, **22（F5/F6 后半）** | 05 是主链核心，22 后半不占 05 关键路径 |
| 10/7–10/11（5d） | 相对估值 + 敏感性、Investment Memo、Claim-Evidence Graph、**Financial Claim Passport 基础版** | 08, 09, 10, **23** | 23 依赖 09，与 10 并行 |
| 10/12–10/15（4d） | Real benchmark 收口（**1 家 Demo 公司全链 + 2 家抽查 + 2 家 holdout**）、Failure Injection 场景脚本化、**Evidence Pack 导出（简化版）**、**Thesis Fragility 基础版**、**Temporal Revalidation 基础版**、**FinFuzz 基础版（集成 CARD-11）** | 11（含 ablation）, **12（简化版）**, **24**, **25**, **26** | **Conflict 完整实现 / Replay UI / 24·25·26 完整实现移入决赛缓冲**（若窗口超载） |
| 10/16–10/18（3d） | Bug fix、Demo freeze、陌生公司演练、计划书、5 分钟视频、安装复现测试 | — | 必须演练：陌生公司 PDF 解析 + 断网演示 |

贯穿性卡片：11（基准从第一个模块起持续建设）、15（UI 增量随各卡落地）、14（Prompt Registry 随 LLM 功能落地）。

### 5.1 并行工作流（v3.2 核算，4 条 Track）

**Track A：Document / Normalization / ACME**
- 卡片：01 → 02 → 22 → 04
- 预估人日：6 + 5 + 6 + 3 = 20 人日（22 升级 ACME 六类约束族 +3）
- 关键路径：01（7d）→ 02（7d）→ 22（7d）→ 04（7d）

**Track B：Financial Analysis / Checker / Valuation**
- 卡片：03 → 05 → 08
- 预估人日：5 + 7 + 4 = 16 人日
- 关键路径：03（7d）→ 05（7d）→ 08（10/7-10/11）

**Track C：Graph / Passport / Fragility / Temporal**
- 卡片：09 → 23 → 24 → 25
- 预估人日：6 + 4 + 4 + 5 = 19 人日（23 五态验证 +1，24 cut-set +2，25 增量重算 +3）
- 关键路径：09（10/7-10/11）→ 23（10/7-10/11）→ 24/25（10/12-10/15）

**Track D：Benchmark / FinFuzz / UI / Demo / Submission**
- 卡片：11（含 ablation）→ 12 → 26 → 15 → 14
- 预估人日：8 + 4 + 4 + 4 + 1.5 = 21.5 人日（11 含 FinFuzz 集成 2 + ablation 1）
- 关键路径：11（贯穿）→ 12（10/12-10/15）→ 26（10/12-10/15）→ 15（贯穿）→ 14（贯穿）

**如果实际团队只有 3 名核心开发者**：Track C 和 Track D 合并，24/25 降为决赛增强（或只做 24 critical dependency），26 简化为 5 个核心 operator。

### 5.2 Critical Path 与 Code Freeze

**Critical Path**：01 → 02 → 03 → 05 → 08 → 09 → 10 → 12 → Demo Freeze（创新支线 22/23 并行于主链，不延长主链）

**Code Freeze Date**：2026-10-15 23:59
- 此后禁止新功能
- 仅允许：bug fix、计划书、5 分钟视频、安装复现测试、Demo 演练

### 5.3 工作量核算（v3.2 Scope Check）

| 分组 | 卡片 | 人日 | 合计 |
|---|---|---|---|
| P0 主链 | 01(6) 02(5) 03(5) 04(3) 05(7) 06(3) 07(3) 08(4) 09(6) 10(4) 11(8*贯穿) 12(4) | — | ~58 |
| P0 创新 | 22(6) 23(4) | — | 10 |
| P1 创新增强 | 24(4) 25(5) 26(4) | — | 13 |
| P1 其余 | 13(2.5) 14(1.5) 15(4) | — | 8 |
| P2/P3 决赛 | 16(5) 17(3) 18(6) 19(2) 20(2) 21(5) | — | ~23 |

**初赛（P0+P1）合计 ≈ 89 人日**（含 11 贯穿分散）。21 个工作日 × ≤3 人并行 ≈ 可承载，但 **P1 增强项（24/25/26/13/06）按裁剪顺序执行**：若窗口超载，优先保证 P0（58+10=68 人日）铁定完成。核心业务闭环 → 创新 P0 嵌入 → Benchmark → Demo → 再增强 的顺序不可颠倒。

## 6. 卡片索引与进度台账

> 规则：完成一张卡 → "状态"列打 `[x]`，卡内"执行备注"写入 commit 范围与偏差记录。

| 编号 | 卡片 | 优先级 | 阶段 | 赛题 | 依赖 | 状态 |
|---|---|---|---|---|---|---|
| 01 | [Document Intelligence Layer](cards/CARD-01_document_intelligence.md) | P0 | 初赛 | 1(入口) | 无 | ☐ |
| 02 | [Financial Normalization Engine](cards/CARD-02_financial_normalization.md) | P0 | 初赛 | 2 | 01 | ☐ |
| 03 | [Financial Analysis Engine](cards/CARD-03_financial_analysis.md) | P0 | 初赛 | 2 | 02（04 为可选增强信号） | ☐ |
| 04 | [Accounting Scope & Restatement](cards/CARD-04_accounting_scope.md) | **P0** | 初赛 | 2 | 01, 02 | ☐ |
| 05 | [Report Claim Extractor & Checker](cards/CARD-05_report_checker.md) | P0 | 初赛 | 5 | 02, 04 | ☐ |
| 06 | [Retrieval Engine](cards/CARD-06_retrieval.md) | P0 | 初赛 | 链路① | 01 | ☐ |
| 07 | [Run Manifest & Audit Trail](cards/CARD-07_run_manifest.md) | P0 | 初赛 | 竞赛硬性 | 无 | ☐ |
| 08 | [Relative Valuation & Sensitivity](cards/CARD-08_relative_valuation.md) | P0 | 初赛 | 4 | 02, 07 | ☐ |
| 09 | [Claim-Evidence Graph](cards/CARD-09_claim_evidence_graph.md) | P1 | 初赛 | 核心创新 | 01, 03, 07 | ☐ |
| 10 | [Investment Memo](cards/CARD-10_investment_memo.md) | P0 | 初赛 | 6 | 03, 05, 06, 08, 09 | ☐ |
| 11 | [Real-world Benchmark](cards/CARD-11_real_benchmark.md) | P0 | 贯穿 | 7 | 无（持续） | ☐ |
| 12 | [Evidence Pack & Audit Replay](cards/CARD-12_evidence_pack_replay.md) | P1 | 初赛 | 竞赛硬性 | 07, 09 | ☐ |
| 13 | [Source Conflict Resolver](cards/CARD-13_source_conflict.md) | P1 | 初赛 | 2/5 | 01, 04 | ☐ |
| 14 | [Prompt Registry](cards/CARD-14_prompt_registry.md) | P1 | 初赛起 | 竞赛模块清单 | 07 | ☐ |
| 15 | [Workbench Demo UI 增量](cards/CARD-15_demo_ui.md) | P1 | 贯穿 | 现场展示 | 各业务卡 | ☐ |
| 16 | [DCF 完整实现（修正版）](cards/CARD-16_dcf_valuation.md) | P2 | 决赛 | 4 | 08, 02 | ☐ |
| 17 | [Report Quality Diagnostics](cards/CARD-17_quality_diagnostics.md) | P2 | 决赛 | 7 | 05, 09, 12 | ☐ |
| 18 | [Multi-Agent 编排（含消融）](cards/CARD-18_multiagent.md) | P2 | 决赛 | 6 | 全主线 | ☐ |
| 19 | [Bull/Bear 结构化对照](cards/CARD-19_bull_bear.md) | P3 | 决赛 | 6 | 18 | ☐ |
| 20 | [MCP Server](cards/CARD-20_mcp_server.md) | P3 | 决赛 | — | 工具面稳定 | ☐ |
| 21 | [Industry Chain（重设数学）](cards/CARD-21_industry_chain.md) | P3 | 决赛 | 3 | 08 | ☐ |
| 22 | [ACME（会计约束驱动的多模态证据理解引擎）](cards/CARD-22_acme_multimodal_evidence.md) | **P0** | 初赛 | 2/5（创新一） | 01, 02, 13 | ☐ |
| 23 | [Financial Claim Passport & Proof Verifier（金融AI结论护照）](cards/CARD-23_claim_passport_verifier.md) | **P0** | 初赛 | 全链路（创新二） | 09, 07, 13 | ☐ |
| 24 | [Thesis Fragility Engine（投资逻辑脆弱性分析）](cards/CARD-24_thesis_fragility_engine.md) | **P1** | 初赛增强 | 6（创新三） | 09, 23 | ☐ |
| 25 | [Temporal Revalidation Engine（时间重验证引擎）](cards/CARD-25_temporal_revalidation_engine.md) | **P1** | 初赛增强 | 2/5（创新三） | 09, 13, 24 | ☐ |
| 26 | [FinFuzz（金融语义对抗错误生成与压力测试）](cards/CARD-26_fin_fuzz.md) | **P1** | 初赛增强 | 7（评测创新） | 05, 09, 11 | ☐ |

**工程暂缓项**（赛后处理，不设卡）：workbench.py 全量拆分（仅允许 CARD-15 最小增量）、统一任务队列 SQLite 化（Run Manifest 已覆盖可复现需求）、快照 Catalog（Document Registry 优先）。

## 7. 依赖关系与执行顺序

```text
01 文档智能 ──→ 02 规范化 ──→ 04 口径 ──→ 03 财务分析 ──→ 10 备忘录
    │              │                         ↗ 08 相对估值 ↗
    │              └──→ 05 纠错 ──────────→ 10
    │              └──→ 22 ACME（六类约束）──→ 23 Claim Passport ──→ 24 脆弱性 ──→ 25 时间重验证
    ├──→ 06 检索 ─────────────────────────→ 10
07 Run Manifest ──→ 09 图谱 ──→ 12 证据包/回放
                 └──→ 23 Passport ──→ 24 脆弱性 ──→ 25 时间重验证
13 冲突/三态（依赖 01/04/22 跨源分类）──→ 25 时间重验证
11 基准（贯穿，从 01 起每卡配套；含 FinFuzz 集成与 ablation）
14 Prompt Registry（随 05/10 落地）  15 UI（随各业务卡）
26 FinFuzz（依赖 05/09/11，贯穿评测）
决赛链：08→16 DCF；09/12→17 诊断；主线→18 多智能体→19 辩论；21 产业链
```

单人串行推荐：**01 → 07 → 02 → 22 → 04 → 03 → 06 → 05 → 08 → 09 → 23 → 24 → 25 → 10 → 11 贯穿 → 12（简化版）→ 13 → 14/15 贯穿 → 26 贯穿**。
时间不足时裁剪顺序（从后往前砍）：13（Conflict 完整实现先砍，简化为"记录冲突+阻断"最小版）→ 25（Temporal 基础版先发电统一期还需 24）→ 24（Fragility 降决赛）→ 06（检索降级为标题关键字匹配）→ 26（FinFuzz 缩为 5 个核心 operator）。
**不可裁剪清单**：01/02/03/04/05/07/08/**09**/10/**22**/**23**。09 是"结论→证据→PDF 页回溯"的骨架，22 是 ACME 会计约束驱动的多模态质量控制（创新一），23 是 Financial Claim Passport（创新二），砍掉等于砍掉系统核心创新与差异化，**绝不可裁**。

决赛缓冲（初赛窗口 5 超载时的自动转移）：13 Conflict 完整实现、12 Audit Replay UI、CARD-20 全部能力、24/25 完整实现、26 完整 operator 集 → 决赛前 2 周内补。

## 8. 卡片执行协议（Agent 使用说明）

1. **一次只执行一张卡**。开工前按顺序读：`AGENTS.md` → 本文件第 9/10/11 节 → `ARCHITECTURE_V2.md` → 目标卡片全文。
2. 卡片是规格，不是死板脚本：与代码现状不符时以现状为准做最小合理调整，并在"执行备注"记录偏差。
3. 严格按卡内实施步骤推进；"验收标准"全项达成前不得声称完成。
4. **Skill 加载要求**：涉及 `src/cn/` 数据摄取/证据/估值/报告事实的卡片先加载 `financial-data-provenance` skill；涉及工具契约注册的先加载 `financial-tool-contract` skill；涉及评测设计与基准的先加载 `financial-agent-evaluation` skill。
5. 完成后：跑第 12 节验证命令 → 卡内状态打 `[x]` → 台账同步 → commit（遵循仓库既有风格）。
6. **禁止跨卡顺手改动**。发现别的问题记录到"执行备注"，留给对应卡片。
7. 每张卡完成后系统必须处于全测试通过的可运行状态。

## 9. 统一工程契约

### 9.1 Claim 契约（v3.1 修正：claim_type 与 temporal_status 分离、verification_status 取代 confidence 数值、依赖语义 REQUIRED/SUPPORTING/OPTIONAL）

```python
@dataclass
class Claim:
    claim_id: str
    claim_type: str              # fact | inference | opinion（认识论维度）
    temporal_status: str         # historical | current | forward_looking（时间维度）
    text: str
    evidence_ids: list[str]      # fact 必须直接绑定
    calculation_ids: list[str]   # 有计算的 claim 绑定 Calculation
    assumption_ids: list[str]    # opinion 必须标注假设来源
    derived_from: list[str]      # inference 必须能追踪依赖的 fact claim_id
    dependency_metadata: list[dict]  # [{role: REQUIRED|SUPPORTING|OPTIONAL, target_id}]
    verification_status: str     # EXACT_MATCH | ROUNDING_MATCH | NORMALIZED_MATCH | PERIOD_INFERRED | CONFLICTED | UNVERIFIABLE
    validation_status: str       # pending | supported | unsupported | blocked
    rationale: str | None        # 可选，推理依据说明
```

**v3.1 核心修正**：
- **claim_type 与 temporal_status 分离**：fact/inference/opinion 是认识论维度；historical/current/forward_looking 是时间维度。valuation 作为 claim subtype / domain，不与 fact/inference/opinion 混成同一 enum
- **verification_status 取代 confidence 数值**：删除没有校准依据的 0.8/0.9/1.0 confidence，改为离散状态。如果未来需要 numerical confidence，必须有 calibration 方法
- **依赖语义 REQUIRED/SUPPORTING/OPTIONAL**：REQUIRED 上游 blocked → 下游 blocked；SUPPORTING 失效 → coverage 降级但不自动 blocked；OPTIONAL 不影响核心有效性
- **因果 Claim 三级区分**：explicit_attribution（原文明确说明）/ analyst_inference（有证据但因果是推断）/ unsupported_causal（证据不足）

fact 必须直接绑定 Evidence；inference 必须能追踪其依赖的 Fact；opinion 必须明确假设或主观判断来源。

### 9.2 证据契约

- 事实只来自 Document Registry 的文档抽取或 Snapshot Provider；LLM 文本永不作为事实来源
- 文档型证据必须带 document_id + page（+ bbox）；快照型证据带 snapshot_id + available_at
- 市值与同业估值计算使用 RAW 价格
- 缺失/过期/混期间/混单位/口径冲突：拒绝、降级或显式标注，绝不静默填充

### 9.3 工具契约

新工具注册于 `src/agents/tools/cn_tools.py`，沿用现有信封：`status: ok | error`、error_code、事实字段带 evidence_id/as_of/unit/period。工具内不调用 LLM（编排层除外且留轨迹）。

### 9.4 检索与引用契约（修正 v2 错误）

- chunk_id ≠ evidence_id：**只有真正用于支持 Claim 的 chunk 才进入 Evidence Ledger**
- 引用三型：quote（逐字一致，校验器强制）、paraphrase（允许重述但必须绑定原始 chunk）、inference（允许组合但必须标记）
- 检索命中文本只能被逐字引用；其中的数字不得直接进入结论，必须走数值校验路径

### 9.5 测试纪律

默认测试离线、不依赖 `.env`/网络/墙钟。新模块配套 `tests/test_cn_<module>.py`。确定性模块的测试用手工商可验的封闭数值。集成测试标 `@pytest.mark.integration`。

## 10. 红线（违反即回滚）

1. 不用 LLM 做可以由 Python 精确计算的金融算术
2. 不编造评分权重；不编造 benchmark 结果；不把 synthetic 结果描述成真实表现
3. 不直接对 YTD 财报数计算季度 QoQ（必须先 `convert_ytd_to_single_quarter`）
4. 不忽略单位和会计口径；不把 retrieval chunk 全部登记成 Evidence
5. 不把 inference 写成 fact；不无来源输出确定因果关系
6. 不因官方出现 Tool/Skill/MCP 字样就强制实现所有概念
7. 不大规模重写 UI（Streamlit + FastAPI 够用）；不迁移 React/微服务/K8s
8. 不破坏现有稳定能力；不引入 MongoDB/Redis/LangGraph
9. `data/`、`output/`、`.env`、付费数据、真实公告年报 PDF 原文不入 Git
10. 不复活已移除的美股/加密/预测市场/旧 supervisor 代码
11. 10-15 后禁止重大新功能（Code Freeze）

## 11. 反向检查（每张 P0 卡完成后、每次 Demo 冻结前逐项过）

| # | 问题 | 对应 |
|---|---|---|
| 1 | 能直接处理一份此前从未见过的真实 A 股年报？ | CARD-01/02 |
| 2 | 能处理自然语言研报草稿，而非仅预结构化 JSON？ | CARD-05 |
| 3 | 能正确处理 A 股累计季度数据？ | CARD-02/03 |
| 4 | 能区分合并口径和母公司口径？ | CARD-02/04 |
| 5 | 能检测更正/重述？ | CARD-04/13 |
| 6 | 能追踪一个数字到原始 PDF 页？ | CARD-01/09 |
| 7 | 能追踪一个结论到多个 Evidence？ | CARD-09 |
| 8 | 能追踪一个推论依赖哪些事实？ | CARD-09 |
| 9 | 能在 Evidence 缺失时阻断 Claim？ | CARD-09/Validator |
| 10 | 能重放一次历史任务？ | CARD-07/12 |
| 11 | 能证明最终结果不是仅由 LLM 生成？ | CARD-07/12 |
| 12 | 有真实数据 benchmark？ | CARD-11 |
| 13 | 同时测 Precision / Recall / False Positive？ | CARD-11 |
| 14 | 有完全离线或半离线可复现路径？ | 现有测试体系 |
| 15 | 能在 5 分钟内向评委证明核心价值？ | DEMO_FLOW.md |

任何一问答"不能"且属于 P0 → 回开发计划补齐。

## 12. 每卡通用验证命令

~~~powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
python scripts/smoke_workbench.py
git diff --check
git status --short
~~~

涉及 UI 的卡片额外人工检查：运行 workbench，浏览器控制台无报错，对照原页面确认无回归。
