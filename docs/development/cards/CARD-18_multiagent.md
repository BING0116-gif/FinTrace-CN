# CARD-18: Multi-Agent 编排（含强制消融）

| 属性 | 值 |
|---|---|
| 优先级 | P2 |
| 竞赛阶段 | 决赛版（若入围） |
| 对应赛题 | 赛题6 可选 synthesis strategy |
| 依赖 | 初赛主链全部稳定（01–13） |
| 实现复杂度 | 高（约 6 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-agent-evaluation、financial-tool-contract |

## 1. 目标

`src/cn/multiagent/`：原生状态机多智能体编排（分析师团队 + 风险评审）。**入场合条件：必须先有消融证据**。

## 2. 核心约束（本卡存在的理由）

初赛主架构保持：Planner → Tool Executor → Evidence → Validator → Report Generator。
Multi-Agent 上线前必须回答（消融实验，与 single-agent baseline 对比）：

1. 任务完成率是否提升？
2. 错误率是否下降？
3. Evidence Coverage 是否提高？
4. 成本（token）增加多少？延迟增加多少？

**四问没有明确指标收益，不合并进主线**——禁止只为"技术深度"加入。

## 3. 其余字段

- **设计**：角色（fundamental/valuation/checker/risk/memo_writer），原生状态机（不引 LangGraph），LLM claims 走既有 unverified_number 拦截与证据绑定（复用初赛 validator，零新信任机制）
- **金融逻辑**：编排器零金融判断；角色输出全部结构化 Claim 入图（CARD-09），与单 Agent 产出同构可比
- **Failure Mode**：offline 降级脚本化演示必须显式标注 model=None
- **Unit/Integration Tests**：状态机流转、claim 校验复用、离线降级
- **Benchmark（本卡验收核心）**：CARD-11 增加 multi vs single 消融组，四问指标成表；表进答辩材料
- **Demo Method**（决赛）：消融对比表 + 多智能体运行轨迹回放
- **验收标准**：四问有数字答案；无收益则明确记录"不采用"决策（该记录本身是加分项）

## 4. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
