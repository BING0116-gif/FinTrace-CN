# CARD-17: Report Quality Diagnostics（报告质量诊断）

| 属性 | 值 |
|---|---|
| 优先级 | P2 |
| 竞赛阶段 | 决赛版 |
| 对应赛题 | 赛题7 研究报告质量评估 |
| 依赖 | CARD-05（findings）、09（图）、12（回放） |
| 实现复杂度 | 中（约 3 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-agent-evaluation |

## 1. 目标

新建 `src/cn/quality.py`：多维度报告质量**诊断**（非评分）。修正 v2 的核心错误：在没有专家标注/权重校准/评分者一致性数据的情况下输出"82 分/等级 B"是编造——**取消一切无依据加权总分**。

## 2. 金融逻辑

**十个诊断维度**（各自独立呈现，不合成总分）：

Evidence Coverage（证据覆盖率）、Citation Precision、Citation Recall、Calculation Validity（复算一致率）、Numeric Accuracy、Assumption Disclosure（假设披露完整度）、Unsupported Claims（无支撑主张计数）、Factual Errors（事实错误计数）、False Positive Risk（纠错误报风险）、Replay Consistency（重放一致性）。

每维度附：分子/分母明细 + 涉及 claim 清单（支持人工复核）。**calibrated overall score 仅在获得专家标注数据后才允许增加**（需 inter-rater consistency 验证）。

## 3. 其余字段

- **输入/输出**：报告 + findings + claim 图 + 回放记录 → 诊断卡（JSON + UI 视图）
- **Edge Cases**：维度输入缺失 → N/A + 原因（不删行）；多报告对比 → 维度并排，不做排名合成
- **Failure Mode**：诊断代码自身零 LLM；维度计算错误宁可 N/A 不猜
- **Unit Tests**：各维度封闭算例；N/A 路径；无总分输出（结构断言）
- **Integration Tests**：对 CARD-11 planted 报告集批量诊断，与人工预期维度一致
- **Demo Method**（决赛）：两份报告诊断并排 → 指出弱项与证据
- **验收标准**：十维度各有测试；零加权总分；明细可下钻到 claim

## 4. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
