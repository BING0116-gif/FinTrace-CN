# CARD-02: Financial Normalization Engine（财务规范化引擎）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（9/23–9/29） |
| 对应赛题 | 赛题2/5 的数据基础（全主链） |
| 依赖 | CARD-01（ExtractedFact 输入）、**现有** `src/cn/periods.py`（FinancialPeriodEngine）、**现有** `src/cn/evidence.py`（Evidence Ledger 扩展）、**现有** `src/cn/domain.py`（FinancialStatement） |
| 实现复杂度 | 中高（约 4–5 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/normalization/`：把异构披露格式统一为规范金融数据。处理单位/币种/比率/期间/口径/版本六类规范化，**桥接而非重写**仓库现有 `FinancialPeriodEngine` 完成 YTD→单季和 TTM 推导，正确区分 flow 与 stock 语义，为主链所有计算提供干净输入。这是"数据准确性"评分项的地基。

**关键纠偏**：v3.0 原方案声称"v2 完全没有此层"且新建 `convert_ytd_to_single_quarter`——经审查仓库已存在 `FinancialPeriodEngine.derive_single_quarters()`（含 stock 禁差分抛错）和 `derive_ttm()`。本卡**不得重复造**：做薄适配器，复用现有引擎作为唯一单季化与 TTM 来源。

## 2. 对应竞赛评分点

数据准确性（单位/期间错误是研报最常见硬伤）、金融专业性（口径意识）、计算准确性（下游全部依赖）。

## 3. 为什么需要这个模块

真实 A 股披露的数值带各种单位（元/万元/百万元/亿元，甚至表头声明+正文混用）、期间（YTD 累计 vs 单季）、口径（合并/母公司）、版本（原披露/重述/更正后）。不规范化直接计算 = 必然出错。同时，必须把现有引擎的正确设计（stock 禁差分、TTM 推导、仅对 income/cashflow 生效）接入主链，不平行造轮子。

## 4. 输入 / 输出

- **输入**：`ExtractedFact[]`（CARD-01 产物，raw_value + unit + period + scope 原始字符串）
- **输出**：`NormalizedFact`：`{normalized_fact_id, metric, value(base 单位), currency, period_key, period_kind(ytd_cumulative | single_quarter | ttm | point_in_time), scope, version, available_at, source_fact_id, financial_statement_id}`；附加 `list[DerivedPeriod]`（单季化后，从现有引擎产出）

## 5. 数据模型

```python
class Unit(str, Enum):        # 元 M | 万元 W | 百万元 MM | 亿元 YI，基准=元
class Currency(str, Enum):    # CNY | USD | HKD | ...
class Ratio(str, Enum):       # PERCENT | BP | MULTIPLE
class Scope(str, Enum):       # CONSOLIDATED | PARENT
class Version(str, Enum):     # AS_REPORTED | RESTATED | CORRECTED
class PeriodKind(str, Enum):  # YTD_CUMULATIVE | SINGLE_QUARTER | TTM | POINT_IN_TIME

@dataclass
class NormalizedFact:
    normalized_fact_id: str
    metric: str               # 标准指标名（来自 §7.1 字典，不含层级歧义）
    value: float              # 基准元
    currency: Currency
    period_key: str           # 唯一期间键，复用现有 FinancialPeriodEngine 格式：YYYYQ1 / YYYYH1 / YYYY9M / YYYYFY
    period_kind: PeriodKind   # YTD_CUMULATIVE（披露值本身）| SINGLE_QUARTER（差分后）| TTM（推导后）| POINT_IN_TIME（stock）
    scope: Scope
    version: Version
    available_at: str
    source_fact_id: str       # 回链 CARD-01 的 ExtractedFact
    financial_statement_id: str | None  # 桥接到现有 FinancialStatement 的 id
```

**flow vs stock 语义**：flow（营业收入/营业利润/净利润/CFO/CapEx/费用）是期间流量，`period_kind` 可以是 `YTD_CUMULATIVE`（原始披露）或 `SINGLE_QUARTER`/`TTM`（引擎推导）；stock（现金/存货/应收账款/总资产/总负债）是时点存量，`period_kind` **只能是** `POINT_IN_TIME`，调用引擎会收到 `PeriodEngineError`（现有引擎已实现 stock 禁差分，本卡桥接时不吞此异常）。

## 6. API / Tool Contract

```python
# src/cn/normalization/units.py
def normalize_unit(raw_value: str | float, unit: str) -> float:
    """万元=10^4, 百万元=10^6, 亿元=10^8；基准单位统一为元。"""

# src/cn/normalization/periods.py（桥接现有引擎，不重写）
def canonical_period(raw_period: str, report_type: str) -> str:
    """返回现有引擎可接受的期间键：YYYYQ1 / YYYYH1 / YYYY9M / YYYYFY。
    错误键抛 ValueError，不猜测。"""

def detect_period_kind(source_table_name: str, column_header: str | None, report_type: str) -> PeriodKind:
    """YTD 判定规则（本卡核心，解决 v3.0 遗漏的判定盲区）——见 §7.2。
    无法判定 → 返回 None + warning，禁止猜测。"""

# src/cn/normalization/adapter.py（桥接现有 FinancialPeriodEngine）
def facts_to_financial_statements(normalized_facts: list[NormalizedFact]) -> list[FinancialStatement]:
    """把 NormalizedFact 投影到现有 src/cn/domain.FinancialStatement，
    scope→statement_type/scope, metric→value_dict, period_key→fiscal_period。
    单条失败则该 fact 不入投影，不中断其余。"""

def derive_single_quarters(statements: list[FinancialStatement]) -> list[DerivedPeriod]:
    """委托现有 FinancialPeriodEngine.derive_single_quarters()。
    输入校验：statement_type 必须是 income|cashflow；scope/version 同组内一致。"""

def derive_ttm(statements: list[FinancialStatement]) -> list[DerivedPeriod]:
    """委托现有 FinancialPeriodEngine.derive_ttm()（v3.0 原方案完全遗漏的 TTM 能力）。"""

# src/cn/normalization/scope.py / version.py
def detect_scope(table_header: str) -> Scope | None: ...
def detect_version(paragraph: str) -> Version: ...  # AS_REPORTED 默认；RESTATED/CORRECTED 信号来自 CARD-04

# src/cn/normalization/__init__.py 主入口
def normalize_document(facts: list[ExtractedFact], document) -> tuple[list[NormalizedFact], list[str]]:
    """返回 (NormalizedFact[], warnings[])。
    内部：单位换算 → canonical_period → detect_period_kind → detect_scope/version → 投影 FinancialStatement → derive_single_quarters → derive_ttm。"""
```

Agent 工具 `NormalizeCnFinancialsTool`：入参 `document_id`；出参 `status / facts / single_quarters[] / ttm[] / warnings[]`。**绝对禁止**自行实现单季化或 TTM——桥接层的存在就是为了强制走现有引擎。

## 7. 金融逻辑

### 7.1 标准指标字典（解决 v3.0 遗漏的"指标同义词+层级"问题）

每条显式绑定 A 股披露的**准确层级**，避免归母 vs 含少数股东混用、营业总收入 vs 营业收入混淆：

| metric 标准键 | 披露名称（同义词） | 财务报表位置 | 层级说明 |
|---|---|---|---|
| `revenue` | 营业收入 / 营业总收入 | 合并利润表 | 合并口径，不取母公司；"营业总收入"取合并表首行 |
| `operating_cost` | 营业成本 | 合并利润表 | |
| `gross_profit` | 营业收入 − 营业成本 | 派生 | 不得从"毛利"行取值（若有披露则取披露值） |
| `operating_profit` | 营业利润 | 合并利润表 | |
| `net_profit` | 净利润 | 合并利润表 | 取"合并净利润"行 |
| `net_profit_parent` | 归属于母公司股东的净利润 | 合并利润表 | **估值 EPS 用这个**（非净利润含少数股东） |
| `net_profit_deducted` | 扣除非经常性损益后归属于母公司股东的净利润 | 合并利润表 | CARD-03 的"扣非净利润"指标来源 |
| `cfo` | 经营活动产生的现金流量净额 | 合并现金流量表 | |
| `capex` | 购建固定资产、无形资产和其他长期资产支付的现金 | 合并现金流量表 | |
| `cfo_minus_capex` | CFO − CapEx | 派生 | FCF（简化版） |
| `total_assets` | 资产总计 | 合并资产负债表 | stock，禁止差分 |
| `total_liabilities` | 负债合计 | 合并资产负债表 | stock，禁止差分 |
| `equity_parent` | 归属于母公司股东权益合计 | 合并资产负债表 | stock；PB 的 BPS 来源 |
| `inventory` | 存货 | 合并资产负债表 | stock |
| `receivables` | 应收账款 | 合并资产负债表 | stock |
| `contract_liabilities` | 合同负债 | 合并资产负债表 | stock |
| `diluted_shares` | 期末总股本 / 稀释后股本 | 股本公告或资产负债表附注 | 时点；缺失 → 估值阻断 |
| `raw_price` | 最近交易日收盘价 | 快照提供者 | 行情链，**必须 RAW 价格** |
| `peers` | 可比公司集 | 快照提供者 | 用于 PE/PB/PS 同业估值 |

**规则**：字典外的 metric → `metric_unknown_xxx` 前缀 + warning；下游指标表不得引用未知 metric。

### 7.2 period_kind 判定规则表（解决 v3.0 遗漏的 YTD/单季判定盲区）

| 来源类型 | 识别条件 | period_kind | 期间键来源 |
|---|---|---|---|
| 合并利润表 / 合并现金流量表主体 | 表头/节名含"合并利润表"、"合并现金流量表" | **YTD_CUMULATIVE** | 文档声明的报告期（FY→YYYYFY，半年报→YYYYH1，三季报→YYYY9M，一季报→YYYYQ1） |
| 年报第三节"主要会计数据和财务指标"摘要表 | 表头含"本报告期/年初至本报告期末"双列 | 按列名："本报告期"→ **SINGLE_QUARTER**（不调用差分）；"年初至本报告期末"→ **YTD_CUMULATIVE** | 同报告期 |
| 季报"主要财务数据"表 | 表头同上双列 | 同上 | 同报告期 |
| 合并资产负债表 | 主体或附注 | **POINT_IN_TIME** | 报告期末日期 |
| 附注（含财务附注） | 段落文本提取的指标 | 按上上文判定；无法判定 → **None + warning** | |
| 公告 | 非报表段落 | **None + warning**（不猜） | |

**判定失败处理**：`period_kind=None` + `warnings.append(f"无法判定 {metric} 的期间语义，跳过单季化/TTM")`。**禁止**将无法判定的值默认当作 YTD 或单季——判错比不转换更糟。

### 7.3 其余规范化逻辑

1. **单位换算**：万元=10^4，百万元=10^6，亿元=10^8；基准单位统一为元
2. **表头优先**：表格数值单位以表头声明为准；正文与表头冲突 → 用表头 + 输出 warning，不静默
3. **期间键**：唯一格式 = `FinancialPeriodEngine` 接受的 `YYYYQ1/H1/9M/FY`；自定义 `period_key` 格式 → ValueError
4. **口径配对**：同比/环比计算（CARD-03）只能用同 scope 同 version 配对；跨 scope → 拒绝
5. **版本**：更正公告后的值标 CORRECTED；重述标 RESTATED（信号来自 CARD-04）

## 8. Edge Cases

1. 千分位逗号、括号负数（会计惯例 `(1,234)` = -1234）、"—"/"N/A" → 解析规则显式枚举
2. 表内混单位（某行万元某行元）→ 行级单位检测，无法判定 → 该行标 unparseable，不猜
3. 单位声明在页眉而非表头 → 向上搜索最近单位声明（限同页）
4. 币种为 USD/HKD 的财务附注 → 保留原币种，不换算，标注 currency
5. Q4 单季推导需要 FY 与 Q3YTD 同口径同版本，缺失 → Q4 为 None 并记录 missing（现有引擎自然处理）
6. 同期间同指标出现两个不同 scope 值 → 各自保留，靠 scope 字段区分
7. 季度报告披露的是 Q3YTD=390（9M 累计），不是 Q3 单季=160 → `detect_period_kind` 正确识别为 YTD_CUMULATIVE，差分引擎推导 Q3 单季

## 9. Failure Mode

任何无法确定语义的值 → `normalized_value=None` + warning，**绝不默认猜测**。规范化失败的 facts 汇总进 `warnings`，CARD-03 跳过对应指标并令 `data_complete=False`。

## 10. Validator Rules

- `normalize_unit` 输出必须与封闭算例一致（单位换算零容差）
- `canonical_period` 返回值必须匹配现有引擎正则 `^(?P<year>\d{4})(?P<kind>Q1|H1|9M|FY)$`，否则 ValueError
- `detect_period_kind` 返回 None 时必须有 warning，禁止返回猜测值
- 桥接层调用 `derive_single_quarters` 时若收到 `PeriodEngineError`（stock 输入）→ 重新抛出，不吞
- scope/version 配对检查供 CARD-03 调用（配对失败 → 禁止计算）

## 11. Unit Tests（封闭算例，手工可验）

- 单位换算全矩阵（元↔万元↔百万元↔亿元）
- **YTD 算例**（指令原文）：Q1=100, H1=230, Q3YTD=390, FY=540 → 单季 100/130/160/150（通过桥接层验证现有引擎输出）
- **TTM 算例**：FY2023=540, H12024=230, H12023=220 → H12024 TTM = 230 + 540 − 220 = 550（桥接现有 `derive_ttm`）
- 括号负数/千分位/N/A 解析
- stock 输入桥接后抛 `PeriodEngineError`（引擎侧）
- 表头正文单位冲突告警
- `detect_period_kind` 对摘要表双列正确分类
- `detect_period_kind` 对无法判定来源返回 None + warning
- 缺 Q3YTD → Q4=None（现有引擎自然处理）
- 混 scope 保留
- 未知 metric → `metric_unknown_xxx` + warning
- 错误期间键（`FY2024`, `2024Q1_YTD`, `Q1 2024`）→ ValueError

## 12. Integration Tests

CARD-01 合成年报 → 本卡 → NormalizedFact + Single Quarters + TTM 全部完整；接入扩展后的 Evidence Ledger（每 NormalizedFact 带回链 + document_id/page/bbox）。

## 13. Benchmark

Unit Accuracy / Period Accuracy / Scope Accuracy / **Period Kind Detection Accuracy** 四指标接入 CARD-11（合成集 + 真实集），目标待冻结。

## 14. Demo Method

UI 展示"原始披露值 → 规范化值"对照表（含单位换算、YTD→单季标注、TTM 推导），旁边列出 warnings——展示系统对脏数据的免疫力。

## 15. 验收标准

- [ ] 第 11 节全部封闭算例通过（含指令原文的 YTD 算例和 v3.0 遗漏的 TTM 算例）
- [ ] 桥接层代码路径存在（grep `derive_single_quarters|derive_ttm` 有调用），无自定义单季化/TTM 实现
- [ ] flow/stock 语义分离有测试保护（stock 输入 → PeriodEngineError 重抛）
- [ ] period_kind 判定失败 → None + warning，零猜测
- [ ] metric 字典覆盖 §7.1 全部指标，未知 metric 走 `metric_unknown_xxx`
- [ ] warnings 机制全覆盖（无法规范的值零静默）
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
