# FinTrace-CN 后续开发总方案（AI 可执行版）

## 1. 目标

把项目从“带有可信边界的 A 股研究 Agent 原型”升级为“面向 A 股年报、季报和公告的可验证金融研究系统”：

问题 / PDF / 公告 / Snapshot
→ 文档注册、哈希、解析、OCR、表格抽取
→ 单位、币种、期间、口径、flow-stock、版本规范化
→ Evidence Ledger（来源、页码、bbox、available_at）
→ 单季化、TTM、财务诊断、相对估值、敏感性
→ Claim-Evidence Graph（fact/inference/opinion）
→ Validator 与状态传播（supported/weakened/stale/blocked）
→ Research Report / Investment Memo / API / Workbench
→ Run Manifest / Replay / Benchmark / FinFuzz

最终要能回答：一个数字从哪里来？一个结论依赖什么？数据更正后哪些结论过期？为什么系统拒绝下结论？

## 2. 现状基线

- 已有 A 股符号、Snapshot Provider、Point-in-Time、期间转换、Evidence Ledger、PE/PB/PS、Validator、FastAPI、Streamlit、Agent 工具循环、离线 Benchmark。
- 当前离线基线应重新运行确认；上次检查为 320 passed、1 deselected。
- 主要缺口：真实文档输入、页码级证据、独立规范化层、Report Checker、Claim Graph、Investment Memo、Run Manifest/Replay、Temporal Revalidation、FinFuzz、真实模型结果。
- workbench.py 约 1700 行，应在核心链路稳定后拆分。
- 自带数据主要是 illustrative/synthetic fixture；版权年报、付费数据、API Key 和运行输出不得进入 Git。
- 文档里的“已实现”与“未开始”必须用状态表校准。

## 3. 不可破坏的原则

1. Provider fact、Python deterministic calculation、LLM narrative 三者分离。
2. LLM 不创建财务事实、最终算术、Evidence 或 Validator 决策。
3. 每个数字至少记录 provider/snapshot/document、cutoff、period、unit、currency、scope、Evidence ID 和 validation。
4. 缺失、冲突、过期、解析不完整时只能降级、标记不可核验或阻断，不能补猜数字。
5. 工具统一返回结构化 status envelope：ok、partial、warning、blocked、stale、conflicted、failed、cancelled。
6. 默认测试离线，不依赖 .env、缓存、网络、墙钟或付费数据。
7. 不重新引入美股、Yahoo Finance、加密、预测市场、旧 Supervisor；不为简历堆 Multi-Agent、MCP、向量库或实时预测。

## 4. 目标目录

新增目录按需落地：

    src/cn/documents/       文档注册、PDF、表格、OCR
    src/cn/normalization/   单位、币种、期间、scope、flow-stock
    src/cn/analysis/        财务诊断和信号
    src/cn/claims/          Claim、Graph、传播、验证
    src/cn/memo/            投资备忘录和逐句校验
    src/cn/temporal/        版本谱系和增量重验证
    src/cn/runs/            Manifest、事件和 replay
    src/cn/finfuzz/         金融语义变异和指标
    src/ui/                 Streamlit 页面和共享组件
    tests/fixtures/documents/

建议测试文件：

    tests/test_cn_documents.py
    tests/test_cn_normalization.py
    tests/test_cn_claim_graph.py
    tests/test_cn_memo.py
    tests/test_cn_temporal.py
    tests/test_cn_runs.py
    tests/test_cn_finfuzz.py

## 5. 版本路线

| 版本 | 交付 |
|---|---|
| v3.3 | 文档注册、PDF 文本、页码 Evidence、规范化 MVP |
| v3.4 | 财务诊断、Report Checker、Claim Graph、Memo |
| v3.5 | Run Manifest、Replay、版本谱系、Temporal Revalidation |
| v3.6 | FinFuzz、真实模型 Benchmark、SQLite 任务持久化、UI 拆分 |
| v4.0 | 稳定 Demo、完整文档、评测材料 |

延期时保留“真实文档 → Evidence → Claim → Memo → Validator”垂直闭环，砍横向功能，不砍主链。

## 6. 阶段 0：基线冻结

### 任务

1. 运行：

    python -m pytest -q -m "not integration" -p no:cacheprovider
    python scripts/smoke_workbench.py
    git diff --check
    git status --short

2. 新建 docs/development/IMPLEMENTATION_STATUS.md，逐项记录能力、代码入口、测试入口、状态、限制和下一步。
3. 状态只允许 implemented、partial、planned、deprecated。
4. README 只描述实际完成能力，未来能力进入路线图。
5. 记录基线 commit、Python 版本、依赖版本和测试命令。

### 验收

状态表、README、MASTER_PLAN、CARD 不再互相矛盾；新 AI 可以判断一项能力是否真的完成。

## 7. 阶段 1：Document Intelligence MVP

### 用户结果

用户上传 PDF 后，系统显示文件哈希、报告元数据、页码、原文片段和候选事实；解析不完整明确显示 partial。

### 文件

src/cn/documents/schema.py、registry.py、pdf_parser.py、table_parser.py、ocr.py、service.py，以及 API、fixture 和测试。

### 数据模型

DocumentRecord：

    document_id, file_name, document_type
    symbol, fiscal_period, published_at, ingested_at
    sha256, parser_name, parser_version, page_count
    status=complete|partial|failed
    source=user_upload|local_fixture|provider
    warnings

SourceFragment：

    fragment_id, document_id, page_number, text, bbox
    text_sha256, extraction_method=text_layer|table|ocr
    confidence=exact|normalized|ocr|unavailable

ExtractedFact：

    fact_id, metric, raw_value, raw_unit, raw_currency
    period, scope, source_fragment_id
    extraction_status=extracted|ambiguous|rejected
    warnings

### 解析规则

1. 首选文本层；空文本页进入 OCR。
2. OCR 不可用时页面 failed、文档 partial。
3. 表格和文本冲突时保留两个候选，不静默覆盖。
4. Parser 只抽取原文和候选值，不决定最终财务事实。
5. 文件类型、大小、页数必须有界。
6. API 不回显绝对路径、原始 traceback 或敏感内容。
7. 版权文档只作为本地输入。

### API

POST /api/documents/register
POST /api/documents/{document_id}/parse
GET /api/documents/{document_id}
GET /api/documents/{document_id}/fragments
GET /api/documents/{document_id}/facts
GET /api/documents/{document_id}/artifacts

返回 status、data、document_id、warnings、validation。

### 测试和退出条件

- 文本型 PDF 成功；空文本页走 OCR 或 partial。
- SHA256 稳定；页码从 1 开始；片段能反向定位。
- 表格/文本冲突不覆盖；不支持格式返回 typed error。
- 至少一个自造离线文档完成“注册 → 解析 → Fragment → Fact → Evidence”。

Demo：上传自造年报，点击净利润下降，展示页码、原文、抽取值、解析方式和 Evidence ID。

## 8. 阶段 2：Financial Normalization

### 目标

任何进入估值或报告的财务事实都经过同一规范化层，同时保留原始值和转换规则。

NormalizedFact 必须包含：

    fact_id, metric
    raw_value, raw_unit
    normalized_value, normalized_unit
    currency
    period_basis=FY|Q1|H1|9M|TTM
    economic_period
    scope=consolidated|parent
    flow_stock=flow|stock
    source_evidence_ids
    normalization_rule
    validation_status=normalized|ambiguous|rejected
    warnings

### 必须支持

- 元、万元、百万元、亿元；百分比和小数。
- CNY/非 CNY 只有汇率 Evidence 时转换。
- FY/H1/9M 累计转单季。
- TTM = current_ytd + prior_fy - prior_comparable_ytd。
- flow 可做期间转换，stock 不做累计。
- 合并/母公司不自动混合。
- 亏损基期不输出虚假同比百分比。
- 缺失、零、负、不适用分开。
- period、unit、currency、scope 不明时 ambiguous 或 blocked。

新增 NormalizeCnFinancialFactsTool，只接受已注册 Evidence。

测试覆盖：9M 冒充 Q3、亿元/万元、FY/H1、合并/母公司、亏损基期、缺少上年同期、币种不一致、flow/stock 错换。

退出条件：Snapshot 和新文档都通过同一个 NormalizedFact，再进入估值、诊断和报告。

## 9. 阶段 3：Financial Diagnostics

### 目标

增加描述业绩状态的确定性信号，不把诊断伪装成因果。

DiagnosticSignal：

    signal_id, code, severity=info|warning|critical
    claim_type=inference
    description
    input_fact_ids, calculation_ids, period
    validation_status, limitations

至少实现收入、利润、毛利率、净利率、CFO/NI、应收和存货信号；覆盖正常、扭亏为盈、由盈转亏、亏损扩大、亏损收窄、零基期。

“毛利率下降”不能直接写成“由于某因素导致毛利率下降”，除非有明确管理层归因 Evidence。

## 10. 阶段 4：Claim-Evidence Graph

### 目标

把孤立 Evidence ID 升级为可遍历、可校验、可传播状态的图。

Claim 节点：

    claim_id
    claim_type=fact|inference|opinion
    temporal_status
    text
    evidence_ids
    calculation_ids
    derived_from
    dependencies（role=REQUIRED|SUPPORTING|OPTIONAL）
    verification_status
    validation_status
    rationale

Calculation 节点：

    calculation_id, formula, formula_version
    inputs, output, code_version, validation_status

Thesis 节点：

    thesis_id, statement, claim_ids
    dependency_roles, status

### 校验

- fact 无 Evidence：orphan。
- inference 无 derived_from：结构错误。
- opinion 无 assumption：结构错误。
- calculation 缺输入：unsupported。
- Evidence ID 不存在：missing。
- 环依赖：构建失败。
- 图构建失败：输出 graph_incomplete，不输出假完整图。

### 状态传播

REQUIRED 上游 blocked/conflicted 时下游至少 blocked/stale；SUPPORTING 只降低支持完整度；OPTIONAL 不影响核心有效性。禁止未经校准的伪置信分数。

### API/工具

GET /api/runs/{run_id}/claims
GET /api/runs/{run_id}/claims/{claim_id}/trace
GET /api/runs/{run_id}/graph
POST /api/runs/{run_id}/evidence/{evidence_id}/deactivate
POST /api/runs/{run_id}/revalidate

工具：TraceCnClaimTool、DeactivateCnEvidenceTool、ValidateCnClaimGraphTool。

退出条件：好数据场景 orphan/unsupported/missing 均为 0；停用关键 Evidence 后相关 Claim、Thesis、Memo 段落变为 blocked/weakened。

## 11. 阶段 5：Report Checker

### 目标

核查研究报告草稿，严格区分 supported、contradicted、unverifiable、unsupported_causal、malformed。

ReportFinding：

    finding_id, sentence_span, finding_type
    error_class=numeric|unit|period|scope|citation|causal|valuation
    expected, observed, evidence_ids
    severity, explanation, suggested_fix

LLM 只抽取候选 Claim；数字、单位、期间、口径、引用和因果判断由确定性代码比对。无 Evidence 只能 unverifiable，不能直接 contradicted。

测试至少覆盖 numeric、unit、period、scope、citation、causal、valuation、错误页码、错误 Evidence ID 和无法核验。

## 12. 阶段 6：Investment Memo

### 目标

输出逐句标注、数字可追溯的 11 段买方备忘录：

executive_summary、company_overview、financial_performance、investment_thesis、valuation、catalysts、risks、counter_thesis、falsification、tracking_kpis、evidence_appendix。

financial_performance、valuation、tracking_kpis 优先模板化；thesis、risks、counter_thesis、catalysts 可以由 LLM 组织语言，但只能引用白名单 Claim ID。

MemoSection：

    section_id, body_markdown, sentence_claims, evidence_ids, status

InvestmentMemo：

    memo_id, run_id, symbol, sections, validation, generated_at

规则：事实句必须有 Evidence；inference 必须有 derived_from；数字句必须有 calculation/Evidence；缺数据段落使用 data_unavailable；blocked Claim 不能隐藏。

## 13. 阶段 7：Run Manifest、事件和 Replay

RunManifest 必须记录：

    run_id, started_at, finished_at
    input_document_sha256, snapshot_id
    model, model_provider, model_version
    temperature, prompt_hash, skill_hash
    parser_name, parser_version, git_commit
    tool_versions, random_seed
    execution_mode=offline|real_model|replay
    status

事件写入 runs/<run_id>/events.jsonl，只追加。每行包括 ts、run_id、stage、event_type、input_digest、output_digest、status、detail。

Replay 规则：

1. 输入 SHA256 不一致时拒绝。
2. git commit 不同时显式标记。
3. 确定性计算比较数值、单位、期间和状态。
4. LLM 只比较 Claim 引用、数字和状态，允许文本采样差异。
5. 原始 run 不修改，只生成新的 replay run 和 diff。

退出条件：完整研究任务有 manifest/events；Replay 后确定性部分完全一致；输入被修改时 Replay 被拒绝。

## 14. 阶段 8：Temporal Revalidation

事件必须区分 DATA_CONFLICT、VERSION_SUPERSESSION、NEW_INFORMATION。

VersionLineageEntry：

    fact_id
    version_status=AS_REPORTED|RESTATED|CORRECTED|SUPERSEDED
    supersedes, superseded_by, reason
    source_published_at, ingested_at

增量算法：

changed_node_ids
→ 沿依赖方向 BFS/DFS
→ affected_subgraph
→ 只重算 calculation/claim/thesis/valuation/memo
→ state_diff
→ 与 full recomputation 比较

必须验证旧证据不被覆盖、冲突未裁决时下游阻断、new information 产生 stale/refresh、affected_subgraph 覆盖 state_diff、增量与全量结果一致、循环依赖被拒绝。

## 15. 阶段 9：FinFuzz

第一批变异算子：

numeric、unit、sign、period、ytd_vs_single、scope、version、valuation、citation、causal。

每个 MutationSpec 保存 source claim、mutated claim、diff、expected_detection 和 seed。指标包括 overall Precision/Recall/F1、per-error-type Recall、False Positive Rate，并区分 extractor failure 和 checker failure。无样本类别显示 N/A。

第一阶段至少接入 numeric、unit、period、scope、citation；所有算子都必须有单测。

## 16. 阶段 10：Benchmark 和真实模型

离线评测固定 snapshot、案例版本和 expected outcome，分别测工具选择、参数、顺序、Evidence coverage、计算一致性、Validator 拦截率、错误泄漏率和 blocked case 正确率。

真实模型必须记录 model/provider/version、prompt hash、temperature、max steps、snapshot、benchmark version、git commit、工具轨迹、错误、延迟和成本。

dry-run 只能描述为机制验证；不以 LLM judge 判定财务算术和引用正确性；所有指标必须有明确分母。

## 17. 阶段 11：任务持久化和 UI

第一阶段使用 SQLite + append-only 文件事件，不引入 Redis/MongoDB。任务字段：

task_id、run_id、kind、status、idempotency_key、created_at、started_at、finished_at、attempt、error_type、progress、input_digest、output_digest。

必须支持查询、取消、重试、幂等、防重复执行和进程重启后 interrupted。

稳定后将 workbench.py 拆为：

src/ui/pages/research.py
src/ui/pages/documents.py
src/ui/pages/evidence.py
src/ui/pages/claims.py
src/ui/pages/memo.py
src/ui/pages/replay.py
src/ui/components/status_badge.py
src/ui/components/evidence_trace.py
src/ui/components/event_timeline.py
src/ui/components/validation_panel.py

UI 不做财务计算，不改变 Validator 状态，业务逻辑继续在 src/cn 服务层。

## 18. AI 开发卡片格式

以后给 AI 的每张任务卡必须包含：

任务名、目标、范围内、范围外、现有入口、数据契约、确定性边界、失败模式、实现步骤、测试要求、验收命令、Demo、完成后需要更新的文档。

推荐任务提示词：

    你正在维护 FinTrace-CN。先阅读 AGENTS.md、docs/DEVELOPMENT_ROADMAP_AI.md、目标模块、相邻测试和相关技能规范。
    本次只实现 CARD-XX：<任务名>。
    A-share only；不得引入被移除的美股/加密/预测市场/旧 Supervisor。
    Provider fact、deterministic calculation、LLM narrative 必须分离。
    不用 LLM 补缺失数字，不静默混合期间、单位、币种、口径。
    工具返回 status envelope，不返回裸字符串或原始异常。
    默认测试离线，不依赖 .env、网络、缓存或墙钟。
    先列计划和受影响文件，再用 apply_patch 修改。
    写正常、负面、边界和契约测试。
    运行聚焦测试、全量离线测试、smoke_workbench.py、git diff --check。
    报告修改、测试结果、未完成项、风险和后续建议。
    发现测试或文档冲突时报告冲突，不为绿色测试削弱 Validator。

## 19. Definition of Done

一张卡片只有同时满足以下条件才算完成：

1. 代码、测试、README、状态表一致。
2. 有正常输入和缺失/错误/冲突测试。
3. 契约覆盖来源、时点、单位、期间、Evidence 和 validation。
4. 不依赖 .env、网络、缓存或运行顺序。
5. API/Tool schema 有契约测试。
6. 失败时不输出猜测数字或虚假成功。
7. 有成功 Demo 和失败阻断 Demo。
8. 默认测试、smoke、diff check 全部通过。

## 20. 执行顺序

1. 基线冻结和状态校准。
2. 文档注册、PDF 文本、页码 Evidence。
3. 单位、期间、口径规范化。
4. Claim-Evidence Graph。
5. Report Checker。
6. Investment Memo。
7. Run Manifest 和 Replay。
8. Temporal Revalidation。
9. FinFuzz。
10. 真实模型 Benchmark。
11. SQLite 任务持久化。
12. Streamlit 模块化。

## 21. 最终简历材料

必须准备：

1. 成功案例：文档或 Snapshot 到 Memo，展示至少 3 个数字和 3 条结论的证据链。
2. 失败注入：删除 Evidence、改单位、改期间或导入更正公告，展示 blocked/stale 传播。
3. 评测报告：工具路由、Evidence coverage、错误检测、阻断率、成本、延迟。
4. Replay 报告：manifest、重新执行、确定性部分一致、LLM 文本差异边界。

简历只填写真实运行结果；设计目标、mock 结果和未来计划必须明确标注。
