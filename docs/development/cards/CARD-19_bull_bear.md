# CARD-19: Bull/Bear 结构化对照

| 属性 | 值 |
|---|---|
| 优先级 | P3 |
| 竞赛阶段 | 决赛可选 |
| 对应赛题 | 赛题6 反向验证增强 |
| 依赖 | CARD-18 |
| 实现复杂度 | 低（约 2 人日） |
| 状态 | ☐ 未开始 |

## 1. 目标

多空双视角对照模块。**修正 v2 错误**：删除 `Σ(argument × (1 + 0.5 × evidence_count))` 类无理论依据的多空评分与"谁赢"判定——目标是辅助研究员形成双向验证框架，不是让 Agent 裁决胜负。

## 2. 金融逻辑

**只输出六件结构化产物**：Bull Case（多头论据）、Bear Case（空头论据）、Unresolved Questions（双方持证分歧）、Key Assumptions（关键假设清单）、Falsification Conditions（证伪条件）、Tracking Indicators（跟踪指标）。

论据全部走 Claim 模型（fact/inference 标注 + 证据绑定）；**不存在 bull_score / bear_score / 胜负结论字段**（结构断言测试）。

## 3. 其余字段

- **输入/输出**：主链产物（分析/估值/检索/信号）→ 六段结构化对照
- **Edge Cases**：某侧论据不足 → 如实标注"该视角证据有限"，不硬凑对称
- **Failure Mode**：论据数值必须过 unverified_number；无证据论点标 unsupported
- **Unit Tests**：六产物结构；无评分字段断言；单侧缺失路径
- **Demo Method**（决赛）：备忘录 Counter-thesis 段与本案对照展示
- **验收标准**：零评分机制（测试强制）；六产物齐全；论据 100% 有 claim 标注

## 4. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
