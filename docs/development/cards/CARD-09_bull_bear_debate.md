# CARD-09: 多空辩论与风险评审

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段3 / P1 |
| 对应选题 | 选题6（投资逻辑与反向验证条件的质量来源） |
| 依赖 | CARD-08 |
| 状态 | ☐ 未开始 |

## 1. 目标

在 `src/cn/multiagent/` 下实现多空辩论（bull/bear 各 2 轮）与风险评审（激进/保守双清单），填充 CARD-08 留下的 stage 3/4 钩子。辩论抑制单视角偏差，为备忘录提供"反向验证条件"素材。

## 2. 设计

### 2.1 辩论（`src/cn/multiagent/debate.py`）

```python
@dataclass
class DebateTurn:
    round_no: int             # 1-2
    role: AgentRole           # bull | bear
    opening: list[AgentClaim]  # 本轮新论点
    rebuttals: list[dict]     # [{target_claim_id, counter_claim: AgentClaim}]
    token_cost: int

@dataclass
class DebateResult:
    turns: list[DebateTurn]
    bull_score: float          # 证据加权论点强度（确定性计算：evidence 覆盖×数量）
    bear_score: float
    unresolved_conflicts: list[str]   # 双方都持证据的分歧点 → 进备忘录"反向验证条件"

def run_debate(llm_client, opinions: list[AgentOpinion], trace) -> DebateResult:
    """Prompt 约束（硬规则写进系统提示并在代码侧二次校验）：
    - 每条论点必须引用 evidence_ids 或显式标注为 assumption
    - 反驳必须引用对方 claim_id（缺失引用的 turn 被裁掉并记录）
    - 只允许引用分析师阶段已产出的证据，不得引入新外部事实
    """
```

辩论强度评分（bull_score/bear_score）是**确定性公式**：`Σ(每条论点 × (1 + 0.5×len(evidence_ids)))`，无证据论点计 0.3 权重并标记 unsupported。公式与权重常量集中声明。

### 2.2 风险评审（`src/cn/multiagent/risk_review.py`）

```python
@dataclass
class RiskItem:
    description: str
    severity: str           # high | medium | low
    stance: str             # aggressive | conservative
    evidence_ids: list[str]

def run_risk_review(debate: DebateResult, snapshot, gate) -> list[RiskItem]:
    """双清单评审：
    - conservative：复用现有 research_gate 全量规则 + debate 的 unsupported 论点全列为 high
    - aggressive：仅结构化风险因素提取（LLM 叙述，数值仍须过 trace_validator）
    输出双立场清单，交由 CARD-10 备忘录的"风险因素"与"反向验证条件"段消费。
    """
```

### 2.3 离线降级

offline 模式：bull/bear 用预设论点模板（基于快照事实确定性拼接，如"PE 高于行业中位→空头论点"），保证演示可跑且显式标注 model=None。

## 3. 实施步骤

1. 通读 CARD-08 产物的 stage 钩子签名，接 `run_debate` / `run_risk_review` 进编排。
2. 实现辩论 Prompt + 输出结构化解析（复用 `research_agent.py` 的工具调用解析方式）+ 代码侧引用校验（反驳无 target_claim_id → 裁掉该 turn）。
3. 实现确定性强度评分与 unresolved_conflicts 提取。
4. 实现风险评审双清单（conservative 侧全确定性）。
5. 离线模板路径。
6. `tests/test_cn_multiagent_debate.py`：
   - 无证据论点权重 0.3 且标记 unsupported
   - 缺引用反驳被裁掉
   - 双方持证分歧进入 unresolved_conflicts
   - offline 模式标注完整性
7. 端到端（离线）样例贴执行备注。

## 4. 验收标准

- [ ] 引用校验四条规则（论点证据、反驳引用、禁止外部新事实、离线标注）全部有测试
- [ ] 强度评分确定性：同输入同分（浮点相等断言）
- [ ] 风险评审 conservative 清单零 LLM 依赖
- [ ] 全部测试通过；trace 中辩论阶段完整可见

## 5. 红线（本卡特有）

- 辩论 LLM 只能重组分析师阶段已有事实，不得新增数字；新增数字一律 unverified_number
- 评分公式权重显式常量；不引入情感分析模型
- 演示辩论结果标注 model=None

## 6. 执行备注（agent 填写）

| 日期 | 记录（Prompt 迭代 / 权重调整 / 偏差） |
|---|---|
|  |  |
