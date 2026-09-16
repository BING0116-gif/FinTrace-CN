# CARD-07: 报告质量评分（scorer.py）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段1 / P1 |
| 对应选题 | 选题7 研究报告质量评估 |
| 依赖 | CARD-06（消费其 findings 作为扣分输入） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/scorer.py`：对研究报告输出多维质量评分卡。评分维度分为**确定性可算**（评分主体）与**模型依赖**（显式降级标注）两类，为选题 7 的"评分结果稳定性、评估效率、人工复核支持"提供基础。

## 2. 竞赛考察点映射

| 选题7考察点 | 本卡落点 |
|---|---|
| 评价指标专业性 | 五维 rubric + 权重显式可调 |
| 评分稳定性 | 确定性维度同输入必同分（可断言）；模型维度走重跑方差 |
| 评估效率 | 全自动，单报告秒级 |
| 人工复核支持 | 评分卡每项附明细与证据链接 |

## 3. 设计

### 3.1 评分维度

| 维度 | 权重 | 计算方式 | 属性 |
|---|---|---|---|
| 证据覆盖率 | 30% | 有 evidence 支撑的数字陈述占比（复用报告结构遍历） | 确定性 |
| 计算可验证性 | 25% | 同比/估值等可复算数字的复算一致率（复用 CARD-06 规则） | 确定性 |
| 假设披露完整度 | 15% | 估值关键假设是否显式列出并带 provenance（结构检查） | 确定性 |
| 事实错误扣分 | 20% | CARD-06 findings 按严重级加权扣分 | 确定性 |
| 结论稳定性 | 10% | 同输入多温度重跑的结论方差（需 LLM 运行） | 模型依赖 |

前四维合计 90 分为"确定性总分"；第五维仅在真实模型评测时附加，dry-run/mock 下必须标注 `model_dependent_skipped`。

### 3.2 数据结构与入口

```python
@dataclass
class DimensionScore:
    dimension: str
    score: float | None       # None 表示跳过（如模型维度离线时）
    weight: float
    detail: dict              # 计算明细（分子/分母/涉及证据清单）
    determinism: str          # exact | model_dependent

@dataclass
class Scorecard:
    total: float              # 0-100
    dimensions: list[DimensionScore]
    grade: str                # A/B/C/D（分档阈值模块常量）
    determinism_note: str     # 确定性总分 vs 全量总分的说明

def score_report(report_structure, checker_findings, stability_runs: list | None = None) -> Scorecard:
    """report_structure：报告的结构化表示（数字陈述+evidence+假设段）。"""
```

`report_structure` 的构造：优先复用现有 `report.py` 生成报告时的中间结构；若其无结构化中间产物，则定义轻量 schema（数字陈述列表 + 假设列表），并在执行备注中记录对接方式。

### 3.3 工具注册

`ScoreCnReportTool`（`cn_tools.py`）：入参 `symbol` + `report_structure`（可选 `stability_runs`）；出参 `status / scorecard`。

### 3.4 稳定性维度实现边界

- 真实模型评测：调用现有 benchmark/ablation 的运行通道，多次采样后计算结论一致性（复用 `ablation_agent.py` 思路，先读后接）。
- 离线/无凭证：维度跳过 + `Scorecard.determinism_note` 显式声明"模型维度未评估，总分不含该维度"。
- **禁止**用 mock 结果填充稳定性分数。

## 4. 实施步骤

1. 通读 `report.py` 报告结构与 CARD-06 findings 结构，定义 `report_structure` 对接（最小改动优先）。
2. 实现四维确定性评分 + 权重合成 + 分档；阈值常量集中顶部。
3. 稳定性维度接 ablation 通道（真实凭证路径）+ 离线跳过路径。
4. 测试：`tests/test_cn_scorer.py`
   - 同输入两次评分确定性总分完全一致（浮点相等断言）
   - 构造好/中/差三份样例报告，总分单调递减
   - findings 数量增加 → 事实错误维度单调下降
   - 离线模式 scorecard 含 skip 标注
5. 注册工具 + 契约测试；端到端样例贴执行备注。

## 5. 验收标准

- [ ] 确定性维度同输入同分（测试断言）；三档样例单调性通过
- [ ] 离线跑分不含模型维度且显式声明；mock 数据零流入
- [ ] 每维度 detail 可展开到证据/claim 级（人工复核支持）
- [ ] 全部测试通过

## 6. 红线（本卡特有）

- 权重与分档阈值显式常量并注释依据；不许魔法数字散落
- 确定性维度禁止调用 LLM；模型维度结果必须带运行环境标注（模型名/温度/次数）
- 评分不得反向修改报告或证据

## 7. 执行备注（agent 填写）

| 日期 | 记录（report_structure 对接方式 / 阈值调整 / 偏差） |
|---|---|
|  |  |
