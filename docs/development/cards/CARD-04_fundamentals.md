# CARD-04: 财务趋势分析引擎（fundamentals.py）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段1 / P0 |
| 对应选题 | 选题2 上市公司财务报告分析 |
| 依赖 | 无，可独立开工 |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/fundamentals.py`：从快照财务数据中确定性计算同比/环比、识别非经常性损益异常与利润-现金流背离，输出全量挂 Evidence ID 的趋势报告，并注册为 Agent 工具。这是竞赛选题 2 的核心考察点。

## 2. 竞赛考察点映射

选题 2 明确考察：
- 财务数据提取及**同比、环比计算的准确性** → 本卡的 `compute_yoy / compute_qoq`
- 对**非经常性损益**的识别 → `detect_non_recurring_anomaly`
- 对**利润与现金流背离**的识别 → `detect_profit_cashflow_divergence`
- 对会计口径变化的识别 → 期间口径由现有 `src/cn/periods.py` 保证，本卡复用不重造

## 3. 现状盘点

- `src/cn/providers/snapshot.py` 提供版本化快照读取；财务域数据结构先通读再对接（动手前读快照中 income/cashflow 相关字段）。
- `src/validation/financial_validator.py` 已有口径校验，本卡输出必须能被其校验。
- 现有工具注册模式见 `src/agents/tools/cn_tools.py`。

## 4. 详细设计

### 4.1 核心数据结构

```python
@dataclass
class TrendMetric:
    label: str            # 指标名，如 "营业收入"
    value: float
    unit: str             # 元 / 亿元，与快照一致
    period: str           # 报告期 key，复用 periods.py
    yoy: float | None     # 同比变化率（小数），不足一年为 None
    qoq: float | None     # 环比变化率
    evidence_id: str

@dataclass
class DivergenceReport:
    periods: list[str]          # 出现背离的报告期
    net_income: list[float]      # 对应期净利润
    operating_cf: list[float]    # 对应期经营现金流净额
    consecutive: int            # 连续背离期数
    severity: str               # none | single | persistent
    evidence_ids: list[str]

@dataclass
class AnomalySignal:
    kind: str              # non_recurring | divergence | growth_reversal
    period: str
    detail: str            # 人可读描述（确定性拼接，非 LLM）
    evidence_ids: list[str]

@dataclass
class FundamentalsReport:
    symbol: str
    metrics: list[TrendMetric]
    divergence: DivergenceReport
    anomalies: list[AnomalySignal]
    data_complete: bool     # 任一必备序列缺失时 False 并附 missing 字段
```

### 4.2 函数契约

```python
def compute_yoy(current: float, year_ago: float) -> float:
    """(current - year_ago) / |year_ago|。year_ago == 0 时抛 ValueError（数据不可比，不静默）。"""

def compute_qoq(current: float, prev: float) -> float: ...

def analyze_growth(financials_series: list[dict]) -> list[TrendMetric]:
    """输入按报告期排序的财务序列（快照原始结构），输出营收/归母净利/扣非净利的 TrendMetric。"""

def detect_profit_cashflow_divergence(income_series, cashflow_series) -> DivergenceReport:
    """净利润与经营现金流净额符号相反或持续显著背离（|净利-CF|/|净利|>阈值且连续>=2期）。"""

def detect_non_recurring_anomaly(net_income_series, deducted_income_series) -> AnomalySignal | None:
    """扣非净利润/净利润 比值环比骤降（阈值见模块常量，写明依据）。"""

def analyze_financial_trends(snapshot, symbol: str) -> FundamentalsReport:
    """汇总入口；任何必备序列缺失 → data_complete=False，绝不编造。"""
```

### 4.3 数据缺口处理

- 扣非净利润：检查 `src/cn/providers/akshare.py` 是否可取；若快照无该字段，`detect_non_recurring_anomaly` 返回 `None` 并在 `FundamentalsReport.missing` 中登记，**不得用净利替代**。
- 序列不足（<2 期）：对应指标 yoy/qoq 置 None，不插值、不外推。

### 4.4 工具注册

`AnalyzeCnFinancialTrendsTool`（注册进 `cn_tools.py`，遵循现有工具信封）：
- 入参：`symbol`
- 出参：`status`、`report`（FundamentalsReport 序列化）、每指标带 `evidence_id / as_of / unit / period`
- 快照缺失 → `status: error` + error_code

## 5. 实施步骤

1. 通读快照财务数据真实结构 + `periods.py` 的期间 key 规则，固化序列构造方式（写入执行备注）。
2. 实现纯函数层（4.2 全部），先写测试：手工构造已知数列（含亏损期、零基期、序列缺口），断言精确数值。
3. 实现 `analyze_financial_trends` 汇总与缺口处理。
4. 注册工具 + `tests/test_cn_tools.py` 补契约用例。
5. 用一份 illustrative 快照端到端跑通，输出样例贴进执行备注。

## 6. 验收标准

- [ ] `tests/test_cn_fundamentals.py` 覆盖：正常同比环比、零基期抛错、亏损期符号、连续背离判定、扣非缺失时 data_complete=False
- [ ] 全部输出字段带 evidence_id / unit / period；无 LLM 参与
- [ ] 工具契约测试通过（ok 与 error 两路）
- [ ] 全部测试通过

## 7. 红线（本卡特有）

- 全部确定性代码；禁止用 LLM 生成或"修正"任何指标值
- 阈值常量集中在模块顶部命名并注释依据（答辩会被问）
- 增长率分母为零必须抛错/标注，不得返回 0 或 inf

## 8. 执行备注（agent 填写）

| 日期 | 记录（快照字段映射 / 阈值调整 / 偏差） |
|---|---|
|  |  |
