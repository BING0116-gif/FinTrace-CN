# CARD-05: DCF 估值与敏感性分析（valuation_dcf.py）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段1 / P0 |
| 对应选题 | 选题4 自动化估值建模 |
| 依赖 | 无，可独立开工（输出与现有 `valuation.py` 相对估值对接时需读其接口） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/valuation_dcf.py`：两阶段 FCFF 折现 + WACC + **敏感性矩阵** + 估值区间三角验证（DCF 与现有相对估值交叉），全部假设显式化并区分 sourced fact 与 assumption，注册为工具。这是选题 4 明确考察"敏感性分析完整性"的直接响应。

## 2. 竞赛考察点映射

| 选题4考察点 | 本卡落点 |
|---|---|
| 模型结构 | 两阶段 FCFF（显式预测期 + 永续） |
| 假设依据 | `DcfAssumptions` 每参数标注 evidence_id 或 assumption |
| 财务勾稽关系 | FCF 从财务序列推导，勾稽校验复用 financial_validator 思路 |
| 估值结果合理性 | 三角验证区间 + implied price 与现价对照 |
| 敏感性分析完整性 | WACC × g 双参数 5×5 矩阵 + 区间输出 |

## 3. 现状盘点

- `src/cn/valuation.py`：已有相对估值（PE/PB/PS、IQR 离群剔除、置信度）——本卡不改动它，只做组合层对接。
- 历史教训：仓库曾移除美股 DCF 管线（见 AGENTS.md 维护面说明），本卡是**全新 A 股版实现**，不复活任何旧模块。

## 4. 详细设计

### 4.1 假设结构（事实与假设分离的核心）

```python
@dataclass
class DcfAssumptions:
    rf_rate: float                    # 无风险利率（sourced：可挂国债收益率证据）
    equity_risk_premium: float        # assumption 或 sourced
    beta: float | None                # 无快照来源时 None，走保守默认并标注
    cost_of_debt: float
    tax_rate: float
    debt_ratio: float                 # D/(D+E)
    perpetual_growth: float           # 永续增长率 g
    forecast_years: int               # 显式期年数，默认 5
    provenance: dict[str, str]        # 每参数: evidence_id | "assumption: <理由>"
```

纪律：`provenance` 中没有任何 sourced 标注的参数，输出报告必须整体降级为"纯假设演示"，并在结果里显式声明。

### 4.2 函数契约

```python
def cost_of_equity(a: DcfAssumptions) -> float:
    """CAPM: rf + beta * erp。beta 为 None 时抛 ValueError（不允许静默用 1.0）。"""

def wacc(a: DcfAssumptions) -> float:
    """E/(D+E)*ke + D/(D+E)*kd*(1-t)。校验 wacc > perpetual_growth，否则 ValueError（终值发散）。"""

def free_cash_flow_series(financials_series) -> list[float]:
    """FCFF = EBIT*(1-t) + D&A - CapEx - 营运资本增加；字段缺失则抛 DataIncompleteError（errors.py 复用）。"""

def two_stage_dcf(fcfs: list[float], explicit_growth: list[float] | float,
                  wacc_v: float, g: float) -> "DcfResult":
    """显式期逐年折现 + 终值 TV = FCF_last*(1+g)/(wacc-g)。返回各年现值明细。"""

def sensitivity_matrix(base: "DcfResult", fcfs, wacc_range: list[float],
                       g_range: list[float]) -> "SensitivityGrid":
    """默认 wacc ±1% 步长 0.5%、g ±0.5% 步长 0.25% 的 5×5；每格为股权价值/implied price。"""

def valuation_interval(dcf: "DcfResult", peer_result, shares, price) -> "ValuationInterval":
    """三角验证：DCF 区间与相对估值区间取交集或并集（不重叠时并集+警示），输出 low/mid/high、upside、来源标注。"""
```

### 4.3 输出结构

```python
@dataclass
class DcfResult:
    equity_value: float
    implied_price: float
    per_year_pv: list[float]      # 勾稽：sum + TV_pv == equity_value
    assumptions: DcfAssumptions
    data_grade: str               # sourced | mixed | assumption_only

@dataclass
class SensitivityGrid:
    wacc_values: list[float]
    g_values: list[float]
    matrix: list[list[float]]     # implied price
    monotonicity_check: bool      # wacc↑→估值↓，g↑→估值↑，测试断言
```

### 4.4 工具注册

`RunCnDcfValuationTool`（`cn_tools.py`）：
- 入参：`symbol`，可选 `assumptions_overrides`（仅允许覆盖 provenance 中为 assumption 的参数，覆盖 sourced 参数返回 error）
- 出参：`status / dcf / sensitivity / interval`，全部含 evidence_id 或 assumption 标注

## 5. 实施步骤

1. 通读 `valuation.py` 相对估值输出结构，确定 `valuation_interval` 对接字段。
2. 实现纯函数层，测试先行：封闭数值算例（手工计算器核对到分），含终值、单年现值、WACC 校验。
3. 实现敏感性矩阵与单调性断言。
4. 实现三角验证区间（交集/并集逻辑 + 不重叠警示）。
5. 注册工具 + 契约测试（ok / assumption_only 降级 / 数据缺失 error 三路）。
6. 用 illustrative 快照端到端跑通，输出样例贴执行备注。

## 6. 验收标准

- [ ] 封闭算例数值精确匹配（手工可验）；`sum(per_year_pv) + TV_pv == equity_value` 勾稽测试
- [ ] 敏感性矩阵单调性测试通过；`wacc <= g` 抛 ValueError
- [ ] assumption_only 降级路径有测试；无 sourced 参数时结果带显式警示
- [ ] 工具契约测试三路通过；全部测试通过

## 7. 红线（本卡特有）

- 模型计算零 LLM；假设参数 provenance 强制登记，无登记不输出
- 输出必须区分"事实（财务数据/股价）"与"假设（折现率/增长率）"两类标注
- 不复活历史美股 DCF 代码，全部新写
- 估值输出必须含适用边界声明文本（确定性模板拼接）

## 8. 执行备注（agent 填写）

| 日期 | 记录（算例核对 / 阈值 / 偏差） |
|---|---|
|  |  |
