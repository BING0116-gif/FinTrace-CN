# FinTrace-CN 评测说明

## 评测原则

事实、公式和证据使用确定性断言；模型文案不作为金融正确性的裁判。默认测试只读取固定夹具或本地生成的 illustrative 快照，不访问网络。

## 测试层级

1. 单元测试：代码标准化、期间转换、估值与证据重算；
2. Provider 契约：标准 Schema、错误分类、缓存、重试、fallback 与熔断；
3. Golden 回归：固定快照、Evidence ID、Validator 结果与报告边界；
4. Agent 评测：工具选择、参数、证据覆盖、失败恢复与结论泄漏；
5. Integration：真实 Tushare 或 LLM，仅在显式提供凭据时运行。

## 四组 Agent 消融

| 变体 | 工具 | Evidence | Validator |
|---|---|---|---|
| direct_llm | 否 | 否 | 否 |
| agent_tools | 是 | 剥离 | 否 |
| agent_tools_evidence | 是 | 是 | 否 |
| agent_tools_evidence_validator | 是 | 是 | 是 |

固定指标包括 tool F1、参数正确率、证据覆盖率、端到端成功率、Validator 拦截率、错误结论泄漏、延迟与成本。每个指标都由固定案例和明确分母计算。

## 离线机制验证

~~~powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
python scripts/run_agent_ablation.py --dry-run --output output/agent_ablation
python scripts/check_ablation_thresholds.py output/agent_ablation/ablation_results.json
~~~

dry-run 使用 mock provider，证明评测器、工具契约和 Validator 的确定性行为。它不代表真实模型能力，简历和 README 不得把 dry-run 分数描述为真实 LLM 指标。

## 真实模型评测

~~~powershell
python scripts/run_agent_ablation.py --model deepseek-v4-flash --output output/real_agent_ablation
~~~

真实运行必须记录模型标识、Prompt/案例版本、温度、最大步数、快照 ID、Git commit、每案工具轨迹、错误、延迟与成本。连接失败的运行应保留为失败诊断，但不能作为模型效果结论。

## 当前边界

评测重点是工具路由、证据和 fail-closed 行为，不等价于完整投资研究质量，也不衡量收益预测能力。真实模型输出仍可能随服务端版本变化。
