# FinTrace-CN 实施状态基线

> 本文件记录代码和测试已经证明的状态，不记录设计目标。状态更新必须伴随代码、测试或可复现运行结果。`implemented` 表示当前代码有对应入口和测试；`partial` 表示有一部分链路但存在明确缺口；`planned` 表示只有规格/文档，尚无对应实现；`deprecated` 表示不再纳入主线。

## 基线信息

| 项目 | 当前值 |
|---|---|
| 基线日期 | 2026-10-01 |
| 代码范围 | `src/cn/`、`src/agents/tools/`、`src/validation/`、`src/llms/`、`api.py`、`workbench.py` |
| 默认验证 | `python -m pytest -q -m "not integration" -p no:cacheprovider` |
| 初始基线测试结果 | 320 passed, 1 deselected |
| CARD-22 本轮离线测试结果 | 400 passed, 1 deselected；`tests/test_cn_acme.py` 4 passed |
| CARD-24 本轮离线测试结果 | 406 passed, 1 deselected；`tests/test_cn_fragility.py` 3 passed |
| CARD-25 本轮离线测试结果 | 411 passed, 1 deselected；Temporal/Memo integration focused tests 8 passed |
| CARD-05 本轮离线测试结果 | 413 passed, 1 deselected；`tests/test_cn_checker.py` 6 passed，包含 13 类 planted cases |
| CARD-26 本轮离线测试结果 | 418 passed, 1 deselected；`tests/test_cn_finfuzz.py` 4 passed，10 类 mutation operator 已覆盖 |
| CARD-12 本轮离线测试结果 | 419 passed, 1 deselected；`tests/test_cn_evidence_pack.py` 3 passed，失败注入副本脚本已验证 |
| CARD-01 MVP 后测试结果 | 329 passed, 1 deselected |
| CARD-02 MVP 后测试结果 | 336 passed, 1 deselected |
| CARD-03 MVP 后测试结果 | 347 passed, 1 deselected |
| Smoke | `python scripts/smoke_workbench.py` 可执行；需要每次发布重新运行 |
| 版权/密钥边界 | `data/`、`output/`、`.env`、运行文件和付费/版权原文不得入 Git |
| 真实数据边界 | 默认 fixture 和 bootstrap demo 为 illustrative/synthetic，不代表实时行情或真实财务数字 |

## 已实现能力

| 能力 | 代码入口 | 测试入口 | 状态 | 当前限制 |
|---|---|---|---|---|
| A 股代码标准化 | `src/cn/symbols.py` | `tests/test_cn_symbols.py` | implemented | 仅覆盖当前 A 股代码规则，不扩展海外证券 |
| 财报期间模型 | `src/cn/periods.py` | `tests/test_cn_periods.py`, `tests/test_cn_period_filter.py` | implemented | 依赖输入已具备规范 period 字段；真实文档字段映射尚未完成 |
| 领域数据模型 | `src/cn/domain.py` | `tests/test_cn_snapshot_provider.py`, `tests/test_cn_periods.py` | implemented | 主要服务 Snapshot/Provider 链路 |
| Snapshot Provider | `src/cn/providers/snapshot.py` | `tests/test_cn_snapshot_provider.py` | implemented | 默认是 JSON 快照，不是文档解析器 |
| Provider 抽象 | `src/cn/providers/base.py` | `tests/test_cn_router.py`, `tests/test_cn_tushare_provider.py` | implemented | 真实 Provider 测试需 integration 和凭据 |
| Provider Router | `src/cn/providers/router.py` | `tests/test_cn_router.py` | implemented | 只覆盖现有 Provider 方法；没有文档级来源路由 |
| Provider Cache | `src/cn/providers/cache.py` | `tests/test_cn_cache.py` | implemented | 当前是进程/本地缓存能力，不是多实例共享缓存 |
| Tushare Provider | `src/cn/providers/tushare.py` | `tests/test_cn_tushare_provider.py`, `tests/test_cn_tushare_integration.py` | partial | 默认离线不调用；需要真实 token、配额和供应商数据校验 |
| AkShare Provider | `src/cn/providers/akshare.py` | 现有 Provider/每日复盘测试 | partial | 主要用于在线/每日复盘路径，字段覆盖和稳定性依赖外部源 |
| Evidence Ledger | `src/cn/evidence.py` | `tests/test_cn_evidence.py` | implemented | 当前以 Snapshot/计算证据为主，尚无 PDF 页码/bbox SourceFragment |
| 确定性期间转换 | `src/cn/periods.py` | `tests/test_cn_periods.py` | implemented | 新文档规范化层还未桥接 |
| 相对估值 PE/PB/PS | `src/cn/valuation.py` | `tests/test_cn_valuation.py` | implemented | 尚未有完整 Bear/Base/Bull 假设登记和敏感性矩阵 |
| 同行估值工作流 | `src/cn/peer_workflow.py` | `tests/test_cn_peer_workflow.py` | implemented | 仍以快照候选为输入；真实行业可比质量依赖 Provider 覆盖 |
| 财务 Validator | `src/validation/financial_validator.py` | `tests/test_cn_validation.py` | implemented | 主要验证现有结构化快照，不验证文档解析候选 |
| Research Gate | `src/validation/research_gate.py` | `tests/test_cn_validation.py`, `tests/test_cn_agent_ablation.py` | implemented | 没有 Claim Graph 级的 REQUIRED/SUPPORTING/OPTIONAL 传播 |
| Report Validator | `src/validation/report_validator.py` | `tests/test_cn_report.py`, `tests/test_cn_validation.py` | partial | 有报告边界校验，尚非完整的逐句 Report Checker |
| Markdown 研究报告 | `src/cn/report.py` | `tests/test_cn_report.py`, `tests/test_cn_report_cli.py` | implemented | 输出主要来自结构化快照；没有 PDF 页码回溯 |
| 快照研究服务 | `src/cn/research.py`, `src/cn/workbench_service.py` | `tests/test_cn_research.py`, `tests/test_cn_workbench_service.py` | implemented | 业务入口主要围绕本地快照 |
| Offline Agent | `src/cn/offline_agent.py` | `tests/test_cn_offline_agent.py` | implemented | 有界工具链，不等于真实文档研究 Agent |
| Real-model Agent | `src/cn/research_agent.py`, `src/cn/agent_service.py` | `tests/test_cn_research_agent.py`, `tests/test_agent_research_service.py` | partial | 真实 LLM 运行需凭据；没有文档、Claim Graph、Memo 全链路 |
| Tool Contract | `src/agents/tools/base.py`, `src/agents/tools/cn_tools.py` | `tests/test_cn_tools.py` | implemented | 现有工具面以快照研究为主 |
| Agent 消融 | `src/cn/ablation_agent.py`, `scripts/run_agent_ablation.py` | `tests/test_cn_agent_ablation.py` | implemented | dry-run 只证明机制；真实模型效果未默认存在 |
| Benchmark Runner | `src/cn/benchmark.py`, `scripts/run_benchmark.py` | `tests/test_cn_benchmark.py`, `tests/test_cn_benchmark_runner.py` | implemented | 当前案例规模和文档语义错误覆盖仍有限 |
| Real Benchmark 基础 | `src/cn/real_benchmark.py` | `tests/test_real_benchmark.py` | partial | 需要显式真实模型运行后才有可报告结果 |
| FastAPI | `api.py` | `tests/test_workbench_api.py`, `tests/test_agent_research_api.py` | implemented | 任务状态主要依赖本地进程/文件，尚无持久化数据库和 Replay API |
| Streamlit Workbench | `workbench.py` | `tests/test_cn_workbench_service.py`, `tests/test_workbench_api.py`, smoke | partial | 页面可用但单文件约 1700 行，尚无文档/Claim/Memo/Replay 页面 |
| 每日复盘 Schema | `src/cn/daily_review/schema.py` | `tests/test_cn_daily_review.py` | implemented | 数据模型和 gate 已有 |
| 每日复盘分析 | `src/cn/daily_review/analysis.py` | `tests/test_cn_daily_review.py` | implemented | 主要是确定性分析，不等于投资预测 |
| 每日复盘采集 | `src/cn/daily_review/collector.py` | `tests/test_cn_daily_review.py` | partial | 离线 synthetic fallback 明确；在线覆盖、配额、源稳定性仍受外部条件影响 |
| Docker 运行 | `Dockerfile`, `docker-compose.yml` | smoke/人工验证 | partial | 可启动双服务，但没有生产级认证、持久化任务队列和多实例协调 |

## 已有但不应误称为完整实现

| 名称 | 已有内容 | 尚缺内容 |
|---|---|---|
| Evidence DAG | Evidence ID、计算输入和 Validator 关联 | Document → Fragment → Evidence → Claim → Thesis 的可遍历图 |
| Point-in-Time | research_as_of、available_at 相关校验 | 文档 published_at、版本谱系和更正公告增量传播 |
| Agent 评测 | 工具轨迹、消融、离线案例 | 文档语义错误、Claim 级指标、FinFuzz、真实模型结果 |
| API 任务 | 本地任务状态、事件和重试入口 | SQLite 持久化、幂等、进程重启恢复、Replay |
| 每日复盘 | 快照、gate、确定性报告、在线尝试 | 完整数据源覆盖与可复现历史回放 |
| 估值 | PE/PB/PS、IQR、银行边界 | 假设注册、三情景、敏感性矩阵、完整 Memo 接入 |

## 规划中：尚无对应生产代码

| 能力 | 规格/规划入口 | 状态 | 下一步 |
|---|---|---|---|
| Document Intelligence | `src/cn/documents/`, `tests/test_cn_documents.py`, `docs/development/cards/CARD-01_document_intelligence.md` | partial | 已实现注册、SHA256、TXT/Markdown 分页、PyMuPDF 文本层、页级 bbox、候选营收/净利润、内容变更拒绝和 API；尚缺 OCR 实际执行、多页表合并、完整字段抽取和持久化文档索引 |
| Financial Normalization 独立层 | `src/cn/normalization/`, `tests/test_cn_normalization.py`, `CARD-02_financial_normalization.md` | partial | 已实现单位/币种/期间/flow-stock/scope 规范化、现有 PeriodEngine 桥接和 NormalizeCnFinancialsTool；尚缺文档抽取候选的完整桥接、更多指标维度和下游 Validator 接入 |
| Financial Diagnostics | `src/cn/analysis/`, `tests/test_cn_analysis.py`, `CARD-03_financial_analysis.md` | partial | 已实现同比状态迁移、单季 QoQ、核心比率、FCF 和四类保守诊断信号；尚缺完整 14 项指标、Claim 接入、WorkBench 指标页和更完整的 scope/version 配对门禁 |
| Financial Diagnostics | `CARD-03_financial_analysis.md` | planned | 先覆盖盈利状态迁移和现金质量，全部绑定 Calculation/Evidence |
| Accounting Scope | `src/cn/analysis/scope_signals.py`, `src/cn/documents/parser.py`, `src/cn/evidence.py`, `tests/test_cn_accounting_scope.py`, `CARD-04_accounting_scope.md` | implemented | 六类口径/重述信号、block/use_adjusted/warning 决策、Evidence 绑定、混合 consolidated/parent 计算阻断；未知披露保守阻断同比 |
| Report Checker | `src/cn/checker/`, `tests/test_cn_checker.py`, `CARD-05_report_checker.md` | partial | 已补齐 13 类 planted checker 覆盖、好草稿零误报回归和 `check_raw_report` 自然语言边界；仍缺真实 PDF 草稿解析和真实 benchmark 统计 |
| Evidence Retrieval | `src/cn/retrieval/`, `tests/test_cn_retrieval.py`, `CARD-06_retrieval.md` | implemented | 自研确定性 BM25、BM25 fallback、quote/paraphrase/inference 校验；检索 chunk 与 Evidence 分离，仅显式引用后入账 |
| Run Manifest | `src/cn/runs/`, `tests/test_cn_runs.py`, `CARD-07_run_manifest.md` | implemented | 17 字段 manifest、9 类 stage、append-only 事件哈希链、interrupted/tamper/input-change replay preflight |
| Relative Valuation 增强 | `src/cn/valuation.py`, `tests/test_cn_relative_valuation.py`, `CARD-08_relative_valuation.md` | implemented | TTM 输入门禁、RAW 价格纪律、PE/PB/PS 三情景、Assumption Registry、EPS×PE/BPS×PB 敏感性、方法独立 dispersion 与负分母阻断 |
| Claim-Evidence Graph | `src/cn/graph/`, `tests/test_cn_graph.py`, `CARD-09_claim_evidence_graph.md` | implemented | Claim/Calculation/Thesis 图、trace、孤儿/悬空/不支持检测、环引用拒绝、序列化和 Evidence 停用后的 blocked/stale 传播 |
| Investment Memo | `src/cn/memo.py`, `tests/test_cn_memo.py`, `CARD-10_investment_memo.md` | implemented | 11 段结构化 Memo、JSON/Markdown 双输出、逐句 fact/inference/opinion 标注、Claim 白名单和数值追踪校验、缺失数据降级 |
| Real Benchmark 完整版 | `src/cn/benchmark.py`, `src/cn/real_benchmark.py`, `tests/test_cn_benchmark_v2.py`, `CARD-11_real_benchmark.md` | partial | 已有 24 指标 scorecard、N/A 纪律、fingerprint、synthetic 分片与 real/holdout 隔离；仍缺至少 2 家真实公司全披露链、24 指标逐项单测、FinFuzz/全链集成和授权后的真实运行 |
| Evidence Pack Replay | `src/cn/evidence_pack.py`, `scripts/run_replay_failure_injection.py`, `tests/test_cn_evidence_pack.py`, `CARD-12_evidence_pack_replay.md` | partial | 已有 13 类产物校验、ZIP 导出、损坏事件容错、时间线和 7 场景目录；新增安全复制式失败注入函数/脚本；仍缺完整 Workbench Replay UI |
| Source Conflict | `src/cn/conflict.py`, `tests/test_cn_conflict.py`, `CARD-13_source_conflict.md` | implemented | 四级来源优先级、DATA_CONFLICT/VERSION_SUPERSESSION/NEW_INFORMATION 三态、同级 unresolved 阻断和舍入容差 |
| Prompt Registry | `src/agents/prompts/`, `tests/test_prompt_registry.py`, `CARD-14_prompt_registry.md` | implemented | 版本化 frontmatter 模板、稳定 SHA-256、变量 fail-closed、usage 记录；研究 Agent 已迁移系统 prompt 并可写入 Run Manifest prompt_hash |
| Demo UI 增强 | `src/cn/workbench_demo.py`, `workbench.py`, `api.py`, `src/cn/workbench_service.py`, `tests/test_cn_workbench_service.py`, `tests/test_workbench_api.py`, `scripts/smoke_workbench.py` | partial | 已完成快照/服务层接线、文档上传解析、页级 Viewer、上传后 ACME 检查、按语义分发 run 产物、run 选择、Replay 时间线、Evidence Pack 下载、统一 readiness 契约和 FastAPI 端点；CARD-15 已纳入 13/13 smoke 与本地浏览器无数据降级彩排；候选事实不自动升级，完整真实材料 5 分钟彩排仍需授权的年报、研报草稿和持久化 run |
| DCF | `src/cn/valuation_dcf.py`, `tests/test_cn_dcf.py`, `CARD-16_dcf_valuation.md` | implemented | FCFF DCF、EV→Equity bridge、显式证据门禁、WACC×g 敏感性、行业适用性 Gate、终值发散阻断；真实公司输入仍需授权数据 |
| Quality Diagnostics | `src/cn/quality.py`, `tests/test_cn_quality.py`, `CARD-17_quality_diagnostics.md` | implemented | 十个独立诊断维度、分子/分母/claim 明细、N/A 纪律；不生成未经校准的总分 |
| Multi-Agent | `CARD-18_multiagent.md` | planned/deferred | 必须先有消融证据证明收益，否则不进入主线 |
| Bull/Bear | `CARD-19_bull_bear.md` | planned/deferred | 用 Thesis/Fragility 替代空泛打分 |
| MCP Server | `CARD-20_mcp_server.md` | planned/deferred | 只有独立服务部署或解耦收益成立时才实现 |
| Industry Chain | `CARD-21_industry_chain.md` | planned/deferred | 需要真实数据和金融意义验证，初赛不阻塞 |
| ACME 多模态约束 | `src/cn/acme/`, `tests/test_cn_acme.py`, `CARD-22_acme_multimodal_evidence.md` | partial | 已实现六类确定性检查、显式容差、IntegrityReport/review queue 和 ValidateCnAcmeTool；仍缺真实 PDF/OCR 多模态适配、DocumentService 编排与完整跨源裁决接线 |
| Claim Passport Verifier | `src/cn/proof/`, `tests/test_cn_proof.py`, `CARD-23_claim_passport_verifier.md` | partial | 已实现 FPO、稳定 proof hash、零 LLM 五态 verifier 和 VerifyCnClaimTool；仍缺 Run Manifest 持久化关联、Memo 结论段阻断接线及 CARD-25 版本谱系联动 |
| Thesis Fragility | `src/cn/fragility/`, `tests/test_cn_fragility.py`, `CARD-24_thesis_fragility_engine.md` | partial | 已实现 REQUIRED 路径关键节点、单点依赖、有限 DAG 最小割集、阈值来源白名单和 monitoring plan；仍缺 Memo/UI 接线与 CARD-25 增量重验证联动 |
| Temporal Revalidation | `src/cn/temporal/`, `tests/test_cn_temporal.py`, `CARD-25_temporal_revalidation_engine.md` | partial | 已实现三类 TemporalEvent、append-only version lineage、affected subgraph、状态传播、impact analysis 和 full-vs-incremental 合同；仍缺 Run Manifest 事件持久化、真实 valuation/memo 重算接线 |
| FinFuzz | `src/cn/finfuzz/`, `tests/test_cn_finfuzz.py`, `CARD-26_fin_fuzz.md` | partial | 已实现 10 类确定性 mutation operator、seed 可复现 suite、extractor/checker 失败区分、Overall/per-type 指标和 CARD-11 报告挂载；真实/holdout 数据及完整 Checker operator 联调仍待授权数据与后续接线 |

## 任务顺序

1. CARD-00：本状态表和基线冻结（本卡）。
2. CARD-01：Document Intelligence MVP。
3. CARD-02：Financial Normalization。
4. CARD-03：Financial Diagnostics。
5. CARD-09：Claim-Evidence Graph。
6. CARD-05：Report Checker。
7. CARD-10：Investment Memo。
8. CARD-07：Run Manifest。
9. CARD-12：Evidence Pack Replay。
10. CARD-13 + CARD-25：来源冲突和 Temporal Revalidation。
11. CARD-26：FinFuzz。
12. CARD-11：完整真实模型 Benchmark。
13. CARD-15：UI 增强和拆分。

CARD-16、18、19、20、21 在主链稳定和指标证明后再决定；没有明确收益时保持 deferred。

## 每张卡片完成标准

1. 代码、测试、README、状态表一致。
2. 有正常输入、缺失/错误/冲突测试。
3. 契约覆盖来源、时点、单位、期间、Evidence 和 validation。
4. 默认测试不依赖网络、缓存、.env、墙钟或付费数据。
5. Tool/API schema 有契约测试。
6. 失败时不输出猜测数字或虚假成功。
7. 有成功 Demo 和失败阻断 Demo。
8. 运行默认 pytest、smoke_workbench.py、git diff --check。
9. 在本文件更新状态和已知限制。

## 本基线后的下一张卡

下一张是 CARD-01 Document Intelligence MVP。实现范围只包括：文档注册、SHA256、PDF 文本层抽取、页码 SourceFragment、最小 ExtractedFact、Evidence 接入和离线自造 fixture；暂不实现 OCR 全覆盖、向量检索、完整表格理解或前端重构。
