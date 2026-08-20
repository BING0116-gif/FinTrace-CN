# FinTrace-CN：A 股可验证金融研究 Agent

FinTrace-CN 是一个离线优先的 A 股研究系统。Agent 负责理解任务与选择工具，Python 负责财务计算，Evidence Ledger 记录事实与计算依赖，Validator 在证据不足、时点错误或估值方法不适用时阻断结论。

> 本项目用于工程实践与研究辅助，不构成投资建议，不连接券商账户，也不承诺任何收益。

## 为什么做这个项目

普通金融问答容易把模型记忆、实时数据、计算结果和叙事混在一起。FinTrace-CN 将它们拆成四个明确边界：

1. Provider 提供带来源、时间与口径的事实；
2. 确定性引擎计算 TTM、PE/PB/PS 和同行估值；
3. Evidence Ledger 保存事实、公式和依赖关系；
4. Validator 决定最终结论是否允许输出。

LLM 不拥有数据源选择权、财务计算权、证据创建权或 Validator 放行权。

## 已实现能力

- 沪、深、北 A 股代码与中文名称标准化；
- 版本化快照与可选 Tushare/AkShare 在线 Provider；
- research_as_of / available_at Point-in-Time 控制；
- FY、Q1、H1、9M、TTM 确定性期间转换；
- RAW 价格、币种、单位、期间和公式校验；
- PE、PB、PS 同行估值、IQR 异常值处理及金融机构适用性边界；
- Evidence DAG、工具轨迹、成本和校验状态；
- FastAPI 契约与 Streamlit 研究工作台；
- A 股每日复盘，synthetic demo 永不冒充实时行情；
- 离线测试、负面案例、四组 Agent 消融及 CI 回归门禁。

## 架构

~~~mermaid
flowchart LR
    U[研究问题] --> S[A 股代码标准化]
    S --> P[版本化快照 / 在线 Provider]
    P --> T[结构化研究工具]
    T --> R[ResearchState 与 Evidence Ledger]
    R --> C[确定性计算]
    C --> V{Validator}
    V -->|通过或非阻断警告| O[工作台 / API / Markdown]
    V -->|关键错误| B[拒绝结论与修复提示]
~~~

核心代码：

- src/cn/providers/：Provider 合约、缓存、路由、重试与熔断；
- src/cn/periods.py：累计财报转单季度与 TTM；
- src/cn/evidence.py：事实、计算与依赖证据；
- src/cn/valuation.py、peer_workflow.py：同行估值；
- src/validation/：财务、报告与研究结论闸门；
- src/cn/offline_agent.py：有界工具调用 Agent；
- src/cn/workbench_service.py：工作台与 API 共用业务服务。

## 5 分钟本地运行

~~~powershell
git clone https://github.com/BING0116-gif/FinTrace-CN.git
cd FinTrace-CN
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\bootstrap_demo.py
python -m streamlit run workbench.py
~~~

macOS/Linux：

~~~bash
git clone https://github.com/BING0116-gif/FinTrace-CN.git
cd FinTrace-CN
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/bootstrap_demo.py
python -m streamlit run workbench.py
~~~

bootstrap_demo.py 只生成确定性的 illustrative 数据，不访问网络，不使用真实公司财务数字。工作台也会在首次启动时自动补齐这套演示数据。

打开 http://localhost:8501，建议依次演示：

1. 成功案例：快照 → Evidence DAG → 同行估值 → 允许输出；
2. 阻断案例：删除总股本证据 → Validator 阻断估值与报告；
3. 每日复盘：查看明确标注的 synthetic_demo 与数据覆盖状态。

## API

~~~powershell
python -m uvicorn api:app --reload
~~~

- Swagger UI：http://localhost:8000/docs
- 健康检查：GET /health
- 研究快照：GET /api/research
- 估值与证据：GET /api/research/{snapshot_id}/valuation、evidence、validation
- 每日复盘：GET /api/daily-review

API 返回统一的 status: ok|error 信封，并保留快照、研究截止时间、Provider、Evidence ID、数据覆盖和 Validator 状态。

## Docker

~~~powershell
docker compose up --build
~~~

- Streamlit：http://localhost:8501
- FastAPI：http://localhost:8000/docs

镜像以非 root 用户运行，启动时自动生成 illustrative Demo；真实数据与输出保存在具名卷中。

## 测试与评测

~~~powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q -m "not integration" -p no:cacheprovider
python scripts/run_agent_ablation.py --dry-run --output output/agent_ablation
python scripts/check_ablation_thresholds.py output/agent_ablation/ablation_results.json
python scripts/smoke_workbench.py
~~~

默认测试完全离线。真实 Tushare 或 LLM 测试必须显式使用 -m integration 并提供凭据。

--dry-run 使用 mock provider，只验证工具契约、评测器和 Validator 机制，不能被描述为真实模型效果。真实模型结果应记录模型、Prompt、温度、快照、延迟、成本和失败详情。

## 数据与演示边界

- data/、output/、.env 均被 Git 忽略；
- 仓库不提交 API Key、付费原始数据或版权公告全文；
- illustrative 数据由代码生成并标记 illustrative_demo_not_for_investment；
- 在线 Provider 失败时返回 error、partial 或明确 synthetic fallback，不生成猜测数字；
- 历史快照永远不会显示为实时行情。

## 项目来源与个人工作

本项目基于开源 Agentic-Analyst/stock-analyst 进行 A 股方向二次开发。当前主线已移除原项目的美股新闻、DCF、加密资产与通用多 Agent 流水线，保留必要许可证和 Git 历史。

主要二次开发内容包括：A 股 Provider 与标准 Schema、Point-in-Time 快照、期间引擎、Evidence Ledger、确定性同行估值、Validator 闸门、Agent 评测、FastAPI/Streamlit 工作台和每日复盘。

## 文档

- [架构说明](ARCHITECTURE.md)
- [数据来源与口径](DATA_SOURCES.md)
- [估值方法](VALUATION_METHODOLOGY.md)
- [评测方法](EVALUATION.md)
- [演示指南](DEMO_GUIDE.md)
- [限制与合规](LIMITATIONS.md)
- [简历与面试准备](docs/RESUME_AND_INTERVIEW.md)

## License

Apache License 2.0。上游版权与许可信息保留在 [LICENSE](LICENSE) 和 Git 历史中。
