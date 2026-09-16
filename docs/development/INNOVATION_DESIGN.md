# FinTrace-CN 四大创新体系设计（INNOVATION_DESIGN）

> 版本：v3.2 编码前冻结版 ｜ 2026-09-16
> 本文档描述 FinTrace-CN 的四大核心创新体系，对应 ARCHITECTURE_V2.md §8。
> 原则：创新来自解决真实金融痛点，不来自技术名词堆砌。
> v3.2 命名变更：ACEE → **ACME**（Accounting-Constrained Multimodal Evidence Engine）；FPO 对外名 → **Financial Claim Passport（金融AI结论护照）**。ACME / FPO / Fragility Engine / FinFuzz 均为本项目技术命名，不是已被学术界验证的理论。

---

## 0. 创新声明边界

**禁止在 development 中使用**：
- 全球首创 / 国内首创 / 唯一 / 第一
- 除非后续有系统文献/产品检索证明

**建议表述**：
- "将会计一致性约束前移到财务文档解析质量控制环节"
- "将关键金融 Claim 封装为可独立验证的 Financial Proof Object"
- "在 Claim-Evidence Graph 上进一步分析投资逻辑的脆弱节点、失效条件与重验证范围"
- "使用金融语义 mutation 对系统进行持续对抗评测"

**每个创新必须回答**：
1. 真实金融痛点是什么？
2. 普通 RAG / Chatbot / 多 Agent 为什么不够？
3. 技术机制是什么？
4. 如何量化验证？
5. 现场如何展示？

---

## 1. 主创新一：ACME — Accounting-Constrained Multimodal Evidence Engine

**会计约束驱动的多模态金融证据理解引擎（不是简单 OCR / PDF Parser / RAG）**

### 1.1 真实金融痛点

传统 OCR/Table Parser 输出的财务数据不能直接被信任。真实年报中存在：
- 跨页续表（三大表跨 2–4 页）
- 双列表格（"本报告期 / 年初至本报告期末"）
- 单位混用（表头声明万元，正文某行用元）
- 扫描质量差（表格线断裂、字符模糊）
- 勾稽关系破坏（Assets ≠ Liabilities + Equity）

普通 RAG / Chatbot 无法发现这些"不可能成立"的解析结果，因为它们缺乏会计约束知识。

### 1.2 技术机制

**必须覆盖六类 Constraint Family**（v3.2 冻结，详见 CARD-22）：

**F1 Accounting Identity Constraints**（会计恒等式）
- `Assets ≈ Liabilities + Equity`
- `Net Profit ≈ Profit Before Tax − Income Tax`
- `Closing Cash ≈ Opening Cash + Net Change in Cash`
- 允许 rounding tolerance 与 statement-specific adjustment，**必须定义 tolerance policy，不机械绝对相等**

**F2 Table Structural Constraints**（表格结构）
- `Subtotal ≈ Sum(children)`、`Total ≈ Sum(line items)`
- 检测：OCR 错位、列错位、负号丢失、单位错误、单元格串行

**F3 Period Constraints**(期间关系)
- `Q2 = H1 − Q1`、`Q3 = 9M − H1`、`Q4 = FY − 9M`
- **与现有 FinancialPeriodEngine 共用统一 period schema，不得重复实现另一套 period logic**

**F4 Cross-period Constraints**（跨期连续性）
- `current_year_opening_balance ≈ previous_year_closing_balance`
- 会计政策调整、重述、合并范围变化时**不能强制一致**——结合 Accounting Scope / Restatement Signal

**F5 Cross-source Constraints**（跨源一致性）
- `Annual Report Revenue vs Snapshot Provider Revenue`
- period/scope/version/currency/unit 统一后比较；结果 ≥ 四类：`MATCH | ROUNDING_MATCH | CONFLICT | NOT_COMPARABLE`
- **禁止直接"谁不一样就认为谁错"**；裁决职责交 CARD-13

**F6 Cross-modal Constraints**（跨模态一致性）
- 例：正文写"毛利率同比下降 2.1 个百分点"、表格计算 33.4%→31.2% = −2.2pct、图表标注 −2.2pct → 检出不一致
- **不能直接判断正文一定错误**；记录 source A / source B / source C / computed value / conflict type / resolution status

**初赛 P0/P1 基础版**：constraint validation + anomaly localization + review queue（**初赛不自动静默修值**）
**决赛 P2 增强**：Constraint-Based Candidate Correction（CP-SAT / constraint solver，保留 original candidate / selected candidate / constraint reason / review status，**不得自动静默覆盖**）

### 1.3 量化验证

**指标**：
- Constraint Violation Detection Recall（约束违反检测召回率）
- Constraint False Alarm Rate（约束误报率）
- Financial Proof Verification Pass Rate（财务证明验证通过率）

**测试集**：
- Synthetic：合成年报 + planted constraint violations
- Real：真实年报 + 人工标注 constraint violations

### 1.4 现场展示

**Demo 剧本**：
- 上传真实年报 PDF → Document Registry 解析
- 展示一个财务解析异常被 Accounting Constraint 捕获（如 Assets ≠ Liabilities + Equity）
- 点击异常 → 跳转原始 PDF 页 + 展示约束违反详情
- 如果现场不稳定，使用预先准备好的 deterministic failure-injection case

### 1.5 对应 CARD

**CARD-22: ACME（Accounting-Constrained Multimodal Evidence Engine）**（P0，初赛）

---

## 2. 主创新二：Financial Claim Passport / Financial Proof Object（金融AI结论护照）

**每个重要金融 Claim 生成一个机器可验证的 Financial Proof Object（FPO）**

### 2.1 真实金融痛点

传统研报的结论无法独立验证。评委/用户看到"盈利质量下降"这样的结论，无法快速验证：
- 这个数字来自哪份文档的哪一页？
- 计算用了什么公式？
- 输入数据是否可靠？
- 假设条件是什么？
- 依赖的证据是否还有效？

普通 RAG / Chatbot 只能提供"引用来源"，但无法提供完整的证明链。

### 2.2 技术机制

**Financial Proof Object（FPO）至少包含**：

```python
@dataclass
class FinancialProofObject:
    # Claim
    claim_id: str
    claim_text: str
    claim_type: str              # fact | inference | opinion
    temporal_status: str         # historical | current | forward_looking
    economic_period: str         # 如 "2025Q2"
    
    # Source Proof
    document_hash: str           # 文档 sha256
    source_locator: dict         # {page, bbox, table, row, column} 或 {sheet, cell} 等
    publication_version_info: dict
    
    # Accounting Context
    consolidated_or_parent: str  # consolidated | parent
    unit_currency: dict          # {unit: "元", currency: "CNY"}
    ytd_or_single: str          # ytd_cumulative | single_quarter | point_in_time
    as_reported_or_restated: str # as_reported | restated | corrected
    
    # Calculation Proof
    formula: str                 # 如 "cfo / net_profit_parent"
    formula_version: str         # 公式版本
    inputs: list[dict]           # [{ref: evidence_id, value: 123456.78}]
    deterministic_output: float  # 确定性输出
    code_version: str            # 代码版本（git commit）
    
    # Assumptions
    assumption_ids: list[str]    # 假设 ID 列表
    
    # Dependencies
    dependencies: list[dict]     # [{role: REQUIRED|SUPPORTING|OPTIONAL, target_id}]
    
    # Validation
    source_validation: str       # VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED
    period_validation: str       # VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED
    unit_validation: str         # VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED
    calculation_validation: str  # VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED
    dependency_validation: str   # VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED
    
    # Integrity
    proof_hash: str              # SHA256(proof content)
    run_id: str                  # 运行 ID
    git_commit: str              # 代码版本
```

**新增 Verify API / Tool**：
- 独立接口 `verify_claim(claim_id)`——**不依赖 LLM 重新回答**
- 至少重查：document hash、evidence existence、source version、period、scope、unit、formula、calculation result、required dependencies、assumptions、validator state
- 验证结果五态：`VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED`（并给出原因）
- 验证项：source / period / scope+unit / calculation / dependency / assumption / validator state status

### 2.3 量化验证

**指标**：
- FPO Verification Pass Rate（FPO 验证通过率）
- Orphan Claim Rate（孤儿 Claim 率）
- Evidence Coverage（证据覆盖率）

**测试集**：
- Synthetic：合成 Claim + planted verification failures
- Real：真实研报 + 人工标注 verification failures

### 2.4 现场展示

**Demo 剧本**：
- 点击一个关键 Claim → Financial Claim Passport（Financial Proof Object）→ **点击 VERIFY CLAIM → 系统脱离 LLM 重新执行证明**
- 展示完整证明链：Claim → Calculation → Evidence → PDF Page
- 展示验证五态：VERIFIED / DEGRADED / STALE / BLOCKED / CONFLICTED

### 2.5 对应 CARD

**CARD-23: Financial Claim Passport & Proof Verifier**（P0，初赛）

---

## 3. 主创新三：Thesis Fragility + Temporal Revalidation

**投资逻辑脆弱性与时间重验证**

### 3.1 真实金融痛点

**Thesis Fragility**：
投资逻辑通常依赖多个关键假设和证据。但传统研报无法回答：
- 核心投资逻辑最依赖什么？
- 最少破坏哪些节点会让它失效？
- 哪些假设是脆弱的？

**Temporal Revalidation**：
金融数据是动态的。新公告/更正/重述进入后：
- 哪些旧事实被替代？
- 哪些计算过期？
- 哪些 Claim 失效？
- 估值是否需要更新？
- 备忘录哪些段落需要刷新？

普通 RAG / Chatbot 无法自动追踪这些依赖关系和时效性。

### 3.2 技术机制

**Thesis Fragility Map**：

**基础版**（初赛 P1）：
- 基于 REQUIRED dependency 计算关键节点
- 单点依赖检测（single point of failure）
- fragile assumption 识别（脆弱假设）
- 可以加入结构脆弱性：minimal cut set / critical dependency

**数值增强版**（决赛 P2）：
- 对具有可靠阈值来源的指标计算：
  - critical threshold（临界阈值）
  - distance to invalidation（距离失效的距离）
- **严禁**让 LLM 凭空编阈值
- Fragility 结果必须能转为 Monitoring Plan：
  ```python
  @dataclass
  class MonitoringPlan:
      dependency: str              # 依赖项
      observable_kpi_event: str    # 可观察 KPI/事件
      trigger_condition: str       # 触发条件
      affected_claims: list[str]   # 受影响的 Claim
      revalidation_action: str     # 重验证动作
  ```

**Temporal Revalidation**：

**基础版**（初赛 P1）：
- 在 version lineage + Claim Graph 上实现：
  - 新公告 / 更正 / 重述进入后 → old facts superseded
  - dependent calculations stale
  - dependent claims stale/blocked
  - valuation affected
  - memo sections marked for refresh
- 初赛只需 basic propagation

**决赛 P2 增强**：
- incremental recomputation（增量重计算）
- automatic refresh（自动刷新）
- 注意区分：economic period / source published time / ingestion time / version lineage

### 3.3 量化验证

**指标**：
- Affected-node propagation accuracy（受影响节点传播准确率）
- Single point of failure detection recall（单点故障检测召回率）
- Temporal revalidation latency（时间重验证延迟）

**测试集**：
- Synthetic：合成 Claim Graph + planted fragility patterns
- Real：真实研报 + 人工标注 fragility patterns + 模拟 temporal events

### 3.4 现场展示

**Demo 剧本**：
- Thesis Fragility Map → 展示一个关键 REQUIRED dependency / fragile assumption / tracking KPI
- 导入更正公告 → version supersession → affected calculations/claims/memo sections stale
- 展示 Monitoring Plan：dependency, observable KPI/event, trigger condition, affected claims, revalidation action

### 3.5 对应 CARD

**CARD-24: Thesis Fragility Engine**（P1，初赛增强）
**CARD-25: Temporal Revalidation Engine**（P1，初赛增强）

---

## 4. 评测创新：FinFuzz（金融语义错误攻击器）

**金融语义 mutation suite**

### 4.1 真实金融痛点

金融研报中的错误往往是语义级别的，而非简单的拼写错误：
- 数字量级错误（3.1 亿元写成 31,000 亿元；注：3.1 亿元 = 31,000 万元，**数值相等不构成错误**）
- 单位错误（万元 ↔ 亿元、CNY ↔ USD、% ↔ bp）
- 期间错误（YTD 当成单季；FY ↔ H1）
- 口径错误（合并口径当成母公司口径）
- 因果过度声称（"利润增长主要因海外订单放量"但年报无此表述）
- 引用错误（引用第 45 页但实际在第 118 页）

传统测试方法无法系统性地检测这些语义错误。

### 4.2 技术机制

**新增金融语义 mutation suite**，至少覆盖：
- numeric_scale（数值量级）
- unit（单位）
- sign（符号）
- period（期间）
- YTD_vs_single（YTD 与单季混淆）
- scope（口径）
- version（版本）
- valuation_basis（估值基础）
- citation/page（引用/页码）
- causal_overclaim（因果过度声称）

**从正确事实/模拟真实业务研报生成 adversarial variants**：
```python
def mutate_claim(claim: Claim, mutation_type: str) -> Claim:
    """生成 adversarial variant"""
    ...
```

**输出**：
- Precision（精确率）
- Recall（召回率）
- F1
- False Positive Rate（误报率）
- Error-type Recall（各类错误召回率）
- Holdout performance（留集性能）

**必须区分**：
- Claim Extractor failure（提取器失败）
- Checker failure（核查器失败）

### 4.3 量化验证

**指标**：
- Mutation Detection Precision / Recall / F1
- Mutation Type Recall（各类错误召回率）
- False Positive Rate（误报率）
- Holdout Performance（留集性能）

**测试集**：
- Synthetic：合成正确 Claim + planted mutations
- Real：真实研报 + planted mutations

### 4.4 现场展示

**Demo 剧本**：
- FinFuzz 注入一个单位/期间/因果错误 → Checker/Validator 捕获
- 展示错误类型、原始值、正确值、证据、建议

### 4.5 对应 CARD

**CARD-26: FinFuzz**（P1，初赛）

---

## 5. 创新优先级（不能破坏初赛交付）

**P0**（第一冻结点前必须）：
- ACME 基础版（CARD-22）：会计恒等式 + 表格结构 + YTD 关系 + 跨期
- Financial Claim Passport（CARD-23）：完整 FPO + verify_claim() + Validator integration
- REQUIRED dependency propagation（CARD-09）
- Source/version semantics 修正（CARD-02/13）
- FinFuzz 基础版（CARD-26）：Numeric / Unit / Period / Scope / Citation

**P1**（初赛增强）：
- Temporal Revalidation 基础版（CARD-25）
- Thesis Fragility structural analysis（CARD-24）
- Cross-source reconciliation / cross-modal 增强（CARD-22 F5/F6）
- tamper-evident audit hash chain（CARD-07，如果开发量允许）

**P2 / 决赛**：
- constraint-based candidate correction / CP-SAT（CARD-22 增强）
- numerical fragility optimization（CARD-24 增强）
- full incremental revalidation（CARD-25 增强）
- advanced visualization（CARD-23/24 增强）

**不能因为创新模块导致**：
- PDF 解析延期
- 财务计算延期
- Report Checker 延期
- 估值延期
- Memo 延期
- Validator 延期
- Benchmark 延期

---

## 6. 创新与普通 RAG / Chatbot / 多 Agent 的对比

| 能力 | 普通 RAG / Chatbot | 多 Agent | FinTrace-CN 创新 |
|---|---|---|---|
| 会计约束检测 | ❌ 无 | ❌ 无 | ✅ ACME（六类约束族驱动的多模态证据理解与质量控制） |
| 证明链 | ⚠️ 仅引用来源 | ⚠️ 仅引用来源 | ✅ Financial Claim Passport / FPO（完整证明链 + verify_claim 五态） |
| 脆弱性分析 | ❌ 无 | ❌ 无 | ✅ Thesis Fragility Engine（关键节点、最小割集、脆弱假设、Monitoring Plan） |
| 时间重验证 | ❌ 无 | ❌ 无 | ✅ Temporal Revalidation（三态区分 + affected-subgraph 增量重算） |
| 语义错误检测 | ⚠️ 简单规则 | ⚠️ 简单规则 | ✅ FinFuzz（金融语义 mutation suite + per-error-type 指标） |

**结论**：FinTrace-CN 的创新来自解决真实金融痛点，不来自技术名词堆砌。

---

## 7. 验收

- [ ] 四大创新体系在 ARCHITECTURE_V2.md §8 有完整描述
- [ ] 四大创新体系对应 CARD-22/23/24/25/26 已创建
- [ ] 每个创新回答了 5 个问题（痛点/为什么不够/技术机制/量化验证/现场展示）
- [ ] 创新优先级明确（P0/P1/P2）
- [ ] 创新不破坏初赛交付（PDF 解析/财务计算/Report Checker/估值/Memo/Validator/Benchmark）
- [ ] 创新声明边界遵守（无"全球首创/国内首创/唯一/第一"）
