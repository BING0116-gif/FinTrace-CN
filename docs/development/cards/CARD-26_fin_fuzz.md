# CARD-26: FinFuzz — Financial Semantic Adversarial Benchmark（金融语义对抗错误生成与压力测试框架）

| 属性 | 值 |
|---|---|
| 优先级 | P1（初赛增强；不阻塞主链） |
| 竞赛阶段 | 初赛版（10/12–10/15 窗口 5；贯穿评测） |
| 对应赛题 | 北京赛：赛题7 内部评价机制（评测创新）；华北五省：Adversarial Testing |
| 依赖 | CARD-05（Report Checker）、CARD-09（Claim 结构）、CARD-11（Benchmark 集成） |
| 实现复杂度 | 中（约 4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-agent-evaluation |

> 本卡前身：v3.1 的 "FinFuzz"。v3.2 明确其定位：**FinFuzz 不是业务核心功能，它是验证 FinTrace 可信能力是否真的有效的测试框架**，必须集成到 Benchmark CARD（CARD-11）。

## 1. Objective（目标）

新建 `src/cn/finfuzz/`：金融语义 mutation suite——从正确事实/真实业务研报生成 adversarial variants，系统性地测试系统的错误检测能力。金融研报中的错误是**语义级别**的（单位、期间、口径、因果、引用），传统测试无法系统性覆盖。

## 2. Competition relevance（双赛分别解决什么评审问题）

| 比赛 | 解决的评审问题 |
|---|---|
| 华北五省计算机设计大赛 | 展示 **Adversarial Testing**：主动攻击自己的系统（mutation → 检测 → 分层指标），证明可信能力是真的而非演示脚本 |
| 北京市大学生金融人工智能竞赛 | 回答赛题7"内部评价机制"：per-error-type 的 Precision/Recall/F1/误报率，说明系统对每一类金融语义错误的具体检测能力 |

## 3. Why this is not a gimmick（为什么不是点缀）

普通评测只测"正确输入 → 正确输出"。FinFuzz 测"**篡改后的输入 → 系统能否识别篡改**"，并**按错误类型分层**报告（不能只统计总 F1）。它把"系统是否真的可信"从口头声明变成可复现的对抗测试结果。

## 4. Inputs / 5. Outputs

- **输入**：正确 Claim 集合 / 真实研报切片 + Mutation Operators + 被测系统（Checker/Validator）
- **输出**：`MutationSpec[]` + `MutationResult[]` + `FinFuzzReport`（Overall + per-error-type metrics）

## 6. Data Models（数据模型）

```python
class MutationOperators(str, Enum):
    NUMERIC = "numeric"                 # 小数点移动/量级：1.26 → 12.6
    UNIT = "unit"                       # 万元↔亿元, CNY↔USD, %↔bp
    SIGN = "sign"                       # -3.2% ↔ +3.2%
    PERIOD = "period"                   # FY↔H1, Q2↔Q3, 2024↔2025
    YTD_VS_SINGLE = "ytd_vs_single"     # 9M cumulative 冒充 Q3 single
    SCOPE = "scope"                     # consolidated ↔ parent
    VERSION = "version"                 # corrected ↔ as-reported old value
    VALUATION = "valuation"             # PE_TTM ↔ PE_NTM, PE ↔ PB
    CITATION = "citation"               # 正确数字 + 错误页码 / 错误 Evidence ID
    CAUSAL = "causal"                   # 无 management attribution 时把并列改为因果

@dataclass
class MutationSpec:
    mutation_id: str
    operator: MutationOperators
    source_claim: dict                  # 原始正确 claim
    mutated_claim: dict                 # 变异后 claim
    description: str
    expected_detection: bool            # 应被检出的真变异（部分用于误报测试的"伪变异"为 False）

@dataclass
class MutationResult:
    spec: MutationSpec
    detected_by: str | None             # checker | validator | none
    detected: bool
    detection_time_ms: int
    error_type_classified: str | None

@dataclass
class FinFuzzReport:
    suite_id: str
    overall: dict                       # {precision, recall, f1, false_positive_rate}
    per_error_type: dict                # {numeric: {recall, n}, unit: {...}, period: {...}, scope, version, citation, causal, sign, ytd_vs_single, valuation}
    baseline_holdout: dict              # holdout 结果（防止对测试集过拟合调优）
    extractor_vs_checker: dict          # 区分 Claim Extractor failure 与 Checker failure
```

## 7. Algorithms（算法）

### Mutation Operators（第一阶段至少 10 类，见 §6）
每个 operator 实现为 `<source> → <mutated>` 的确定性转换函数：
```python
def mutate_numeric(claim, factor=10) -> dict: ...      # 1.26 → 12.6
def mutate_unit(claim, from_unit, to_unit) -> dict: ... # 万元→亿元（数值同比例换算，形成单位语义错误）
def mutate_sign(claim) -> dict: ...
def mutate_period(claim, from_, to) -> dict: ...
def mutate_ytd_vs_single(claim) -> dict: ...
def mutate_scope(claim) -> dict: ...
def mutate_version(claim) -> dict: ...
def mutate_valuation_basis(claim) -> dict: ...
def mutate_citation(claim, wrong_page|wrong_evidence) -> dict: ...
def mutate_causal(claim) -> dict: ...
```

### 关键用例设计（与检测能力一一对应）
- `numeric`：1.26 → 12.6（数量级）
- `unit`：3.1 亿元 → 31,000 亿元（量级+单位混合场景按 unit operator 归类）——注：3.1 亿 = 31,000 万，**"3.1 亿元写成 31,000 万元"数值相等不是错误**，必须用 31,000 亿元这类真实量级错误
- `causal`："原材料上涨"+"毛利率下降"（原文并列）恶意改成"原材料上涨导致毛利率下降"——无 management attribution → 应识别为 unsupported causal claim

### 指标计算
- Overall Precision / Recall / F1 / False Positive Rate
- **按错误类型独立**：Numeric/Unit/Period/Scope/Version/Citation/Causal（+ Sign/YTD/Valuation）Error Recall
- 必须区分：Claim Extractor failure（提取器失败）vs Checker failure（核查器失败）

## 8. API / Tool Contract

```python
# src/cn/finfuzz/suite.py
def generate_mutation_specs(claims, operators, seed=42) -> list[MutationSpec]: ...
def run_suite(specs, targets) -> list[MutationResult]: ...   # targets = {checker, validator}
def compute_metrics(results) -> FinFuzzReport: ...
def run_finfuzz(suite_id, claims, operators, targets, holdout=None) -> FinFuzzReport: ...
```

CLI：`python -m src.cn.finfuzz --operator numeric,unit,... --set synthetic|real --out output/benchmark/finfuzz/`。集成进 CARD-11 的 `--suite cn_agent_v2` 体系。

## 9. Deterministic vs LLM boundary（确定性与 LLM 边界）

- mutation 生成是**确定性函数**（seed 固定，结果可复现）
- 被测对象（Checker/Validator）是确定性模块；对 LLM 提取器的评测以离线 mock 接口隔离
- 评测报告由确定性代码生成，**禁止编造结果**

## 10. Dependencies（依赖）

CARD-05（Checker 目标）、CARD-09（Claim schema 与 Validator 状态）、CARD-11（benchmark 集成与报告）。
协议：FinFuzz 只在 CARD-11 的评测流水线调用，不进入业务主链。

## 11. Failure Modes

- MutationSpec 生成失败 → 跳过并记录（不影响其余）
- 被测系统超时 → 标记 timeout，按 miss 处理（在报告中注明）
- 指标分母为零（某 error type 无样本）→ 该 type 记 `N/A`，不删除行

## 12. Edge Cases

1. 变异后仍正确（数值未真变）→ 应标记 `expected_detection=false` 作为误报压力样本
2. 多 operator 组合变异 → 记录组合标签
3. 同一 claim 重复变异 → 去重
4. holdout：FinFuzz 调优不得触碰 holdout 子集

## 13. Validator Rules

- 每个 MutationSpec 必须有 source_claim 与 mutated_claim 的 diff 描述
- 报告必须区分 extractor failure 与 checker failure
- 误报样本（expected_detection=false）计入 false_positive_rate，禁止从报告中剔除

## 14. Unit Tests

- 每个 operator ≥ 1 个确定性用例（1.26→12.6、31,000 亿 case、causal 合并 case 等手算可验）
- 指标计算器正确性（构造已知 P/R/F1 假结果核对）
- seed 固定 → 输出一致

## 15. Integration Tests

- 与 CARD-05 Checker 集成：注入 mutations → 检测结果符合预期（10 个 operator 全跑）
- 与 CARD-11 集成：`--suite cn_agent_v2 --set synthetic` 包含 finfuzz 报告

## 16. Benchmark

输出：Overall Precision/Recall/F1、False Positive Rate、per-error-type Recall、Holdout Performance。**Target / TO BE MEASURED**——未运行前只写目标不写假数字，接入 CARD-11 报告体系。Ablation 对照：`无 FinFuzz 常规测试` vs `含 FinFuzz` 的错误检测覆盖率。

## 17. Demo Flow

Demo 步骤 E2（DEMO_FLOW.md）：FinFuzz 注入一个单位/期间/因果错误到正确研报 → Report Checker/Validator 捕获 → 展示错误类型、原始值、正确值、证据、建议。答辩展示批量报表（per-error-type recall 表格）。

## 18. Acceptance Criteria（验收标准）

- [ ] 10 个 Mutation Operator 全部实现并有确定性用例
- [ ] 指标计算：Overall + per-error-type 全部有单测
- [ ] extractor vs checker 区分有测试
- [ ] 与 CARD-11 集成测试通过
- [ ] 报告可复现（seed 固定）
- [ ] 无编造数字（未运行时为 TARGET/TO BE MEASURED）

## 19. Priority

**P1**（初赛增强；核心 5 个 operator——numeric/unit/period/scope/citation——优先，其余跟进）；不阻塞主链。

## 20. Competition Stage

初赛：10 类 operator 基础版 + per-error-type 指标；决赛：更多 operator（汇率/股份拆分）、自适应变异、高级可视化。

## 21. Estimated Complexity

约 4 人日（operators 2 + suite/指标 1 + benchmark 集成 1）。

## 22. Fallback / Degradation Strategy

- 时间不足：5 个核心 operator + Overall 指标先行，per-error-type 完整化决赛补
- 无真实数据 → Synthetic 集先行，Real 集标注后接入
- 断网不影响（全部本地确定性）

## 23. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |