# CARD-03: Financial Analysis Engine（财务分析引擎）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（9/23–9/29） |
| 对应赛题 | 赛题2 主方向 |
| 依赖 | CARD-02（NormalizedFact）、CARD-04（可比性信号，可后接） |
| 实现复杂度 | 中高（约 4–5 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/analysis/`：在规范化数据上执行确定性财务分析——14 项指标 + 4 类诊断信号。修复 v2 方案的两处金融逻辑硬伤：**YTD 直接算 QoQ** 与 **亏损基期百分比同比**。

## 2. 对应竞赛评分点

计算准确性（同比/环比/单季化）、分析逻辑（诊断信号）、金融专业性（盈利状态语义）。

## 3. 为什么需要这个模块

赛题2 明确考察"同比、环比计算的准确性"与"利润与现金流背离等问题识别"。v2 的 `compute_qoq(current, prev)` 对 A 股 YTD 披露是错的；`compute_yoy` 对亏损基期输出误导性百分比。这两处会被专业评委当场击穿。

## 4. 输入 / 输出

- **输入**：`NormalizedFact[]`（同 scope/version 配对校验后的序列）
- **输出**：`AnalysisResult`：指标表（含计算过程）+ 诊断信号列表 + data_complete 标记

## 5. 数据模型

```python
@dataclass
class MetricResult:
    metric: str             # 见第 7 节 14 项
    value: float | None
    unit: str
    period_key: str
    comparison: str | None  # yoy | qoq | level
    comparison_semantic: str | None  # normal | turnaround(扭亏为盈) | to_loss(由盈转亏)
                                   # | loss_widening | loss_narrowing | not_computable
    delta_abs: float | None  # 状态迁移时输出绝对变动额，不输出百分比
    delta_pct: float | None  # 仅 normal 语义输出
    calculation_id: str      # 绑定 Calculation 记录

@dataclass
class DiagnosticSignal:
    signal_id: str          # earnings_quality_warning | receivable_risk | inventory_pressure
                           # | non_recurring_contribution
    periods: list[str]
    detail: str             # 确定性拼接
    metric_calculation_ids: list[str]
```

## 6. API / Tool Contract

```python
def compute_yoy(current, previous) -> MetricResult:
    """previous==0 → not_computable（禁止百分比）；
    previous<0<current → turnaround，返回绝对变动；
    previous>0>current → to_loss，绝对变动；
    同负 → loss_widening/loss_narrowing，绝对变动+方向；
    同正 → normal，百分比。"""

def compute_single_quarter_qoq(current_q, previous_q) -> MetricResult:
    """输入必须是 convert_ytd_to_single_quarter 之后的产品（CARD-02）。"""

def analyze_financials(facts: list[NormalizedFact]) -> AnalysisResult: ...

def run_diagnostics(metrics) -> list[DiagnosticSignal]: ...
```

Agent 工具 `AnalyzeCnFinancialsTool`：入参 `document_id 或 symbol`；出参 `status / metrics / signals / data_complete / missing[]`。

## 7. 金融逻辑

**14 项指标**（含期间对齐表，v3.0 原方案缺失——角色 M3 点）：

| 指标 | metric 键 | 计算期间 | 来源 | 备注 |
|---|---|---|---|---|
| Revenue YoY | revenue | FY/TTM | CARD-02 normalize | 同比 |
| Single-quarter Revenue QoQ | revenue | SINGLE_QUARTER | CARD-02 差分后 | 环比 |
| Net Profit YoY | net_profit_parent | FY/TTM | CARD-02 normalize | 归母净利润（非合并净利润） |
| Deducted Net Profit YoY | net_profit_deducted | FY/TTM | CARD-02 normalize | |
| Gross Margin | (revenue − operating_cost) / revenue | FY/TTM | 派生 | 分母必须是同期间 revenue |
| Net Margin | net_profit_parent / revenue | FY/TTM | 派生 | |
| ROE | net_profit_parent / average_equity_parent | FY/TTM | 派生 | 平均净资产=期初+期末/2 |
| Operating CFO / Net Profit | cfo / net_profit_parent | FY/TTM | 派生 | 盈利质量诊断信号分母 |
| Receivables / Revenue | receivables / revenue | Revenue=FY/TTM, Receivables=期末 | 派生 | 混合期间，标注口径 |
| Inventory / Revenue | inventory / revenue | Revenue=FY/TTM, Inventory=期末 | 派生 | 混合期间，标注口径 |
| Contract Liabilities | contract_liabilities | 期末（POINT_IN_TIME） | 原始 | 存量值，不做同比/环比 |
| CapEx | capex | FY/TTM | CARD-02 normalize | |
| FCF | cfo − capex | FY/TTM | 派生 | CARD-02 cfo_minus_capex |
| Non-recurring Profit / Net Profit | (net_profit_parent − net_profit_deducted) / net_profit_parent | FY/TTM | 派生 | |

**4 类确定性诊断规则**：

| 条件 | 信号 |
|---|---|
| 利润上涨 + CFO 下降 | earnings_quality_warning |
| 收入上涨 + 应收增速显著高于收入增速 | receivable_risk |
| 收入上涨 + 存货增速显著高于收入增速 | inventory_pressure |
| 净利润上涨 + 扣非净利润下降 | non_recurring_contribution |

"显著高于"阈值集中为模块常量并注释依据。**信号只是信号**：LLM/报告不得将 signal 直接写成确定因果（validator 强制：signal 引用必须保留 signal 语义措辞，因果表述必须有独立证据）。

## 8. Edge Cases

1. Q4 单季 = FY − Q3YTD（任一缺失 → Q4 指标 None，不插值）
2. 扣非净利润缺失 → 跳过该指标 + data_complete=False（不得用净利润替代）
3. 亏损基期全部走状态迁移语义（第 6 节）
4. ROE 用加权平均 ROE 披露值优先，缺失则期末净资产近似并标注口径
5. 跨 scope/version 配对 → CARD-02 校验拒绝，本卡不重复实现
6. 期间序列不连续 → 断点处禁止跨断点环比，明确标注

## 9. Failure Mode

任一必备输入缺失 → 对应指标 None + missing 登记，绝不编造。诊断信号在输入指标不完整时静默不产生该信号（宁缺勿假）。

## 10. Validator Rules

- 所有 MetricResult 的 calculation_id 可解析（公式+输入证据可复核）
- 状态迁移语义的输出禁止出现百分比（validator 断言）
- signal 引用措辞检查（不得出现"因为...所以导致"式确定因果，除非有独立因果证据）

## 11. Unit Tests

- 指令算例：Q1=100/H1=230/Q3YTD=390/FY=540 → 单季 100/130/160/150 → QoQ 正确值
- 同比五分支（normal/扭亏/转亏/亏损扩大/亏损收窄）+ 零基期 not_computable
- 4 类诊断信号的正例/反例（各 ≥2 用例）
- 缺扣非/缺 Q3YTD/序列断点的降级行为

## 12. Integration Tests

CARD-01→02→03 全链跑合成年报；信号进入 Claim 生成（fact 级，evidence 绑定）。

## 13. Benchmark

Calculation Accuracy 指标接入 CARD-11：合成集上 14 指标数值精确匹配；真实集上与人工标注对照。

## 14. Demo Method

财务分析页：指标表（每行可展开公式与输入证据）+ 信号徽章（点击看触发条件的数值依据）。

## 15. 验收标准

- [ ] 第 11 节全部封闭算例通过（含指令原文的 YTD 算例）
- [ ] 状态迁移语义全覆盖且无百分比泄漏
- [ ] 全部指标带 calculation_id 可回溯
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
