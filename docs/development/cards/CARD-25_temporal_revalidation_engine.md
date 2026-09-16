# CARD-25: Temporal Revalidation Engine（时间重验证引擎）

| 属性 | 值 |
|---|---|
| 优先级 | P1（基础版 P0 可选早段：version lineage + 三态区分） |
| 竞赛阶段 | 初赛版（10/12–10/15 窗口 5；与 CARD-24 共用 Dependency Graph） |
| 对应赛题 | 北京赛：赛题2/5 时效性与版本处理（创新三）；华北五省：Incremental Computation |
| 依赖 | CARD-09（Dependency Graph）、CARD-13（三态区分：CONFLICT/SUPERSESSION/NEW_INFO）、CARD-24（Monitoring Plan 联动） |
| 实现复杂度 | 中高（约 5 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

> 本卡前身：v3.1 的 "Temporal Revalidation"。v3.2 升级为 **Temporal Revalidation Engine**：明确 Version Lineage（AS_REPORTED/RESTATED/CORRECTED/SUPERSEDED），区分 DATA CONFLICT / VERSION SUPERSESSION / NEW INFORMATION 三种变化，实现 **Incremental Revalidation（affected-subgraph recomputation）**——新信息进入后，**不得默认全量重新执行所有 LLM workflow**。

## 1. Objective（目标）

新建 `src/cn/temporal/`：当新财报/新公告/更正公告/重新披露/新 Snapshot 进入系统后，做影响传播与**增量重验证**：

```
Source Changed ↓ Evidence superseded/conflict ↓ Calculation stale ↓ Claim stale/blocked ↓ Thesis affected ↓ Valuation affected ↓ Memo section affected
```

目标：自动计算 `affected_subgraph`，只重新执行受影响的 calculations / claims / theses / valuations / memo sections，并提供 impact analysis。

## 2. Competition relevance（双赛分别解决什么评审问题）

| 比赛 | 解决的评审问题 |
|---|---|
| 华北五省计算机设计大赛 | 展示 **Incremental Computation**：不重新跑整条 pipeline，而是仅重算受影响子图——性能与正确性可对比（full vs incremental → 相同结果 + 更低延迟） |
| 北京市大学生金融人工智能竞赛 | 回答"时效性/版本正确性"：更正公告或重述进入后，系统自动识别哪些结论过期/被阻断，而不是带着旧结论继续交付 |

## 3. Why this is not a gimmick（为什么不是点缀）

普通系统面对新公告的做法：要么"整份报告重新生成"（高成本、不稳定），要么忽略（错误保留旧结论）。本引擎的差异：

- **版本谱系**：旧值永不覆盖、可回放历史视图（supersedes / superseded_by）
- **三类变化分开传播**：DATA CONFLICT / VERSION SUPERSESSION / NEW INFORMATION **对应的传播规则不同**，不能全部叫 conflict
- **增量重验证**：changed_node_ids → affected_subgraph → 只重算受影响节点（可验证：与全量重计算同结果）
- 与 CARD-24 Monitoring Plan 联动：监测 KPI 触发 → 自动发起受影响的 claims 重验证

## 4. Inputs / 5. Outputs

- **输入**：changed_node_ids / TemporalEvent（新文件、更正、重述、新 snapshot）、Dependency Graph、Version Lineage
- **输出**：`RevalidationReport` + impact analysis（如：7 facts superseded / 4 calculations stale / 3 claims invalidated / 1 thesis weakened / 1 valuation stale / 2 memo sections affected）+ revalidated state diff

## 6. Data Models（数据模型）

```python
@dataclass
class VersionLineageEntry:
    fact_id: str
    version_status: str            # AS_REPORTED | RESTATED | CORRECTED | SUPERSEDED
    supersedes: str | None         # 被替代的旧 version_id
    superseded_by: str | None
    reason: str                    # restatement | correction | update | deprecation
    source_published_at: str
    ingested_at: str               # 显式区分：published vs ingested

@dataclass
class TemporalEvent:
    event_id: str
    event_kind: str                # DATA_CONFLICT | VERSION_SUPERSESSION | NEW_INFORMATION
    event_type: str                # new_filing | correction | restatement | new_snapshot
    event_date: str
    changed_source_ids: list[str]
    description: str

@dataclass
class RevalidationReport:
    event_id: str
    impact: dict                   # {facts_superseded, calculations_stale, claims_invalidated, theses_weakened, valuations_stale, memo_sections_affected}
    changed_nodes: list[str]
    affected_subgraph: list[str]
    state_diff: list[dict]         # [{node_id, before, after}]
    revalidation_actions: list[dict]  # [{action_type, target_id, priority}]
    full_vs_incremental: dict      # {nodes_recomputed, full_nodes, latency_ms, results_identical}
```

## 7. Algorithms（算法）

### 三态区分与传播规则（核心，与 CARD-13 联动）

| 事件 | 定义（不能全叫 conflict） | 传播行为 |
|---|---|---|
| DATA CONFLICT | 同期间同口径两个官方/来源值不一致，无版本关系 | 标记 CONFLICTED → CARD-13 裁决 > unresolved → 下游 BLOCKED |
| VERSION SUPERSESSION | 新版本明确替代旧版本（如更正公告 → E95 替代 E37） | 旧 evidence → SUPERSEDED；依赖计算 stale；依赖 claim stale/blocked |
| NEW INFORMATION | 新季度/新数据（无替代关系） | 计算 stale（period 更新）→ claim needs_refresh → memo section marked refresh |

### Incremental Revalidation（关键算法）
```
changed_node_ids
  → 在 Dependency Graph 上沿依赖方向计算 affected_subgraph（BFS/DFS 受限深度）
  → 只重算子图内 calculations / claims / theses / valuations / memo sections
  → 输出 state diff + 与"全量重算"结果一致性校验（测试断言，运行时可采样验证）
```
- **不得默认全量重新执行所有 LLM workflow**
- 非受影响节点保持原状态（快照视图）

## 8. API / Tool Contract

```python
# src/cn/temporal/engine.py
def ingest_temporal_event(event: TemporalEvent) -> RevalidationReport: ...
def compute_affected_subgraph(changed_node_ids, graph, max_depth=8) -> list[str]: ...
def propagate_status(affected_subgraph, graph) -> list[dict]: ...      # state_diff
def run_incremental_revalidation(report, env) -> RevalidationReport: ...
def impact_analysis(report) -> dict: ...
def compare_full_vs_incremental(run_id, changed_node_ids) -> dict: ...
```

Agent 工具 `RevalidateCnClaimsTool`：入参 `event 或 changed_node_ids`；出参 `status / revalidation_report / impact`。

## 9. Deterministic vs LLM boundary（确定性与 LLM 边界）

- 状态传播、affected_subgraph、重算**全确定性**
- LLM 不参与"是否受影响"判定；LLM 仅用于**受影响 memo 段落的改写**（发生在传播完成后，且只允许在 affected sections 内）

## 10. Dependencies（依赖）

CARD-09（Dependency Graph）、CARD-13（三态/裁决）、CARD-07（事件流审计）、CARD-04（重述信号）、CARD-24（monitoring 触发）。

## 11. Failure Modes

- 传播失败 → 该子图标记 `propagation_failed`，其余不受影响；报告如实列出
- 无法确定影响范围 → 标记 unknown 并人工复核（宁可漏报不误报——漏报让用户看见，误报破坏信任）
- 增量与全量结果不一致 → 断言失败，回落全量重算并记录

## 12. Edge Cases

1. 事实被删除无替代 → 依赖链全部 STALE/BLOCKED
2. 重述调整经济期间 → 重新映射 economic_period
3. 循环依赖 → 构建时拒绝（CARD-09 保证），本卡断言
4. 多事件并发 → 按时间顺序依次传播
5. 新 snapshot 更新同名指标 → NEW_INFORMATION → 计算 stale（不覆盖历史）

## 13. Validator Rules

- superseded 事实永不物理覆盖（append-only + lineage）
- 传播状态变化可回溯（event → state_diff 一一对应）
- affected_subgraph 是 state_diff 的超集（断言）

## 14. Unit Tests

- 三态区分（同一变化场景分别构造 CONFLICT / SUPERSESSION / NEW_INFO）传播正确
- version lineage：更正公告替代 → superseded_by 链正确
- affected_subgraph 计算（小图手工可验）
- **full vs incremental：人工构造图，两组结果完全一致断言**
- 无影响 → 空报告
- 循环 → 拒绝断言

## 15. Integration Tests

真实流程：旧年报 → 更正公告 → 输出 impact（facts/calcs/claims/theses/valuations/memo sections 数量与列表正确）；状态传播与 CARD-23 verify_claim STALE 联动。

## 16. Benchmark

**Ablation**：`full recomputation` vs `incremental affected-subgraph recomputation`，指标 = nodes recomputed / latency / **same deterministic result**（必须三个都有）。接入 CARD-11。

## 17. Demo Flow

Demo 步骤 11（DEMO_FLOW.md，时间允许时）：导入更正公告 → Temporal Revalidation 显示哪些 Fact / Calculation / Claim / Valuation / Memo 段落受影响 → VERIFIED→STALE/BLOCKED 传播可见。

## 18. Acceptance Criteria（验收标准）

- [ ] 三态区分有测试（不全部叫 conflict）
- [ ] version lineage 四态 + supersedes/superseded_by 关系测试通过
- [ ] affected_subgraph 计算正确（小图手工验证）
- [ ] full vs incremental 结果一致性断言通过
- [ ] 传播/重算路径零 LLM（代码断言）
- [ ] 全部测试离线通过

## 19. Priority

**P1**（基础版：version lineage + 三态 + 单向传播，10/12–10/15；incremental recomputation 为 P2/决赛增强，但 impact 统计初赛要出）。不裁剪 P0 主链。

## 20. Competition Stage

初赛：version lineage + 三态 + affected-subgraph 单向传播 + impact analysis；决赛：full incremental recomputation / automatic refresh / 高级可视化。

## 21. Estimated Complexity

约 5 人日（lineage+三态 2 + affected-subgraph 1.5 + impact/测试 1.5）。

## 22. Fallback / Degradation Strategy

- 时间不足：只做**单向** VERSION_SUPERSESSION 传播（更正公告是 demo 主场景），CONFLICT/NEW_INFO 降为"仅记录不阻断"
- incremental 不可用 → 声明回落全量重算（结果一致，代价是延迟）
- 断网不影响（全部本地确定性）

## 23. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |