# CARD-24: Thesis Fragility Engine（投资逻辑脆弱性分析）

| 属性 | 值 |
|---|---|
| 优先级 | P1（初赛增强；critical dependency detection 为 P0 可选早段） |
| 竞赛阶段 | 初赛版（10/12–10/15 穿插；或提前与 CARD-09 联动） |
| 对应赛题 | 北京赛：赛题6 反向验证增强（创新三）；华北五省：Graph Algorithms |
| 依赖 | CARD-09（Claim-Evidence Graph + dependency semantics，必须）、CARD-23（护照/验证状态）、CARD-08（假设） |
| 实现复杂度 | 中（约 4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

> 本卡前身：v3.1 的 "Thesis Fragility Map"。v3.2 升级为 **Thesis Fragility Engine**：建立在 Claim-Evidence Graph 之上，实现 Thesis 模型、REQUIRED/SUPPORTING/OPTIONAL 依赖语义、Critical Dependency Detection、Minimal Cut Set、Numeric Fragility（可选）、Monitoring Metrics。**不是 Bull/Bear 打分**。

## 1. Objective（目标）

新建 `src/cn/fragility/`：基于 Claim-Evidence Graph 分析投资逻辑（Thesis）的**脆弱性**——哪些 Claim/Evidence/Assumption 位于多条核心 Thesis 的 REQUIRED 路径上；最少破坏哪些节点会让 Thesis 失效；哪些假设是脆弱的；输出 Monitoring Plan 供后续 Temporal Revalidation（CARD-25）与备忘录刷新使用。

## 2. Competition relevance（双赛分别解决什么评审问题）

| 比赛 | 解决的评审问题 |
|---|---|
| 华北五省计算机设计大赛 | 展示 **Graph Algorithms**：REQUIRED 路径分析、minimal cut set（图论/可靠性分析），非 ML 依赖的确定性图算法 |
| 北京市大学生金融人工智能竞赛 | 回答"分析逻辑/反向验证"：投资逻辑**为什么成立、依赖哪些条件、哪个节点最脆弱、什么变化会使它失效**——把"逻辑严谨性"量化为可展示的图结构 |

## 3. Why this is not a gimmick（为什么不是点缀）

普通研报只有结论，无法回答"你的投资逻辑最依赖什么？"。多 Agent / Bull-Bear 打分只是观点的多空罗列，**不是结构分析**。本引擎的差异：

- 建立在 **Claim-Evidence Graph**（已有依赖语义）之上，输出的是图论意义上可验证的结构结论（关键依赖、最小割集）
- 输出可转为 **Monitoring Plan**（dependency → observable KPI → trigger condition → affected claims → revalidation action），直接驱动 CARD-25 / 备忘录断言更新
- 全部**确定性图算法**，可人工验证正确性

## 4. Inputs / 5. Outputs

- **输入**：`ClaimGraph`（含 Claim/Evidence/Calculation/Thesis 节点 + dependency_metadata）、Assumption Registry
- **输出**：`FragilityReport`（critical_dependencies / minimal_cut_sets / numeric_thresholds(可选) / distance_to_invalidation(可选) / unresolved_assumptions / monitoring_metrics）+ UI 的 **Thesis Fragility Map**

## 6. Data Models（数据模型）

```python
@dataclass
class Thesis:
    thesis_id: str
    statement: str                # 如 "盈利改善具有持续性"
    claim_ids: list[str]          # 构成该 thesis 的 Claims
    dependency_roles: dict[str, str]  # {claim_id: REQUIRED | SUPPORTING | OPTIONAL}
    # 例：T01 依赖 C01 毛利率改善(REQUIRED) + C02 收入增长(REQUIRED) + C03 原材料成本下降(SUPPORTING)

@dataclass
class FragilityReport:
    thesis_id: str
    critical_dependencies: list[dict]   # [{node_id, node_type: claim|evidence|assumption, thesis_ids[], is_single_point}]
    required_dependencies: list[dict]
    minimal_cut_sets: list[list[str]]   # 每个割集为节点 id 列表
    numeric_thresholds: list[dict]      # [{node_id, threshold, current_value, distance_to_invalidation}]  （可选，仅可靠阈值来源）
    unresolved_assumptions: list[dict]
    monitoring_metrics: list[dict]      # [{dependency, observable_kpi_event, trigger_condition, affected_claims[], revalidation_action}]

@dataclass
class MonitoringPlan:
    dependency: str
    observable_kpi_event: str
    trigger_condition: str
    affected_claims: list[str]
    revalidation_action: str
```

## 7. Algorithms（算法——确定性图算法，阶段一不要求复杂 ML）

### A. Critical Dependency Detection（关键依赖检测）
- 遍历所有 Thesis，统计每个 Claim/Evidence/Assumption 出现在多少条 **REQUIRED 路径**上
- 单点依赖（single point of failure）：某节点在所有可达的 Thesis 的 REQUIRED 路径上且无替代路径 → 标记 `is_single_point`

### B. Minimal Cut Set（最小割集）
- 给定 Thesis，求**使其失效所需破坏的最小 REQUIRED dependency 集合**
- 例：T01 依赖 C01 AND C02，其中 C01 依赖 E01 OR E02 → 割集有 {C01, C02}、{E01, E02, C02} 等
- 实现：DAG traversal + cut-set enumeration + graph reliability style analysis
- **初赛限制**：仅 DAG、有限深度（可配置，默认 < 8 层）、小规模 Thesis graph，保证可解释性。**不做 NP-hard 通用求解器**

### C. Numeric Fragility（数值脆弱性，可选）
- 当 Thesis 依赖明确数值条件（如 Gross Margin ≥ 29.4%，当前 31.2%）→ `distance_to_invalidation = 1.8 pct`
- **阈值必须来自**：公开假设 / 分析师明确输入 / 模型或估值约束。**严禁 LLM 凭空创造阈值**
- 无可靠阈值 → 只做 structural fragility，**不伪造 quantitative fragility**

### D. Monitoring Plan 生成
- 每个关键依赖 → 映射到可观察 KPI/事件与触发条件 → 生成 affected claims / revalidation action

## 8. API / Tool Contract

```python
# src/cn/fragility/engine.py
def identify_critical_nodes(graph, thesis_ids) -> list[dict]: ...
def detect_single_points_of_failure(critical_nodes) -> list[dict]: ...
def compute_minimal_cut_sets(graph, thesis_id, max_depth=8, max_sets=20) -> list[list[str]]: ...
def identify_fragile_assumptions(graph, assumptions) -> list[dict]: ...
def compute_numeric_fragility(graph, thresholds) -> list[dict]: ...   # thresholds 来自白名单来源
def generate_monitoring_plans(graph, report) -> list[MonitoringPlan]: ...
def build_fragility_report(graph, thesis_ids, thresholds=None) -> FragilityReport: ...
```

Agent 工具 `AnalyzeCnThesisFragilityTool`：入参 `thesis_id 或 run_id`；出参 `status / fragility_report`。

## 9. Deterministic vs LLM boundary（确定性与 LLM 边界）

- 本卡**全部确定性；零 LLM**
- LLM 可能的角色（不在本卡）：将研报叙事解析为 Thesis 陈述与依赖声明（但依赖角色 REQUIRED/SUPPORTING 必须在 CARD-09 构建时确定并有明确依据）
- 禁止 LLM 生成数值阈值（numeric_fragility 的 thresholds 只接受白名单来源）

## 10. Dependencies（依赖）

CARD-09（前提：Claim Graph + dependency_metadata 已具备）、CARD-23（护照验证状态流入 fragility，refresh 后重算）、CARD-24 → CARD-25（监测计划驱动时间重验证）。

## 11. Failure Modes

- 图规模过大/深度超限 → 返回部分结果并标注 `pruned`，不假装全局最优
- 阈值为空 → `numeric_thresholds = []`（如实为空，不编阈值）
- 割集枚举超预算 → 截断 + 标注 `cut_sets_truncated`

## 12. Edge Cases

1. Thesis 只有 SUPPORTING 依赖、无 REQUIRED → 无割集（无单点），报告如实说明
2. 图含环 → CARD-09 构建时已拒绝，本卡断言无环
3. 同一节点属于多 Thesis → critical 计数累加
4. 数值条件当前处于边界（等于阈值）→ distance_to_invalidation = 0 且标记 `at_threshold`

## 13. Validator Rules

- 每个 minimal cut set：移除集合内节点后 thesis 必须 BLOCKED（**反解断言测试**）
- numeric_thresholds 每项必须有来源类型标注（public_assumption | analyst_input | model_constraint）
- FragilityReport 必须包含 unresolved_assumptions（允许为空数组）

## 14. Unit Tests

- Critical dependency 计数正确性（人工构造小图）
- Minimal cut set：C01 AND C02 / E01 OR E02 反解断言；深度限制；环拒绝
- 单点依赖（唯一路径）检测
- Numeric fragility：阈值来源白名单；无阈值 → 空数组；at_threshold 边界
- Monitoring plan 生成（字段完整）

## 15. Integration Tests

CARD-09 build_graph → CARD-24 分析 → 输出与人工预期一致；异常后 refresh → fragility 报告更新。

## 16. Benchmark

**不是测"准确率"**。至少提供：人工构造 Thesis graph 验证 **critical dependency correctness / cut-set correctness / state propagation correctness**（正确性断言回归集）。接入 CARD-11。

## 17. Demo Flow

Demo 步骤 10b（DEMO_FLOW.md）：打开 Thesis Fragility Map → 展示关键 REQUIRED dependency（如"盈利改善持续性"依赖毛利率改善）→ 点击关键节点展示 Monitoring Plan → 人为删除/替换关键 Evidence → Thesis 状态从 VERIFIED 传播为 STALE/BLOCKED。

## 18. Acceptance Criteria（验收标准）

- [ ] critical_dependencies / minimal_cut_sets / monitoring_metrics 全部有测试
- [ ] cut-set 反解断言全通过
- [ ] 零 LLM（代码断言）
- [ ] 阈值来源白名单机制有测试
- [ ] 与 CARD-23 VERIFIED→STALE/BLOCKED 传播联调通过
- [ ] 全部测试离线通过

## 19. Priority

**P1**（critical dependency + 单点检测可在 10/7 前备好；minimal cut set 为 10/12–10/15 段）；不裁剪 P0 主链。

## 20. Competition Stage

初赛：structural fragility（critical dependency / cut-set / monitoring plan）；决赛：numerical fragility optimization、minimal cut set 复杂度增强、advanced visualization。

## 21. Estimated Complexity

约 4 人日（critical dependency 1.5 + cut-set 1.5 + numeric/monitoring 1）。

## 22. Fallback / Degradation Strategy

- 时间不足裁剪：minimal cut set 降为"单层割集"（只对 Thesis 的直接 REQUIRED 依赖枚举），标注范围
- 没跑出结果 → 报告标注 `fragility_unavailable`，保证不阻断主链
- 断网不影响（全部本地确定性）

## 23. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |