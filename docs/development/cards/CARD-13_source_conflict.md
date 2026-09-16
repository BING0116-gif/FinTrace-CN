# CARD-13: Source Conflict Resolver（来源冲突解决）

| 属性 | 值 |
|---|---|
| 优先级 | P1（基础区分 DATA CONFLICT / VERSION SUPERSESSION / NEW_INFO 为 P0 可选早段） |
| 竞赛阶段 | 初赛版（10/12–10/15） |
| 对应赛题 | 赛题2/5（重述与更正场景）；数据准确性；**并作为 ACME 跨源约束与 Temporal Revalidation 的裁决层** |
| 依赖 | CARD-01（多文档）、CARD-04（重述信号）、CARD-22（ACME 跨源结果四分类） |
| 实现复杂度 | 低中（约 2.5 人日，含三态区分与四分类接入） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/conflict.py`：当同一指标同一期间出现多个来源值（原披露 vs 更正公告 vs 重述 vs 第三方数据源）时，**先分类变化类型，再按明确优先级规则裁决**，全程记录，永不静默覆盖；无法确定时交 Validator 阻断或降级。

## 2. 对应竞赛评分点

数据准确性、金融专业性（真实世界数据治理意识）、分析逻辑。

## 3. 为什么需要这个模块

真实金融材料必然冲突。没有裁决规则的系统要么用错值，要么随机用后到的值——两种都是事故。失败注入演示 #5 依赖本卡。

## 4. 输入 / 输出

- **输入**：同一 (company, metric, period) 的多个候选 NormalizedFact
- **输出**：选定值 + `ConflictRecord`（若存在冲突）

## 5. 数据模型

```python
@dataclass
class ConflictRecord:
    conflict_id: str
    change_kind: str        # DATA_CONFLICT | VERSION_SUPERSESSION | NEW_INFORMATION（三态区分，见 §7b）
    source_a: str           # document_id / snapshot_id
    source_b: str
    selected_source: str
    reason: str             # 优先级规则名 + 说明
    resolver: str           # 规则版本
    timestamp: str
```

## 6. API / Tool Contract

```python
def resolve_conflicts(facts: list[NormalizedFact]) -> tuple[list, list[ConflictRecord]]:
    """按优先级裁决：后发布且明确更正前值的监管披露 > 原监管披露
    > 官方公司公告 > 第三方数据源。
    同级冲突（如两家第三方源不一致）→ 不裁决，标记 unresolved。"""

def unresolved_report(conflicts) -> list[dict]: ...
```

## 7. 金融逻辑

优先级规则（集中常量 + 注明适用范围）：监管披露指交易所/巨潮披露的公司报告与更正公告；"明确更正前值"依据 CARD-04 的 prior_period_error_correction 信号；第三方数据源（如数据商用快照）永远低于官方披露。**数值不同但口径不同（scope/version）不构成冲突**——先由 CARD-02 区分，只有同口径同版本不同值才算冲突。

## 7b. 三种变化状态区分（不能全部叫 conflict，v3.2 强化）

**必须区分三种状态，传播规则不同（对接 CARD-25 Temporal Revalidation）**：

| 状态 | 判据 | 例子 | 处理 |
|---|---|---|---|
| DATA_CONFLICT | 同期间同口径、无版本关系、两个官方/来源值不一致 | 两家第三方源不一致；双官方源矛盾 | 裁决 > unresolved → 阻断该指标 |
| VERSION_SUPERSESSION | 新版本明确替代旧版本 | 原财报 → 更正公告（E37 被 E95 替代） | 旧值保留（superseded），用新值；下游 stale/blocked 传播 |
| NEW_INFORMATION | 新增数据，无替代关系 | 新季度数据补充 | 计算 stale（period 更新）→ claim needs_refresh，不覆盖历史 |

**ACME 跨源四分类（MATCH/ROUNDING_MATCH/CONFLICT/NOT_COMPARABLE）裁决责任**：ACME（CARD-22）只负责检测与分类；本卡对 CONFLICT 类执行裁决；NOT_COMPARABLE（口径未统一）由 CARD-02 先归一后再判。**处理输入必须带 change_kind 上下文。**

**正确用例示例**：
- "原财报值 10 亿 → 更正公告值 12 亿"：VERSION_SUPERSESSION（不是 data_conflict）
- "年报 PDF 营收 35.2 亿 vs 快照 provider 营收 35.2 亿"：MATCH（无冲突）
- "年报 PDF 营收 35.2 亿 vs 快照 provider 营收 36 亿（同期间同口径）"：DATA_CONFLICT → 提交裁决

## 8. Edge Cases

1. 更正公告本身被再更正 → 链式裁决，取最新一环（supersession 链）
2. 优先级相同且值不同（双官方源矛盾，罕见）→ unresolved + Validator 阻断该指标
3. 冲突值差异在舍入容差内 → 不视为冲突（容差=显示位数）
4. 第三方源与官方源一致 → 无冲突，正常输出
5. 更正公告与重述同时存在 → 分别建立 supersession 与 restatement 链，不混用

## 9. Failure Mode

unresolved 冲突 → 该指标在下游全部标记 blocked（宁可阻断不误选）。**静默覆盖是红线**。

## 10. Validator Rules

- 每个 selected_source 的 reason 可追溯到规则名
- unresolved 冲突的指标不得出现在任何 fact claim 中（validator 遍历检查）
- ConflictRecord 不可变（append-only）

## 11. Unit Tests

四级优先级正反例；链式更正；同级矛盾阻断；舍入容差不误报；scope 不同不误判冲突；**三态区分用例**（DATA_CONFLICT vs VERSION_SUPERSESSION vs NEW_INFORMATION 各构造正例）；ACME 四分类接入（CONFLICT 提交裁决、NOT_COMPARABLE 返回归一要求）。

## 12. Integration Tests

失败注入 #5（旧财报+更正公告）全链：值取更正后，报告显示 ConflictRecord 与理由。

## 13. Benchmark

Scope/Version 准确性间接覆盖；本卡无独立指标，由失败注入 #5 复现率保障。

## 14. Demo Method

演示 #5：上传旧年报 + 更正公告 → 系统展示冲突对（两个值并排 + 裁决理由）→ 报告使用更正值。

## 15. 验收标准

- [ ] 四级优先级规则全部有测试
- [ ] 无静默覆盖（代码路径断言）
- [ ] unresolved 阻断链路打通
- [ ] 失败注入 #5 可现场复现

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
