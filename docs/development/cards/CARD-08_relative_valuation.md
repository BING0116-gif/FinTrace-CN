# CARD-08: Relative Valuation & Sensitivity（相对估值与敏感性）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（10/7–10/11） |
| 对应赛题 | 赛题4 重要金融工具（初赛版） |
| 依赖 | CARD-02（规范化财务）、CARD-07（计算记录） |
| 实现复杂度 | 中（约 3–4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

扩展现有 `src/cn/valuation.py`（保留 PE/PB/PS + IQR 离群剔除 + RAW 价格纪律）：增加 Bear/Base/Bull 三情景、EPS×Target PE 与 ROE×Target PB 敏感性矩阵、Assumption Registry 登记全部输入假设，实现每个估值结果"数据→公式→假设→输出"四层可追溯。**不做**与 DCF 区间的交集/并集（无理论依据，v2 错误设计，已废弃）。

## 2. 对应竞赛评分点

自动化估值建模考察点：模型结构、假设依据、财务勾稽、结果合理性、敏感性分析完整性。

## 3. 为什么需要这个模块

赛题4 是初赛版估值主答案（DCF 降决赛）；现有能力缺敏感性分析（通知明确考察"敏感性分析完整性"）与假设登记（"假设依据"考察点）。

## 4. 输入 / 输出

- **输入**：规范化财务（EPS、ROE、BPS）、RAW 价格与股本、同业可比集、情景假设集
- **输出**：`ValuationResult`（各方法区间 + 敏感性矩阵 + dispersion 报告 + 假设清单）

## 5. 数据模型

```python
@dataclass
class Assumption:            # Assumption Registry 单条
    assumption_id: str
    value: float | str
    source: str             # evidence_id | "assumption: 理由"
    reason: str
    valid_from: str

@dataclass
class ScenarioValuation:    # 每方法每情景
    method: str             # pe | pb | ps
    scenario: str           # bear | base | bull
    value_low: float
    value_mid: float
    value_high: float
    assumption_ids: list[str]
    calculation_ids: list[str]

@dataclass
class SensitivityMatrix:
    x_name: str             # 如 Target PE
    y_name: str             # 如 EPS（或 ROE × Target PB 版本）
    x_values: list[float]
    y_values: list[float]
    matrix: list[list[float]]   # implied price
    assumption_ids: list[str]

@dataclass
class ValuationResult:
    scenarios: list[ScenarioValuation]     # 各方法分别展示，不合并
    sensitivity: list[SensitivityMatrix]
    method_dispersion: dict                 # 各方法区间离散度报告
    applicability_note: str                # 方法适用边界（确定性模板）
```

## 6. API / Tool Contract

```python
def build_scenarios(base_inputs, assumption_registry) -> list[ScenarioValuation]: ...
def sensitivity_pe_eps(eps_range, target_pe_range, shares) -> SensitivityMatrix: ...
def sensitivity_pb_roe(roe_range, target_pb_range, bps, shares) -> SensitivityMatrix: ...
def method_dispersion(scenarios) -> dict: ...
```

Agent 工具 `RunCnRelativeValuationTool`（扩展现有估值工具或新增）：入参 `symbol`；出参 `status / scenarios / sensitivity / dispersion / assumptions`。

## 7. 金融逻辑

1. **EPS/ROE 期间定义**（v3.0 原方案完全遗漏，这是角色 B 必查点）：EPS = `net_profit_parent_ttm / diluted_shares`（TTM，来自 CARD-02 的现有引擎）；**禁止**用 FY 静态 EPS 做估值（PE 估值隐含的是"未来 12 个月盈利"）。ROE = `net_profit_parent_ttm / average_equity_parent`（平均净资产，近似取期初+期末/2）。
2. **情景定义**：Bear/Base/Bull 的 EPS 增速与目标倍数各登记假设（如 base=分析师一致预期若有证据，否则 assumption 并标注）
3. **敏感性**：EPS × Target PE 矩阵（行=EPS 区间，列=目标 PE 区间，格子=EPS×PE，y 轴语义直接）；**PB 矩阵初赛简化**（v3.0 原方案"ROE × Target PB 矩阵"数学上 ROE 不进价格公式，格子会是 BPS×PB 与 y 轴 ROE 无关）：初赛 ROE × PB 矩阵 **二选一**——①初赛直接用 BPS × PB 矩阵（诚实，y 轴放 BPS 情景而非 ROE）+ PB 适用边界说明；②决赛做"PB = f(ROE, COE, g)"显式假设模型（类比 Gordon 增长模型），矩阵格子=BPS×PB 且 PB 由 ROE 推导，全部入 Assumption Registry。**初赛采用选项①**（简化版，决赛做②）。
4. 各方法（PE/PB/PS）区间**分别展示**，输出 method_dispersion（如各方法 mid 的极差/均值），不制造合成"最终区间"
5. 市值与倍数计算继续使用 RAW 价格（现有纪律）
6. 负 EPS / 负 BPS → 对应方法标注 not_applicable（不输出负 PE 伪区间）

## 8. Edge Cases

1. 同业可比不足 3 家 → IQR 不做，标注样本不足
2. 总股本缺失 → 阻断每股估值（fail-closed，对应失败注入演示 #1）
3. 假设覆盖 sourced 参数 → 拒绝（只允许登记 assumption 性参数）
4. EPS 为负 → PE 方法 not_applicable，PB/PS 继续
5. 分红导致 BPS 异常 → 数值如实，边界说明模板标注

## 9. Failure Mode

输入数据缺失 → 对应方法整体缺位 + missing 登记，不用别的方法的值填补。全部假设无 sourced 依据 → 结果整体降级标注"纯假设演示"。

## 10. Validator Rules

- 每个 ScenarioValuation 的 assumption_ids 全部可解析
- 敏感性矩阵单调性检查（PE↑→价格↑；EPS↑→价格↑）
- dispersion 报告必须存在（禁止只给单点值）

## 11. Unit Tests

- 矩阵手工算例（EPS 3 档 × PE 3 档，手算 9 格核对）
- 单调性断言；负 EPS 的 not_applicable；股本缺失阻断
- 假设登记完整性（无 assumption_id 的结果被拒）

## 12. Integration Tests

CARD-02→08→10 全链：估值结果进备忘录，点击任一单元格 → 假设 → 数据 → 证据。

## 13. Benchmark

Calculation Accuracy（估值数值精确匹配）接入 CARD-11。

## 14. Demo Method

估值页：三方法区间条 + 敏感性矩阵热力图 + 点击单元格展开假设来源。

## 15. 验收标准

- [ ] 敏感性矩阵手工算例 + 单调性测试通过
- [ ] 全部假设入 Registry 且可追溯（数据→公式→假设→输出链路测试）
- [ ] 方法分别展示 + dispersion 报告（无合成区间）
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
