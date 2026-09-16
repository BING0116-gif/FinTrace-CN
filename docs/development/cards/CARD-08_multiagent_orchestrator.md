# CARD-08: 多智能体编排框架（multiagent/）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段3 / P0 |
| 对应选题 | 选题6 买方投资备忘录编制（基础设施） |
| 依赖 | CARD-04、CARD-05（分析师角色的确定性工具） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/multiagent/` 包：原生状态机编排"分析师团队 → 辩论（CARD-09）→ 风险评审 → 备忘录（CARD-10）"全流程。**不引入 LangGraph**，复用现有 `CnResearchAgent` 的 LLM 客户端与工具注册表，全程轨迹可追溯。架构模式参考 TradingAgents（MIT，借鉴思想，原生实现）。

## 2. 设计原则

1. 编排器只是状态机：决定谁在何时发言，不参与任何金融判断。
2. 每个 agent 角色的"发言"必须结构化（可校验、可存档），不接受自由文本直接进结论。
3. 轨迹完整：每轮记录角色、输入摘要、输出、token 成本、时长——竞赛"运行过程可追溯"的直接证据。

## 3. 详细设计

### 3.1 角色与数据结构

```python
class AgentRole(str, Enum):
    fundamental = "fundamental"    # 基本面分析师
    valuation = "valuation"        # 估值分析师
    checker = "checker"            # 核查员（可只跑确定性规则，零 LLM）
    bull = "bull"                  # 多头（CARD-09）
    bear = "bear"                   # 空头（CARD-09）
    risk = "risk"                   # 风险评审（CARD-09）
    memo_writer = "memo_writer"    # 备忘录撰写（CARD-10）

@dataclass
class AgentClaim:
    claim_id: str
    statement: str
    evidence_ids: list[str]        # 空列表 = 无证据论点，将被 gate 标记 unsupported
    role: AgentRole

@dataclass
class AgentOpinion:
    role: AgentRole
    claims: list[AgentClaim]
    token_cost: int
    model: str | None              # 离线 agent 为 None

@dataclass
class MultiAgentTrace:
    symbol: str
    run_id: str
    stages: list[dict]            # 每阶段：{stage, roles, opinions, wall_time}
    total_token_cost: int
    outcome: str                  # completed | gated | failed
```

### 3.2 编排器（`src/cn/multiagent/orchestrator.py`）

```python
class MultiAgentOrchestrator:
    def __init__(self, llm_client, tool_registry, research_state): ...

    def run(self, symbol: str, snapshot) -> MultiAgentTrace:
        """阶段流（本卡实现 1、2 的骨架，3/4/5 由 CARD-09/10 填充）：
        1) 分析师团队：fundamental/valuation 并行产出 AgentOpinion（调用 CARD-04/05 工具取数，LLM 只做叙述）
        2) 汇总去重：合并 claims，冲突值（同一事实不同数值）标记 conflict
        3) 辩论：见 CARD-09（本卡留 stage 钩子，默认跳过）
        4) 风险评审：见 CARD-09（同上）
        5) 备忘录：见 CARD-10（同上）
        """
```

实现要点：
- 分析师角色 = 确定性工具取数 + LLM 叙述两层：工具结果（事实）直接注入 prompt，LLM 产出 claims（推论），claims 中数值必须引用工具返回的 evidence_id——由校验器强制（见 3.3）。
- LLM 不可用/离线模式：降级为 `offline_agent.py` 风格的脚本化 opinions（演示模式必须显式标注 model=None）。
- 并发用 `ThreadPoolExecutor(max_workers=3)` 有界池，超时边界复用现有服务层做法。

### 3.3 轨迹校验（`src/cn/multiagent/trace_validator.py`）

- 每个 claim 的 evidence_ids 必须存在于证据账本 → 否则该 claim 标记 `unsupported`
- 每个 LLM 生成的数值 claim 必须能在工具结果中找到同值数字 → 否则标记 `unverified_number`（LLM 编数字的最强拦截）
- 冲突/unsupported/unverified 汇总进 trace，供 gate 决策

### 3.4 与现有系统集成

- LLM 客户端：复用 `src/llms/`（先读 `model_registry` / openai 兼容客户端的现有调用方式）。
- 工具注册表：复用 `cn_tools.py` 现有注册结构。
- 运行记录：沿用 `research_agent.py` 的 ResearchState/轨迹存储约定（先读现状，保持一致）。
- `api.py` 增加 `/multiagent/research` 端点（遵循现有 envelope 与任务模型，任务走 CARD-02 的 TaskKind）。

## 4. 实施步骤

1. 通读 `research_agent.py`（LLM 调用、工具循环、轨迹）与 `offline_agent.py`（脚本化降级）。
2. 实现 `orchestrator.py` 骨架 + 角色 dataclass + 阶段状态机（3/4/5 留钩子）。
3. 实现 `trace_validator.py` 三条规则。
4. 离线端到端：offline 模式跑通"分析师→汇总"，trace 完整落盘。
5. `tests/test_cn_multiagent_orchestrator.py`：状态机流转、无证据论点被标记、冲突检测、离线降级标注。
6. api 端点 + 任务接入 + 契约测试。

## 5. 验收标准

- [ ] 离线模式全流程跑通且 trace 每阶段可见（model=None 显式标注）
- [ ] unsupported / unverified_number / conflict 三类标记各有测试用例
- [ ] 真实 LLM 路径：claims 中的数值 100% 可回溯工具返回（trace_validator 断言）
- [ ] api 端点契约测试通过；全部测试通过

## 6. 红线（本卡特有）

- 编排器零金融判断；所有判断来自工具结果或带证据的 claims
- 不引入 LangGraph / autogen / crewai 等编排框架依赖
- 演示（offline）运行结果不得冒充真实模型表现

## 7. 执行备注（agent 填写）

| 日期 | 记录（阶段钩子实现方式 / 偏差 / 遗留问题） |
|---|---|
|  |  |
