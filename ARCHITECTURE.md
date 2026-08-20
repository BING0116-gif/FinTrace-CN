# FinTrace-CN 架构说明

FinTrace-CN 是离线优先的 A 股研究工作流。系统将模型驱动的工具编排，与确定性财务计算及校验严格分离。

```text
研究问题
  -> A股标准代码解析
  -> 版本化本地快照
  -> 快照驱动的研究工具
  -> ResearchState（工具轨迹、证据ID、成本）
  -> 确定性估值 / Validator
  -> 中文 Markdown 或 Excel 报告
```

## 核心组件

| 层级 | 位置 | 职责 |
|---|---|---|
| 领域标准 | `src/cn/domain.py`、`symbols.py`、`periods.py` | A 股代码、财报期间和时点规则 |
| 数据 Provider | `src/cn/providers/` | 中立 Provider 合约、本地快照、可选 Tushare |
| 研究工具 | `src/agents/tools/cn_tools.py` | 代码、行情、财务、估值、报告的 `status: ok\|error` 结构化返回 |
| 可靠性 | `src/cn/evidence.py`、`src/validation/research_gate.py` | Evidence ID、公式/时点校验和结论阻断 |
| Agent 状态 | `src/cn/research.py`、`src/cn/offline_agent.py` | 计划、工具轨迹、证据、成本及有界执行 |
| 评测 | `src/cn/benchmark.py`、`scripts/run_benchmark.py` | 可复现的路由、证据与回归评测 |

## 信任边界

LLM 可以从已提供工具中选择操作并撰写受约束文字；它不负责财务计算、证据创建、数据源选择或 Validator 决策。快照和在线 Provider 的返回均被视为数据，不能作为可执行指令。

## 离线执行

`SnapshotProvider` 读取固定 JSON 快照。离线报告、离线测试及 `--dry-run` 消融实验不依赖网络、Tushare 或 LLM API Key。fresh clone 会生成明确标记的 illustrative 快照；真实模型评测仅访问配置的模型 API，金融数据工具仍只使用本地快照。

## 审计工件

`ResearchState` 保存问题、研究截止时间、标准代码、工具轨迹、返回的 Evidence ID、校验结果、报告文本和成本轨迹。基准 `results.json` 还保存基准/快照 ID、模型、温度、最大步数、Prompt 哈希、Git 提交、延迟与成本。
