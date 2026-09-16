# CHANGELOG.md — 开发文档体系变更记录

> 版本：v2.0 → v3.0 → v3.1 → v3.2 编码前冻结版 ｜ 变更日期：2026-09-16

---

## v3.2 编码前冻结版（2026-09-16）——创新体系正式 CARD 化

### 变更定位

把 v3.1 的四大创新体系**正式转化为可开发、可测试、可验收的 CARD，并融入现有架构**。本轮不是简单新增创新卡，而是先做创新能力与现有 CARD 的逐项重叠检查，**优先扩展已有 CARD，禁止重复建设**。

### 一、合并与扩展决策（为什么没新增重复卡）

| 创新能力 | 决策 | 理由与落点 |
|---|---|---|
| 会计恒等/表格结构/期间约束 | 升级 CARD-22 为 ACME | 独立数据结构（ConstraintViolation/IntegrityReport）+ 算法 + 测试体系 → 保留独立卡；调用 CARD-01/02 与现有 FinancialPeriodEngine，**不重复实现 period logic** |
| Cross-source reconciliation | 扩展 CARD-13 + CARD-22 F5 | 检测分类留在 ACME（MATCH/ROUNDING_MATCH/CONFLICT/NOT_COMPARABLE），**裁决职责扩展进 CARD-13**（三态区分） |
| Cross-modal consistency | 并入 CARD-22 F6 | 无独立模块，作为 ACME 约束族之一 |
| Financial Claim Passport / verify_claim | 升级 CARD-23 | 保留独立卡（对象序列化 + 五态验证器有独立算法）；与 CARD-09（Claim 模型）/Validator/Audit（CARD-07）集成，**不重复造 Claim 模型** |
| Claim 依赖语义 REQUIRED/SUPPORTING/OPTIONAL | 扩展 CARD-09 | 已建立 dependency_metadata 契约（MASTER_PLAN §9.1），本版把传播规则细化入 CARD-09 §7b + Thesis 数据模型 |
| Thesis model / minimal cut set | 升级 CARD-24 | 建立在 CARD-09 Claim Graph 之上，图算法独立 → 独立卡 |
| Version lineage / 三态 / 增量重算 | 升级 CARD-25 | 独立引擎 + 与 CARD-13 三态/裁决联动 |
| FinFuzz | 升级 CARD-26 + 集成 CARD-11 | **明确为测试框架**；集成进 Benchmark（per-error-type 指标 + ablation），不与业务主链重复 |
| Controlled Environment Guard | **并入 CARD-01（不单独做卡）** | 指令明确"可以并入 Document Intelligence 和 Agent Orchestration CARD，不必单独做大 CARD" |
| 双赛定位 | 新增 DUAL_COMPETITION_POSITIONING.md | 同一技术两套叙事，单独成文 |

### 二、CARD 变更清单

| CARD | 原名称（v3.1） | 新名称（v3.2） | 变化 |
|---|---|---|---|
| 22 | Accounting Integrity Validator（ACEE） | **ACME**（Multimodal Evidence Engine） | 六类约束族 + tolerance policy + 跨源四分类 + 跨模态，升级 22 字段 |
| 23 | Financial Proof Object / Verifier（PCIR） | **Financial Claim Passport & Proof Verifier** | 对外名"金融AI结论护照"；verify_claim() 五态（VERIFIED/DEGRADED/STALE/BLOCKED/CONFLICTED）；6 项 proof；升级 22 字段 |
| 24 | Thesis Fragility Map | **Thesis Fragility Engine** | Thesis 模型、minimal cut set、numeric fragility（阈值白名单）、Monitoring Plan；升级 22 字段 |
| 25 | Temporal Revalidation | **Temporal Revalidation Engine** | Version Lineage 四态、三态区分、affected-subgraph 增量重算、impact analysis；升级 22 字段 |
| 26 | FinFuzz | **FinFuzz（Adversarial Financial Benchmark）** | 10 类 operator + per-error-type 指标 + extractor/checker 区分 + CARD-11 集成；升级 22 字段 |
| 01 | Document Intelligence Layer |（保持）| 新增 §9b Controlled Environment Guard（内容隔离/注入防护/路径拦截/禁外网） |
| 09 | Claim-Evidence Graph |（保持）| Claim 加 dependency_metadata/temporal_status/verification_status；新增 Thesis 数据模型；§7b 依赖传播规则表 |
| 11 | Real-world Benchmark |（保持）| 新增对抗组指标（FinFuzz 集成）+ §7b 全创新 ablation 表 |
| 13 | Source Conflict Resolver |（保持）| 新增 §7b 三态区分（DATA_CONFLICT/VERSION_SUPERSESSION/NEW_INFORMATION）+ ACME 四分类裁决责任 |

### 三、其他文档变更

- **ARCHITECTURE_V2.md**：v3.2 版头 + 新叙事（"面向 A 股投研的多模态可验证与可证伪金融智能体"）；§1 主链加入 ACME Constraint Layer / Claim Passport / Fragility Engine / Temporal Revalidation / FinFuzz 外部测试环；§8 全面重写为四创新冻结命名
- **MASTER_PLAN.md**：v3.2 修订说明；卡片索引 22–26 更名；依赖图更新；排期窗口更新（ACME F1–F4 / F5–F6 分段）；§5.3 工作量核算（初赛 ≈89 人日，P0 68 人日铁定完成优先级）
- **COMPETITION_REQUIREMENTS_MATRIX.md**：创新行更新为 ACME / Passport / Fragility / Temporal / FinFuzz + ablation
- **DEMO_FLOW.md**：4b 改名 ACME；7b 升级为 Claim Passport + **VERIFY CLAIM**（五态）；F9 更新为增量重算 impact；创新总结表 5 行；答辩表新增"VERIFY CLAIM 不经过 LLM"问答
- **INNOVATION_DESIGN.md**：命名冻结（ACME/Passport）；ACME 六类约束族机制；verify_claim 五态；FinFuzz E2 示例修正（31,000 亿元量级错误）
- **DUAL_COMPETITION_POSITIONING.md（新增）**：双赛同构叙事

### 四、工作量与冻结点（Scope Check 结论）

- 初赛（P0+P1）≈ 89 人日；4 条并行 Track（A 20 / B 16 / C 19 / D 21.5）
- 不可裁剪：01/02/03/04/05/07/08/09/10/22/23（P0 68 人日铁定完成）
- 裁剪顺序：13 → 25 → 24 → 06 → 26
- Code Freeze 不变：2026-10-15

---

## v3.1 编码前冻结版（2026-09-16）

### 变更总览

| 维度 | v3.0 | v3.1 |
|---|---|---|
| 金融数据模型 | source_period/economic_period 未分离；report_type 语义缺失 | 完全分离；report_type×"本报告期"语义映射 |
| Claim 模型 | claim_type 与 temporal_status 混合；confidence 无校准 | claim_type（fact/inference/opinion）与 temporal_status（historical/current/forward_looking）分离；verification_status 取代 confidence |
| Evidence/Calculation 边界 | derived values 可误作 Evidence | 明确 derived values 不得作为 Evidence |
| Claim-Evidence Graph | 依赖语义不严格 | REQUIRED/SUPPORTING/OPTIONAL 三级依赖 + 传播规则 |
| 创新体系 | 无系统创新设计 | 四大创新：ACEE / FPO / Thesis Fragility / FinFuzz |
| 新增 CARD | 21 张（01-21） | 26 张（01-26，新增 22-26） |
| Demo 剧本 | 11 步 | 12 步（含 3 个创新展示步骤） |
| 新增顶层文档 | — | INNOVATION_DESIGN.md |

### 金融逻辑与数据模型修正（10 项）

| # | 修正项 | 落点 |
|---|---|---|
| A | report_type×"本报告期"语义映射（annual→FY, semiannual→H1, Q1→Q1 single, Q3→Q3 single） | ARCHITECTURE §3.2 |
| B | source_period 与 economic_period 分离 | ARCHITECTURE §3.2 |
| C | TTM PE 与 Forward/NTM PE 分离 | ARCHITECTURE §3.10 |
| D | 股本字段拆分（shares_outstanding_end / weighted_average_basic / diluted） | ARCHITECTURE §3.8 |
| E | revenue 字段不过度归一化 | ARCHITECTURE §3.9 |
| F | 比率经济意义保护 | ARCHITECTURE §3.11 |
| G | 新增 Financial Statement Integrity Validator | CARD-22 |
| H | 因果 Claim 三级区分（explicit_attribution / analyst_inference / unsupported_causal） | ARCHITECTURE §3.3 |
| I | 删除无校准 confidence，改用 verification_status | ARCHITECTURE §3.3 |
| J | claim_type 与 temporal_status 分离 | ARCHITECTURE §3.3 |

### Point-in-Time 与版本语义修正

| 修正项 | 说明 | 落点 |
|---|---|---|
| available_at / ingested_at 分离 | source_published_at = 文档实际发布时间；ingested_at = 系统摄入时间 | ARCHITECTURE §3.2 |
| conflict 与 supersession 分离 | Conflict = 同期矛盾；Supersession = 新版替代旧版；Restatement = 追溯重述 | ARCHITECTURE §3.16 |

### Evidence/Calculation/Claim 语义边界修正

- derived values 不得作为 Evidence（Evidence 必须来自原始文档或 snapshot）
- Calculation 输入必须引用 Evidence，输出可被其他 Calculation 引用
- Claim 可引用 Calculation 输出作为 derived_from

### Claim-Evidence Graph 改造（fail-closed）

- REQUIRED：缺失则 Claim blocked
- SUPPORTING：缺失则 Claim degraded
- OPTIONAL：缺失不影响 Claim status
- 传播规则：任一 REQUIRED 依赖 blocked → Claim blocked

### 新增 Claim Synthesis Stage

- 在 Claim Extraction 之后、Report Checking 之前
- 合并重复 Claim、解决矛盾 Claim、补充缺失依赖

### 补齐 Parser 与 Source Locator 抽象

- SourceLocator：PDF→page/bbox, Excel→sheet/cell, CSV→row/column, TXT/MD→line_start/line_end
- 所有 ExtractedFact 必须携带 SourceLocator

### Audit Trail / Replay 修正

- Replay 与 Re-execution 分离：Replay = 回放已记录事件；Re-execution = 重新执行
- events.jsonl 增强：新增 event_subtype、previous_hash、event_hash
- tamper-evident hash chain：SHA256(previous_hash + canonical_json(event))

### 补充 PeerSet Methodology

- 可比集选择标准：行业/规模/业务相似度
- 可比集排除规则：ST/*ST、上市不足一年、异常财务
- 可比集有效期：定期复核（季度/半年度）

### 修正与扩展 Benchmark

- 新增 FinFuzz mutation detection 指标
- 新增 FPO verification pass rate
- 新增 Thesis Fragility propagation accuracy
- 新增 Temporal Revalidation latency

### 新增 Controlled Environment Guard

- 禁止外网访问（除白名单 LLM API）
- 禁止写入系统目录
- 禁止执行未授权命令
- 所有文件访问记录 sha256

### 四大创新体系

| 创新 | 痛点 | 技术机制 | CARD |
|---|---|---|---|
| ACEE | 传统 OCR 无法发现"不可能成立"的解析结果 | 会计约束验证 + 异常定位 | CARD-22 |
| FPO | 传统研报结论无法独立验证 | 完整证明链 + 纯确定性验证 | CARD-23 |
| Thesis Fragility | 传统研报无法回答"投资逻辑最依赖什么" | REQUIRED 依赖分析 + 单点依赖检测 | CARD-24 |
| FinFuzz | 传统测试无法系统性检测金融语义错误 | 10 类 mutation suite | CARD-26 |

### 新增 CARD（5 张）

| CARD | 名称 | 优先级 | 阶段 |
|---|---|---|---|
| 22 | Accounting Integrity Validator | P0 | 初赛 |
| 23 | Financial Proof Object / Verifier | P0 | 初赛 |
| 24 | Thesis Fragility Map | P1 | 初赛增强 |
| 25 | Temporal Revalidation | P1 | 初赛增强 |
| 26 | FinFuzz | P1 | 初赛增强 |

### Demo 重设计

- 从 11 步扩展到 12 步
- 新增步骤 4b：ACEE 创新展示（会计约束自检）
- 新增步骤 7b：FPO 创新展示（证明对象验证）
- 新增步骤 10b：Thesis Fragility 创新展示（脆弱性分析）
- 修正 E2 示例：3.1 亿元写成 31,000 亿元（量级错误，非单位错误）
- 新增失败注入 F8（FinFuzz 量级错误）、F9（Temporal Revalidation）

### 工作量与并行开发

- 4 条并行工作流：Track A（数据层）/ Track B（计算层）/ Track C（创新层）/ Track D（展示层）
- Critical Path：01→07→02→22→04→03→06→05→08→09→23→24→25→10→...
- Code Freeze：10-15

---

## v3.0 Competition Edition（2026-09-16）

### 变更总览

| 维度 | v2.0 | v3.0 |
|---|---|---|
| 竞赛定位 | 覆盖全部七个赛题 | 赛题2主方向 + 赛题5第二核心 + 赛题6输出 + 赛题4工具 + 赛题7内评 |
| 主链 | Provider→工具→研报（偏数据管道） | 真实文档→Document Intelligence→Normalization→Evidence→确定性工具→诊断→Claim→核查→估值→图谱→备忘录→Validator→Evidence Pack→Audit Replay |
| 文档结构 | MASTER_PLAN + 16 卡 | MASTER_PLAN + 3 顶层文档（ARCHITECTURE_V2 / COMPETITION_REQUIREMENTS_MATRIX / DEMO_FLOW）+ 21 卡 + THIRD_PARTY_NOTICES_PLAN + CHANGELOG |
| 卡片字段 | 不统一 | 20 个统一字段（目标→竞赛阶段），agent 可独立执行 |
| 金融计算假设 | YTD 直接 QoQ、DCF=股价、区间交并集、A/B/C/D 总分、多空加权评分 | YTD 强制单季换算、EV 桥、分方法展示+dispersion、零权重诊断、零评分对照 |
| 工程取向 | 多 Agent / MCP / Skill / 全量拆分前端为卖点 | 去名词化：Multi-Agent 降 P2（强制消融）、MCP 降 P3（入场合条件）、Skill 去空壳、前端最小增量 |

### 逐项修改与理由

#### 竞赛定位收敛

**修改**：放弃"覆盖七赛题"叙事。赛题1（数据结构化提取）升级为系统级 **Document Intelligence Layer**；赛题3（产业链）降 P3 决赛可选。
**理由**：竞赛评分考察"任务完成度、数据准确性、可追溯"，而不是功能广度。堆功能挤占 P0 开发窗口，且每个浅功能都会在答辩中被追问穿。

#### 主链重定义

**修改**：主链起点从"provider 数据"改为"真实金融文档"，终点从"生成研报"延伸到"Evidence Pack + Audit Replay"。
**理由**：评委可现场验证的入口是上传真实 PDF，出口是可离线复核的证据包——首尾都是"可核验"的物理载体。

#### 金融逻辑硬伤修正（v2 五处错误）

| v2 错误 | v3 修正 | 落点 |
|---|---|---|
| 对 YTD 累计值直接 `compute_qoq` | 强制前置 `convert_ytd_to_single_quarter()`（100/230/390/540→100/130/160/150）；flow/stock 区分差分语义 | CARD-02/03 |
| 同比统一 `(cur-prev)/abs(prev)` | 盈利状态迁移五分支：正常/扭亏为盈/由盈转亏/亏损扩大收窄/零基期禁百分比 | CARD-03 |
| DCF 估值结果直接当股价 | EV 桥：EV−净债务−少数股东权益+非经营资产=Equity Value，再除稀释股本 | CARD-16（降 P2 决赛） |
| DCF 与相对估值区间取交/并集 | 分别展示 DCF/PE/PB/PS 区间 + 报告 method dispersion | CARD-08/16 |
| 多空评分 `Σ(argument×(1+0.5×evidence_count))` 与 A/B/C/D 加权总分 | 全部删除；多空只输出结构化对照（六产物），质量评估改零权重多维诊断 | CARD-19/17 |

**理由**：金融专业性是评分项，也是答辩必被追问项。无依据的公式比没有公式更糟。

#### 新增模块（v3 七个新卡）

| 新卡 | 模块 | 理由 |
|---|---|---|
| CARD-01 | Document Intelligence Layer | "从报告数字跳回 PDF 页"是竞赛最重要展示能力 |
| CARD-02 | Financial Normalization | 单位与口径错误是真实研报高频错误 |
| CARD-04 | Accounting Scope / Restatement Detection | 更正公告/重述下直接同比是错误 |
| CARD-07 | Run Manifest + events.jsonl | 可复现的物理基础 |
| CARD-09 | Claim-Evidence Graph | 系统核心创新：结论→计算→证据→PDF 页逐层可溯 |
| CARD-12 | Evidence Pack + Audit Replay | 提交成果物 + 历史任务重放 UI |
| CARD-13 | Source Conflict Resolver | 真实材料必然多版本冲突 |

#### 优先级重排

| 模块 | v2 | v3 | 理由 |
|---|---|---|---|
| Multi-Agent 编排 | P0 主架构 | P2（CARD-18） | 无指标收益不为技术名词买单 |
| MCP Server | P0/P1 | P3（CARD-20） | 初赛不考 MCP |
| Skill 体系 | 独立卡片 | 并入 CARD-14 | 不建空壳目录 |
| DCF | P0 | P2 决赛 | 相对估值已支撑初赛 |
| Benchmark | 末尾补 | P0 贯穿（CARD-11） | 指标与阈值随模块同步建立 |
| 产业链 | P1 | P3（CARD-21） | 线性加总公式无金融意义 |

#### 新增顶层文档

- `COMPETITION_REQUIREMENTS_MATRIX.md`：竞赛要求→模块→状态→卡片→验收→Demo 体现
- `ARCHITECTURE_V2.md`：竞赛版端到端架构、核心数据模型
- `DEMO_FLOW.md`：5 分钟 Demo 主故事 + 错误注入清单 + 失败注入场景
- `THIRD_PARTY_NOTICES_PLAN.md`：依赖合规计划

---

## v2.0 → v3.0 旧卡映射表

| v2 旧卡 | v3 去向 | 处置说明 |
|---|---|---|
| 01_workbench_split | CARD-15 | 全量拆分 → 最小增量 11 页 |
| 02_unified_task_system | CARD-07（部分） | 任务记录由 Run Manifest 承接 |
| 03_snapshot_catalog | 不单列卡 | snapshot 能力保留 |
| 04_fundamentals | CARD-03 | 指标体系重写 |
| 05_dcf_valuation | CARD-16（P2 决赛） | EV 桥修正后降级 |
| 06_report_checker | CARD-05 | 结构化 JSON → 自然语言草稿升级 |
| 07_report_scorer | CARD-17 | 加权总分删除，改零权重诊断 |
| 08_multiagent_orchestrator | CARD-18（P2） | 强制消融四问 |
| 09_bull_bear_debate | CARD-19（P3） | score 公式删除 |
| 10_buy_side_memo | CARD-10 | 解除 Multi-Agent 强依赖 |
| 11_document_parser | CARD-01 | 窄范围 → 8 类输入 |
| 12_industry_chain | CARD-21（P3） | 四量数学重设 |
| 13_benchmark_ablation | CARD-11（P0 贯穿） | 提前到第一模块 |
| 14_skill_prompt_assets | CARD-14 | PromptSpec 五字段 |
| 15_mcp_server | CARD-20（P3） | 入场合条件 |
| 16_retrieval | CARD-06 | chunk/evidence 分离 |
| （无旧卡） | CARD-02/04/07/08/09/12/13 | 新增 |

---

## 未变更事项（明确保留）

Evidence Ledger、Validator、Point-in-Time/available_at、Snapshot Provider、确定性 Python 金融计算、fail-closed 原则、复现信息记录、Agent Tool Contract、离线测试体系、FastAPI + Streamlit 技术栈，全部原样保留并继续作为系统底座。
