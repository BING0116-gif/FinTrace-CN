# CARD-07: Run Manifest & Audit Trail（运行清单与审计轨迹）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（9/16–9/22，最早开工之一） |
| 对应赛题 | 竞赛硬性要求："完整记录文件访问、工具调用、计算过程和结果生成情况" |
| 依赖 | 无 |
| 实现复杂度 | 中（约 3 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/runs/`：每次任务执行生成 17 字段 RunManifest + 只追加 events.jsonl 审计轨迹，支撑"同一输入+同一配置→重新执行"。这是竞赛"执行过程可追溯、运行结果可复现"的**直接合规层**，也是 Audit Replay（CARD-12）的数据源。

## 2. 对应竞赛评分点

结果可复现、执行过程可追溯（两项硬性要求）、结果稳定性（重放一致性）。

## 3. 为什么需要这个模块

现有 fingerprint（prompt hash/git commit/snapshot）只覆盖部分复现信息，且没有文件访问与计算过程的完整事件流。v2 的"统一任务系统"关注队列管理，偏离了竞赛真正要的"可复现清单"——本卡纠偏。

## 4. 输入 / 输出

- **输入**：任务执行过程中的各环节事件（文件加载、解析、工具调用、计算、校验、生成）
- **输出**：`runs/<run_id>/manifest.json` + `runs/<run_id>/events.jsonl`

## 5. 数据模型

```python
@dataclass
class RunManifest:
    run_id: str
    started_at: str
    finished_at: str
    input_document_sha256: list[str]   # 全部输入文档指纹
    snapshot_id: str | None
    model: str | None                  # offline 模式为 None
    model_provider: str | None
    model_version: str | None
    temperature: float | None
    prompt_hash: str | None            # CARD-14 注册表联动
    skill_hash: str | None
    parser_name: str
    parser_version: str
    git_commit: str
    tool_versions: dict[str, str]
    random_seed: int | None
    execution_mode: str                # offline | real_model | replay

# events.jsonl 每行：
# {"ts", "run_id", "stage", "event_type",
#  "input_digest", "output_digest", "status", "detail"}
# stage ∈ {file_load, parse, normalize, retrieval, tool_call,
#          calculation, claim, validation, report}
```

## 6. API / Tool Contract

```python
class RunRecorder:
    def start(self, config) -> str: ...              # 返回 run_id，写 manifest 骨架
    def emit(self, stage, event_type, input_, output, status) -> None: ...
        # 自动计算 input/output digest；追加 events.jsonl
    def finish(self, outcome) -> None: ...             # 补 finished_at
    def verify_replayable(self, run_id) -> ReplayPlan: ...

def replay(run_id) -> RunResult:
    """按 manifest 重新执行；输出与原 run 的 diff 报告
    （确定性部分应全等；LLM 部分标注采样差异）。"""
```

与现有 ResearchState/轨迹的关系：**扩展不重写**——ResearchState 记录 agent 循环层，RunRecorder 记录全链路层，事件共享 run_id 关联。

## 7. 金融逻辑

本卡无直接金融计算，但 digest 的设计决定可复现性：文件访问事件必须含 sha256；计算事件必须含 calculation_id（与 CARD-09 的 Calculation 记录对齐）；工具调用事件记录入参出参摘要。

## 8. Edge Cases

1. 进程中断 → manifest 缺 finished_at → 标记 interrupted（不删，审计价值保留）
2. replay 时 git_commit 已前进 → diff 报告头部显著标注版本差异
3. LLM 部分重放（temperature>0）→ 结果不保证全等，replay 报告分"确定性层全等 + LLM 层采样差异"两段
4. 输入文件已被修改 → sha256 比对失败 → replay 拒绝执行并报告

## 9. Failure Mode

事件写入失败（磁盘）→ 任务标记 failed，fail-closed。**事件只追加不修改**——任何改写历史事件的代码路径都是红线。

## 10. Validator Rules

- manifest 17 字段齐全（offline 模式允许 model 系列为 None，但必须显式存在）
- events.jsonl 单调递增时间戳
- 每个 calculation 事件可回查 calculation_id 完整定义

## 11. Unit Tests

manifest 字段完整性；事件追加顺序；digest 稳定性（同输入同 digest）；interrupted 标记；replay 拒绝（文件已改）。

## 12. Integration Tests

一次完整研究任务 → run 目录产物齐全 → replay 确定性层全等报告；接入现有 benchmark fingerprint 机制（复用不重复造）。

## 13. Benchmark

Replay Success Rate / Multi-run Consistency 两指标接入 CARD-11。

## 14. Demo Method

Demo 结尾展示：任选一次 run → 导出 manifest → 现场重放 → 一致性报告。"结果不是只由 LLM 生成的"的证明材料。

## 15. 验收标准

- [ ] 17 字段 manifest 生成与测试
- [ ] 九类 stage 事件全覆盖（file_load 到 report）
- [ ] replay 确定性层全等验证通过
- [ ] 事件只追加（防篡改测试）
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
