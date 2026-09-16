# DUAL_COMPETITION_POSITIONING.md — 双赛定位（同一套技术，两种叙事）

> 版本：v3.2 编码前冻结版 ｜ 2026-09-16
> FinTrace-CN 同时参加两个比赛：**华北五省计算机设计大赛** 与 **北京市大学生金融人工智能竞赛**。
> 原则：**完全同一套代码、同一套技术**。区别只在叙事顺序与强调重点，禁止为不同比赛做两套系统或夸大表述。

---

## 0. 统一创新叙事（所有文档共用一个口径）

**系统定义**：FinTrace-CN —— **面向 A 股投研的多模态可验证与可证伪金融智能体**。

**核心理念（一句话）**：

> **让每个金融结论可证明，让每个投资逻辑可证伪，让每次信息变化可重验证。**

**技术定位**：Multi-Agent、MCP、Skill、DCF、RAG、知识图谱等均属于 **supporting technologies**，**不作为主创新陈述**。主创新只有四大体系：

1. **ACME**（Accounting-Constrained Multimodal Evidence Engine）—— 会计约束驱动的多模态金融证据理解引擎（CARD-22）
2. **Financial Claim Passport / FPO**（金融AI结论护照 / 财务证明对象）—— 每个关键结论可独立验证（CARD-23）
3. **Thesis Fragility + Temporal Revalidation**（投资逻辑脆弱性 + 时间重验证）—— 逻辑可证伪、变化可重验证（CARD-24/25）
4. **FinFuzz**（金融语义对抗错误生成与压力测试框架）—— 可信能力被系统性证明而非声称（CARD-26，集成于 CARD-11）

---

## 1. 华北五省计算机设计大赛（技术叙事）

### 1.1 重点表达的能力

| 能力 | 对应模块 |
|---|---|
| AI Agent Architecture | 主链 Planner → Executor → Evidence → Validator → Memo |
| **Multimodal Understanding** | ACME：正文 / 表格 / 图表 / 脚注 / 公告 / Snapshot 联合理解 |
| **Constraint Reasoning** | ACME：会计恒等式、subtotal、跨期、YTD、跨源、跨模态六类约束验证 |
| **Graph Algorithms** | Thesis Fragility：REQUIRED 路径、minimal cut set、图可靠性分析 |
| **Incremental Computation** | Temporal Revalidation：affected-subgraph 增量重算（full vs incremental 对比） |
| **Trustworthy AI** | Claim Passport：证明对象 + verify_claim() 脱离 LLM 重新验证 |
| **Adversarial Testing** | FinFuzz：mutation suite 主动攻击自己的系统 |

### 1.2 核心技术演示主线（华北五省叙事）

```
多模态解析（PDF 文本/表格/图表/脚注）
  → ACME 会计约束发现问题（正文 vs 表格冲突）
  → Claim Passport（结论 → 完整证明链 → VERIFY）
  → Fragility Graph（投资逻辑的关键依赖与最小割集）
  → Temporal propagation（更正公告 → affected-subgraph 增量重算）
```

### 1.3 评审能看到的"工程深度"

- 确定性与 LLM 的严格边界（LLM 不做财务算术）
- 图算法（cut-set 枚举、受影响子图传播）全部可复现、可单测
- 增量计算与全量重算结果一致性断言（same deterministic result）
- 对抗评测（FinFuzz）的 per-error-type 指标分层

---

## 2. 北京市大学生金融人工智能竞赛（金融专业性叙事）

### 2.1 重点表达的能力

| 能力 | 对应模块 |
|---|---|
| Financial Accuracy | Normalization + Checker + Validator（unit/period/scope 硬伤检测） |
| Accounting Semantics | ACME 会计恒等式与勾稽关系 |
| Point-in-Time | source_published_at / ingested_at 分离、available_at |
| Report Checking | CARD-05：13 类错误确定性核查（FinFuzz 注入验证） |
| Valuation | 相对估值 + Bear/Base/Bull 敏感性 + PeerSet + 假设登记 |
| Investment Memo | 11 段买方备忘录 + 三级标注（fact/inference/opinion） |
| Evidence Traceability | Claim → Calculation → Evidence → PDF 页逐层回溯 |
| Reverse Validation（反向验证） | Thesis Fragility：投资逻辑可证伪 |
| Monitoring Metrics | Fragility → Monitoring Plan → 持续跟踪 |
| Reproducibility | Run Manifest + Audit Replay + Evidence Pack |

### 2.2 核心金融演示主线（北京赛叙事）

```
上传真实年报 PDF + 含错研报草稿
  → 解析/规范化/会计约束检测（异常定位 → PDF 页）
  → 研报纠错（numeric / unit / period / citation / causal 错误）
  → 点击核心 Claim → Financial Claim Passport
  → 点击 VERIFY CLAIM（脱离 LLM 重新验证）
  → Thesis Fragility Map（关键 REQUIRED dependency）
  → 人为删除/替换关键 Evidence → VERIFIED → STALE/BLOCKED 传播
  →（时间允许）更正公告 → Temporal Revalidation 影响分析
```

---

## 3. 相同点与不同点（演示对照表）

| 维度 | 华北五省 | 北京金融AI |
|---|---|---|
| 同一代码 | ✅ | ✅ |
| 主叙事 | 技术可信性：约束推理 / 图算法 / 增量计算 / 对抗测试 | 金融专业性：准确性 / 口径 / 可追溯 / 反向验证 |
| Demo 开场 | "一套能发现会计矛盾的多模态证据理解引擎" | "一套可验证可证伪的 A 股投研智能体" |
| 重点演示步骤 | ACME 跨模态冲突 + Fragility Graph + TEMPORAL propagation | Claim Passport + VERIFY + 状态传播 + Memo |
| 答辩高光 | ablation（parser vs parser+constraints；full vs incremental） | 失败注入（删证据→阻断）+ FinFuzz per-error-type |

**同一套演示环境**（DEMO_FLOW.md 5 分钟剧本），仅开场话术与讲解顺序按比赛切换。Cut：不预演、不美化失败、离线可复现、每个数字可回跳。

---

## 4. 创新真实性红线（两个比赛共同遵守）

- ✅ 允许：**"本项目提出…" / "本系统设计…" / "针对本竞赛场景，我们将…" / "区别于普通 RAG / 研报生成系统…"**
- ❌ 禁止（除非有充分检索证据）：**"全球首创 / 行业首创 / 国内首创 / 唯一 / 第一"**
- ACME / FPO / Fragility Engine / FinFuzz 均为本项目技术命名，**不能把命名本身当成已被学界验证的新理论**
- 不使用未经校准伪置信分数（0.83/0.72）；未运行的 benchmark 一律写 TARGET / TO BE MEASURED

---

## 5. 两个比赛的时间与冻结点

| 项目 | 华北五省 | 北京金融AI（初赛） |
|---|---|---|
| 提交截止 | 以组委会通知为准（早于北京赛则其冻结点更早） | 2026-10-18（计划书 PDF + ≤5 分钟视频） |
| Code Freeze | 以更早比赛截止日前 3 天为硬冻结 | 2026-10-15 |
| 决赛 | 待通知 | 2026-11 月底 |

**策略**：以更早的提交日驱动 Code Freeze；同一代码同时服务两赛，提交材料（计划书/视频/答辩）按各自叙事重新包装，不重开发。

---

## 6. 验收

- [ ] 开发文档统一使用"面向 A 股投研的多模态可验证与可证伪金融智能体"定义
- [ ] 四大创新体系是唯一主创新陈述；Multi-Agent/MCP/Skill/DCF/RAG 只作 supporting
- [ ] 双赛 Demo 剧本可切换叙事（仅话术不同，流程同一）
- [ ] 无"全球首创/国内首创/唯一/第一"表述（全文档扫描）