# CARD-16: DCF 完整实现（修正版）

| 属性 | 值 |
|---|---|
| 优先级 | P2 |
| 竞赛阶段 | 决赛版 |
| 对应赛题 | 赛题4（决赛深度） |
| 依赖 | CARD-08（估值框架/假设登记）、CARD-02（财务输入） |
| 实现复杂度 | 中高（约 4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/valuation_dcf.py`：金融逻辑修正后的 FCFF DCF。修正 v2 三处硬伤：EV≠Equity、预测变量不明确、与相对估值做无依据的区间合并。

## 2. 对应竞赛评分点

模型结构、假设依据、财务勾稽关系、估值结果合理性、敏感性分析完整性。

## 3. 金融逻辑（本卡核心，全部为修正项）

**3.1 企业价值→股权价值桥**（必须）：

```text
Enterprise Value (FCFF 折现)
  − Net Debt（有息负债 − 现金及等价物）
  − Minority Interest（少数股东权益）
  + Non-operating Assets（非经营性资产，如有披露）
  ± Other Adjustments（显式列出）
  = Equity Value
Equity Value / Diluted Shares = Implied Price
```

桥接每项必须绑定 Evidence（缺 Net Debt 数据 → 阻断，不得假设为零）。

**3.2 预测逻辑显式化**：显式预测变量路径（Revenue Growth / EBIT Margin / Tax Rate / D&A / CapEx / ΔNWC）或 FCFF growth model，二选一并声明。

**3.3 假设五元组**：每个预测假设登记 `{value, source, reason, valid_from, assumption_id}`（Assumption Registry，与 CARD-08 同一套）。

**3.4 估值呈现**：DCF range、PE range、PB range、PS range **分别展示** + `valuation_method_dispersion` 报告。**禁止**交集/并集合成。

**3.5 ValuationApplicabilityGate**（行业适配）：

| 行业 | 优先方法 |
|---|---|
| 银行 | PB/ROE/DDM（不做 FCFF DCF） |
| 保险 | PEV/PB |
| 普通制造业 | PE + DCF |
| 未盈利成长 | PS / EV-Sales |

Gate 输出适用性判定 + 理由；传统 FCFF DCF 不强行覆盖所有行业。

## 4. 其余字段

- **输入/输出**：规范化财务 + 行业分类 → DcfResult（含桥接明细、敏感性 WACC×g 矩阵、dispersion）
- **Edge Cases**：净债务为负（净现金，桥接方向正确）；少数股东权益缺失 → 阻断或保守标注；wacc≤g → ValueError（终值发散）
- **Failure Mode**：桥接任一项无证据 → 整体降级"演示级"并显式警示
- **Unit Tests**：封闭算例（手工算到分）；桥接勾稽（EV−净债务−少数股东=股权）；单调性；银行 Gate 拒绝 DCF
- **Demo Method**（决赛）：展示桥接表逐项证据 + 与相对估值的 dispersion 对照
- **验收标准**：桥接勾稽测试、Gate 全行业分支、假设五元组全覆盖、无区间合并

## 5. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
