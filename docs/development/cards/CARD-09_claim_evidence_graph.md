# CARD-09: Claim-Evidence Graph（主张-证据图谱）

| 属性 | 值 |
|---|---|
| 优先级 | P1（核心创新，初赛窗口内完成） |
| 竞赛阶段 | 初赛版（10/7–10/11） |
| 对应赛题 | 全链路的骨架；"事实、推论与观点区分"的直接实现 |
| 依赖 | CARD-01（证据定位）、CARD-03（计算）、CARD-07（run 关联） |
| 实现复杂度 | 高（约 5–6 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/graph/`：把 Document → Source Fragment → Evidence → Calculation → Claim → Conclusion 组织为可序列化、可遍历、可在 UI 展开的图谱。实现孤儿 claim / 无支撑计算 / 缺失证据三类检测。这是**六大创新点之首**，也是"点击结论回溯到 PDF 页"的技术底座。

## 2. 对应竞赛评分点

分析逻辑严密性、证据支撑充分性、创新性、事实/推论/观点区分。

## 3. 为什么需要这个模块

"任何结论都有证据链"如果只是口号就是 PPT；做成图数据结构 + 遍历校验 + UI 展开，就是可验证的系统能力。示例（指令原文）：'盈利质量下降' → Claim C18 → CFO/NI=0.61 → Calculation CAL12 → CFO Evidence E51 + 净利润 Evidence E37 → 年报 P118 / P96。

## 4. 输入 / 输出

- **输入**：各模块产出的 Evidence / Calculation / Claim 记录（以 run_id 关联）
- **输出**：`ClaimGraph`（序列化 JSON、导出、遍历 API、检测报告）

## 5. 数据模型

```python
@dataclass
class Claim:
    claim_id: str
    claim_type: str          # fact | inference | opinion
    text: str
    evidence_ids: list[str]  # fact 必须非空
    calculation_ids: list[str]
    derived_from: list[str]  # inference 必须非空（指向 fact claim_id）
    confidence: str | float  # 确定性规则给出
    validation_status: str   # pending | supported | unsupported | blocked

@dataclass
class Calculation:
    calculation_id: str
    formula: str
    inputs: list[dict]       # 每项 {ref: evidence_id|calculation_id, value}
    output: dict             # {value, unit}
    tool_version: str

@dataclass
class ClaimGraph:
    run_id: str
    claims: dict[str, Claim]
    calculations: dict[str, Calculation]
    evidence_index: dict     # evidence_id → {document_id, page, bbox | snapshot}

    def trace(self, claim_id) -> TraceTree: ...        # 结论→证据→PDF页
    def detect_orphan_claims(self) -> list[str]: ...    # 无 evidence 的 fact
    def detect_unsupported_calculations(self) -> list[str]: ...  # 输入缺证据的计算
    def detect_missing_evidence(self) -> list[str]: ... # evidence_id 悬空
    def export_json(self) -> dict: ...
```

## 6. API / Tool Contract

```python
def build_graph(run_id) -> ClaimGraph: ...
def validate_graph(graph) -> ValidationReport: ...
    # fact 无 evidence → orphan；inference 无 derived_from → 结构错误；
    # opinion 无假设标注 → 结构错误；证据悬空 → missing

# 证据删除（Demo 高潮三的技术底座）——审计模式：标 invalid 而非物理删除
def deactivate_evidence(run_id, evidence_id, reason) -> str:
    """审计模式：EvidenceLedger 不物理删除，而是添加一条 'inactive' 状态记录
    （只追加原则的延伸：删除也是审计事件）。
    返回 revalidate 后的 impacted claim_id 列表。
    触发：revalidate(run_id) 增量重跑。"""

def revalidate(run_id, changed_evidence_ids=None) -> RevalidationReport:
    """全图增量重验证：
    - 受影响的 Claim validation_status 重计算（blocked/invalidated）
    - 下游 Claim 若所有 derived_from 的 fact 都 blocked → 级联 blocked
    - 返回受影响 Claim 清单 + 旧→新状态 diff
    UI 重渲染 memo 与图谱：blocked 徽章、memo 对应结论划灰加删除线。"""

Agent 工具 `TraceCnClaimTool`：入参 `claim_id`；出参 `status / trace_tree`（逐层到 PDF 页）。
Agent 工具 `DeactivateCnEvidenceTool`：入参 `evidence_id + reason`；出参 `status / impacted_claims / revalidation_report`。

## 7. 金融逻辑

三类绑定规则（强制）：
- **fact**：必须直接绑定 Evidence；数值型 fact 必须绑定 Calculation 或 Evidence 数值
- **inference**：必须能追踪 derived_from 的 fact（如诊断信号 → inference claim）
- **opinion**：必须显式标注假设来源（assumption_id 或"分析师主观判断"声明）

诊断信号（CARD-03）进图时是 inference，其 derived_from 指向指标 fact——**信号不得被当作确定因果写入 fact**。

## 8. Edge Cases

1. 一条 inference 依赖多条 fact（多证据结论）→ derived_from 列表全量记录
2. 链上某证据被删除（失败注入 #6）→ 该 claim validation_status=blocked，下游全部标记
3. 环引用（A 依赖 B 依赖 A）→ 构建时报错拒绝
4. 证据版本更新（更正公告）→ 图保留新旧链，冲突处理记录引用 CARD-13 的 conflict_id

## 9. Failure Mode

图构建失败 → 该 run 标记 graph_incomplete，报告输出缺口，不产出半张图装完整。

## 10. Validator Rules

- 三类绑定规则全覆盖检测（第 7 节）
- trace() 必须能到达文档页或快照 available_at（可达性断言）
- 检测报告三项（orphan/unsupported/missing）每次 run 必产出

## 11. Unit Tests

- 指令原文示例图（C18→CAL12→E51/E37→P118/P96）构建与 trace
- 三类绑定规则正反例
- 证据删除 → blocked 传播
- 环引用拒绝；序列化/反序列化保真

## 12. Integration Tests

全主链跑完后自动建图 → 检测报告零 orphan/unsupported/missing（好数据场景）；失败注入场景对应标记正确。

## 13. Benchmark

Evidence Coverage / Unsupported Claims 指标接入 CARD-11（由图检测自动计算）。

## 14. Demo Method

Demo 压轴：点击备忘录任一结论 → 图谱逐层展开 → 落到 PDF 页。再删除一个 Evidence → 重跑 → 结论变 blocked。**这一幕是整个 Demo 的灵魂**。

## 15. 验收标准

- [ ] 图构建/trace/三类检测全部有测试
- [ ] fact/inference/opinion 绑定规则 validator 强制
- [ ] 序列化导出与 UI 展开链路打通
- [ ] 失败注入 #6（删证据→claim blocked）可现场复现
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
