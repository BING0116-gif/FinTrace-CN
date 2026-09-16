# CARD-22: ACME — Accounting-Constrained Multimodal Evidence Engine（会计约束驱动的多模态金融证据理解引擎）

| 属性 | 值 |
|---|---|
| 优先级 | P0（第一冻结点前） |
| 竞赛阶段 | 初赛版（9/23–10/6 分两段：基础约束 9/23–9/29，跨源/跨模态 9/30–10/6） |
| 对应赛题 | 北京赛：赛题2/5（创新一）；华北五省：Constraint Reasoning / Multimodal Understanding |
| 依赖 | CARD-01（文档解析）、CARD-02（规范化/期间键）、CARD-13（cross-source 裁决）、现有 `src/cn/domain.py`（FinancialStatement） |
| 实现复杂度 | 高（约 6 人日：基础约束 3 + 跨源 1.5 + 跨模态 1.5） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

> 本卡前身：v3.1 的 "Accounting Integrity Validator (ACEE)"。v3.2 按最终创新体系升级为 ACME：在会计完整性约束之上，增加 **Table Structural / Period / Cross-period / Cross-source / Cross-modal** 六类约束族，成为"解析→约束验证→异常定位→降级/重新解析/人工复核"的完整质量控制层。

## 1. Objective（目标）

新建 `src/cn/acme/`：对多模态金融证据（财报正文、财务表格、图表、脚注、公告、Snapshot Provider 数据）的抽取结果做**主动约束验证**。系统**不能"解析完就相信"**，而必须执行：`解析 → 约束验证 → 异常定位 → 降级/重新解析/人工复核`。

初赛阶段以**检测 + 定位 + 阻断**为主；决赛增强阶段才考虑 OCR candidate search / constraint optimization / automatic candidate correction。**禁止在没有充分证据时静默修改原始财务数字。**

## 2. Competition relevance（双赛分别解决什么评审问题）

| 比赛 | 解决的评审问题 |
|---|---|
| 华北五省计算机设计大赛 | 展示 **Constraint Reasoning + Multimodal Understanding**：系统联合理解正文/表格/图表/脚注/公告，并用会计恒等关系与跨模态一致性主动验证抽取结果——这是普通 OCR/RAG 不具备的机器可验证推理能力 |
| 北京市大学生金融人工智能竞赛 | 回答"数据准确性/金融专业性"：单位混用、勾稽关系破坏、期间错配、跨源不一致等真实金融硬伤被系统**主动捕获并定位**，而不是静默用错值继续计算 |

## 3. Why this is not a gimmick（为什么不是点缀）

普通 OCR / PDF Parser / RAG 只做"提取"，没有能力回答"提取结果是否可能成立"。ACME 的核心差异：

- 普通 Pipeline：`parse → trust`（解析完就相信）
- 本系统：`parse → constraint-check → locate anomaly → degrade/re-parse/review`（解析完必须过验证）

约束验证全部是**确定性规则**（会计恒等式、小计勾稽、YTD 关系、跨期连续性、跨源一致），不依赖 LLM 判断，结果可复现、可测试、可向评委展示"系统发现自己错了"。

## 4. Inputs / 5. Outputs

- **输入**：`NormalizedFact[]`（CARD-02）、`FinancialStatement[]`（现有 domain.py 或 CARD-02 适配器投影）、多模态抽取载体（表格结构、图表数值/注释、正文段落）、Snapshot Provider facts
- **输出**：`ConstraintViolation[]` + `IntegrityReport` + `CrossModalInconsistency[]` + `review_queue[]`（人工复核队列）

## 6. Data Models（数据模型）

```python
@dataclass
class ConstraintViolation:
    violation_id: str
    constraint_family: str    # accounting_identity | table_structural | period | cross_period | cross_source | cross_modal
    constraint_id: str        # 如 "balance_sheet_equation" / "subtotal_reconciliation" / "ytd_single_quarter_relation"
    inputs: list[dict]        # [{ref: evidence_id, value, period, scope, version, unit, currency}]
    expected_value: float | None
    actual_value: float | None
    residual: float | None
    tolerance: float          # 已按 tolerance policy 归一
    status: str               # violated | warning | passed | not_comparable
    source_refs: list[dict]   # [{document_id, page, locator} | {snapshot_id, available_at}]
    severity: str             # error | warning
    resolution_status: str    # opened | re_parsed | reviewed | auto_corrected(决赛) | dismissed
    detected_at: str

@dataclass
class CrossModalInconsistency:
    """跨模态不一致（正文 / 表格 / 图表 三方不一致）"""
    inconsistency_id: str
    metric: str
    values: dict[str, float | None]   # {source_a(body): 33.4%, source_b(table): 31.2%, source_c(chart): -2.2pct}
    computed_value: float | None      # 由原始数值计算得到的基准值
    conflict_type: str                # value_mismatch | label_mismatch | unit_mismatch | period_mismatch
    resolution_status: str            # unresolved | resolved_which_source
    source_refs: list[dict]

@dataclass
class IntegrityReport:
    document_id: str
    constraint_families_checked: list[str]
    totals: dict                      # {checked, passed, warning, violated, not_comparable}
    violations: list[ConstraintViolation]
    cross_modal: list[CrossModalInconsistency]
    review_queue: list[str]
```

## 7. Algorithms（算法——约束族与容差策略）

必须覆盖 **六类 Constraint Family**：

### F1. Accounting Identity Constraints（会计恒等式）
- `Assets ≈ Liabilities + Equity`
- `Net Profit ≈ Profit Before Tax − Income Tax`（允许报表项目差异）
- `Closing Cash ≈ Opening Cash + Net Change in Cash`
- **不得机械要求绝对相等**：须按 tolerance policy 判定

### F2. Table Structural Constraints（表格结构）
- `Subtotal ≈ Sum(children)`、`Total ≈ Sum(line items)`
- 用于检测：OCR 错位、列错位、负号丢失、单位错误、单元格串行

### F3. Period Constraints（期间约束）
- `Q2 = H1 − Q1`、`Q3 = 9M − H1`、`Q4 = FY − 9M`
- **必须与现有 `FinancialPeriodEngine` 共用统一 period schema（YYYYQ1/YYYYH1/YYYY9M/YYYYFY）**，只调用 `derive_single_quarters()`，**不得重复实现另一套 period logic**

### F4. Cross-period Constraints（跨期约束）
- `current_year_opening_balance ≈ previous_year_closing_balance`
- 会计政策调整、重述、合并范围变化时**不能强制一致**——结合 CARD-04 的 Accounting Scope / Restatement Signal 决定是否跳过或降级为 warning

### F5. Cross-source Constraints（跨源约束）
- `Annual Report Revenue vs Snapshot Provider Revenue`
- 在 period / scope / version / currency / unit **统一后**比较
- 结果至少分四类：`MATCH | ROUNDING_MATCH | CONFLICT | NOT_COMPARABLE`
- **禁止直接"谁不一样就认为谁错"**：只标记结果，裁决交给 CARD-13（本卡不裁决）

### F6. Cross-modal Constraints（跨模态约束）
- 例：正文写"毛利率同比下降 2.1 个百分点"、表格计算 33.4%→31.2% = −2.2pct、图表标注 −2.2pct → 检出不一致
- **不能直接判断正文一定错误**：记录 source A/B/C、computed value、conflict type、resolution status

### Tolerance Policy（容差策略，必须显式定义，不能机械绝对相等）
- 绝对容差：1000 元（小额舍入差异）；相对容差：0.1%（大额报表）；取两者较大值
- 支持 statement-specific adjustment 白名单（登记后豁免），白名单必须来源可溯
- 容差内差异 → `warning`（不误报为 violated）；容差外 → `violated`

## 8. API / Tool Contract

```python
# src/cn/acme/validator.py
def validate_multimodal_evidence(facts, statements, snapshots=None, chart_annotations=None) -> IntegrityReport: ...
# 各约束族检查函数（每族一个模块级函数，返回 ConstraintViolation[]）
def check_accounting_identities(...) -> list[ConstraintViolation]: ...
def check_table_structural(...) -> list[ConstraintViolation]: ...
def check_period_relations(...) -> list[ConstraintViolation]: ...     # 内部只调 FinancialPeriodEngine
def check_cross_period_continuity(...) -> list[ConstraintViolation]: ...  # 结合 CARD-04 信号
def check_cross_source(...) -> list[ConstraintViolation]: ...         # 输出 MATCH/ROUNDING_MATCH/CONFLICT/NOT_COMPARABLE，裁决交 CARD-13
def check_cross_modal(...) -> list[CrossModalInconsistency]: ...
```

Agent 工具 `ValidateCnAcmeTool`：入参 `document_id`；出参 `status / integrity_report / violations[] / review_queue[]`。解析失败或勾稽失败 → 进入 Validator / review queue，**绝不静默跳过**。

## 9. Deterministic vs LLM boundary（确定性与 LLM 边界）

- 本卡**全部确定性规则，零 LLM**
- LLM 不参与任何约束判定；LLM 只可能在"异常定位后重新解释文档上下文"环节以只读辅助出现（可后续增强，不做初赛依赖）
- 修正值（决赛 P2）必须保留：`raw value / candidate values / constraint violated / selected candidate / selection reason / manual review status`

## 10. Dependencies（依赖）

CARD-01（ExtractedFact + SourceLocator）、CARD-02（NormalizedFact + 期间键）、CARD-04（重述信号，F4 用）、CARD-13（cross-source 裁决）。调用现有 `FinancialPeriodEngine.derive_single_quarters()` / `derive_ttm()`，**不重复实现 period 逻辑**。

## 11. Failure Modes

- 约束检查失败 → 该约束标记 `check_failed`，不影响其余约束；**不得**因检查失败静默跳过
- 字段缺失（如 Gross Profit 未披露）→ 跳过该约束并记录 `skipped_missing_field`，不报错不误报
- 解析失败或勾稽失败 → 进入 Validator / review queue

## 12. Edge Cases

1. 多口径并存（合并/母公司）→ 分别检查不混用
2. 重述/口径变化（CARD-04 信号）→ 使用调整后数据或标记 `restatement_context`
3. 跨期不连续（IPO 公司无上年数据）→ 跳过跨期连续性
4. 容差内差异 → warning 而非 violated
5. 跨源口径不同 → `NOT_COMPARABLE`，不判错
6. 跨模态只有两方（正文+表格，无图表）→ 以两者比对为准，缺失方记录 N/A

## 13. Validator Rules

- 每个 violation 的 source_refs 必须可解析
- residual 与 expected/actual 一致（代码审查断言）
- review_queue 非空（存在 violated/warning 时）
- 决赛自动纠正路径必须有 original/selected/reason/manual review 四字段，否则**禁止写入**该值

## 14. Unit Tests

- 六类约束族各含正例/反例
- 容差测试（容差内 warning / 容差外 violated）；容差策略函数单独测试
- 期间约束只调 FinancialPeriodEngine（接口 mock 断言，不允许自写差分）
- 跨源四分类（MATCH/ROUNDING_MATCH/CONFLICT/NOT_COMPARABLE）
- 跨模态三方不一致正反例（含"正文正确表格错误/img 标注错误"用例）
- 字段缺失跳过、多口径分检、重述上下文标记

## 15. Integration Tests

CARD-01 → CARD-02 → CARD-22 全链：解析真实 PDF → 规范化 → ACME 检查 → violation 报告；注入 cross-source 变化 → CARD-13 裁决后结果正确。

## 16. Benchmark

**指标（接入 CARD-11，带 ablation）**：
- Constraint Violation Detection Recall / False Alarm Rate
- Cross-source reconciliation 准确率（四分类）
- Cross-modal inconsistency detection recall

**Ablation（CARD-11 必须）**：`Parser only` vs `Parser + accounting constraints`，比较 financial extraction error detection / statement integrity error detection。
**测试集**：Synthetic（合成年报 + planted violations）+ Real（真实年报 + 人工标注 violations）。目标值待 baseline 冻结，**禁止编造数字**。

## 17. Demo Flow

Demo 步骤 4b（见 DEMO_FLOW.md）：上传真实年报 → 展示一个约束异常被捕获（如 Assets ≠ Liabilities + Equity 或"正文 vs 表格"毛利变动区间不一致）→ 点击异常 → 跳转原始 PDF 页 + 约束违反详情（含 violation ID、inputs、residual、容差）。

## 18. Acceptance Criteria（验收标准）

- [ ] 六类约束族全部有测试
- [ ] 容差策略函数有测试并通过
- [ ] 期间约束零重复实现（只调现有 FinancialPeriodEngine 断言）
- [ ] 跨源四分类输出正确；裁决交接 CARD-13 链路打通
- [ ] 跨模态不一致检测有正反例测试
- [ ] 初赛无任何自动静默修值路径（代码断言）
- [ ] ablation 至少"parser only vs parser+constraints"可运行出结果（不编数字）
- [ ] 全部测试离线通过

## 19. Priority

**P0**（第一冻结点前必须完成基础版：F1/F2/F3/F4 四族 + tolerance policy；F5/F6 为 P0 后半段或 P1 早段，但 demo 剧本用到 cross-modal）

## 20. Competition Stage

初赛基础版（六类约束检测+定位+阻断）；决赛增强：constraint-based candidate correction / CP-SAT / OR-Tools（保留 original/candidate/selected/reason/manual review）。

## 21. Estimated Complexity

约 6 人日（基础约束 3 + 跨源 1.5 + 跨模态 1.5）。

## 22. Fallback / Degradation Strategy

- 时间不足裁剪顺序：F6 跨模态（demo 彩排可改用演示点）→ F5 跨源（降为仅记录不阻断）→ F3 保留（直接复用引擎，成本低）
- 任何约束族缺失时该族返回 `not_checked`，IntegrityReport 显式列出未检查族，不假装全覆盖
- 断网/材料不足：全部本地规则，无外部依赖

## 23. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |