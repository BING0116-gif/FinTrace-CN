# FinTrace-CN 竞赛版架构（ARCHITECTURE_V2）

> 版本：v3.0 配套架构文档。描述初赛版目标架构与决赛扩展位。
> 原则：技术深度来自系统可信性，不来自技术名词堆砌。

## 1. 端到端主链

```text
真实金融文档（年报/半年报/季报/公告/研报草稿，PDF/TXT/MD/Excel/CSV）
   ↓ Document Intelligence Layer          [CARD-01]
     DocumentRegistry → Parser 组合 → ExtractedFact（带页码/bbox/表格坐标）
   ↓ Financial Normalization Engine        [CARD-02]
     单位/币种/比率 → 期间标准化（YTD→单季） → 口径标注（合并/母公司/重述）
   ↓ Evidence Ledger（现有资产扩展）
     point-in-time 事实，document_id+page+bbox 或 snapshot_id+available_at
   ↓ Deterministic Financial Tools（现有 cn_tools 扩展）
     财务分析引擎 / 相对估值 / 敏感性 —— 全部确定性 Python
   ↓ Financial Diagnostics                 [CARD-03/04]
     单季 QoQ / 盈利状态迁移 / earnings-quality 等诊断信号 / 口径可比性
   ↓ Claim Extraction                      [CARD-05/09]
     自然语言研报 → DraftClaim[]（LLM 提取，结构化输出）
     分析产出 → Claim（fact / inference / opinion 三级）
   ↓ Report Checking（确定性规则引擎）    [CARD-05]
     13 类错误核查：数值/单位/期间/口径/计算/引用/因果
   ↓ Valuation                             [CARD-08 初赛 / 16 决赛]
     PE/PB/PS + Bear/Base/Bull 敏感性矩阵 + Assumption Registry
   ↓ Claim-Evidence Graph                  [CARD-09]
     Document → Source Fragment → Evidence → Calculation → Claim → Conclusion
   ↓ Investment Memo                       [CARD-10]
     11 段买方备忘录，每个数字可回溯，事实/推论/观点逐句标注
   ↓ Validator（fail-closed）              [现有 src/validation 扩展]
     孤儿 claim / 无支撑计算 / 缺失证据 / 口径冲突 → 阻断或降级
   ↓ Evidence Pack + Audit Replay          [CARD-12]
     run_xxx/ 完整产物目录 + events.jsonl 时间线重放
```

## 2. 分层视图

```text
┌ 服务演示层  workbench(Demo UI 增量) | api.py | Audit Replay UI | Evidence Pack 导出
│ 验证层      Claim-Evidence Graph 遍历 | fail-closed Validator | Source Conflict Resolver
│ 编排层      Planner → Tool Executor → Evidence → Validator → Report Generator（单 Agent 主线）
│             Multi-Agent 仅决赛且须消融证明收益                        [CARD-18/19]
│ 计算层      财务分析 | 相对估值+敏感性 | (决赛)DCF | 诊断规则 —— 零 LLM
│ 数据层      Document Registry | Parsers | Normalization | Retrieval | Snapshot Provider(现有)
│ 资产层      Evidence Ledger | Claim 模型 | Assumption Registry | Run Manifest | Prompt Registry
└ 测试层      单测/契约/golden + Synthetic/Real/Holdout 三级基准      [CARD-11]
```

## 3. 核心数据模型

### 3.1 DocumentRecord（CARD-01）

`document_id, sha256, filename, source, document_type(annual/interim/quarterly/announcement/report_draft), company, report_period, publication_date, ingested_at, parser_name, parser_version, page_count`

### 3.2 ExtractedFact（CARD-01 → CARD-02 规范化）

`document_id, page, bbox, section, table, row, column, raw_text, raw_value, normalized_value, currency, unit, period, scope, available_at`

规范化后统一：unit → 基础单位（元）、currency 显式、period 标准键、scope 标注合并/母公司、version 标注原披露/重述/更正后。**flow item 与 stock item 语义分离**：flow（营业收入/营业利润/净利润/CFO/CapEx/费用）是期间流量，单季化需差分；stock（现金/存货/应收/总资产/总负债）是时点存量，**禁止差分**。期间键**唯一采用现有** `FinancialPeriodEngine` 格式：`YYYYQ1 / YYYYH1 / YYYY9M / YYYYFY`，Ttm 推导复用现有 `derive_ttm()`。本卡**桥接而非重写**：`NormalizedFact → FinancialStatement` 适配器 + 调用现有 `derive_single_quarters()` / `derive_ttm()`。

### 3.2b NormalizedFact ↔ FinancialStatement ↔ EvidenceRecord 双链统一数据流（CARD-02 桥接，跨卡硬约束）

仓库存在两条事实来源链，必须统一汇入同一 Evidence Ledger：

| 链 | 入口 | 代表指标 | 定位字段 | 回溯目标 |
|---|---|---|---|---|
| 文档链 | CARD-01 解析真实 PDF/TXT/Excel | 营业收入、净利润、CFO、扣非净利润、三表科目 | `document_id + page + bbox` | PDF 页（Demo 跳转） |
| 快照链 | Snapshot Provider（现有 tushare/akshare） | 行情价、股本、可比集、可用作事实的历史序列 | `snapshot_id + available_at` | 快照 as-of 时间戳 |

**数据流桥接规则**（任何新卡不得绕开）：

```text
文档链：ExtractedFact ──→ NormalizedFact ──→ 适配 ──→ FinancialStatement
                                                       │
快照链：Snapshot row ──────────────────────────────────→│
                                                       ↓
                                          FinancialPeriodEngine（现有）
                                          derive_single_quarters / derive_ttm
                                                       ↓
                                              Evidence Ledger（扩展后）
```

- `FinancialStatement` 是两条链的**汇合节点**：适配器把 NormalizedFact 投影到现有 `src/cn/domain.py` 的 `FinancialStatement`（字段一对一：metric→value_dict，fiscal_period=期间键，scope→statement_type/scope）。桥接代码在 `src/cn/normalization/adapter.py`。
- **Evidence Ledger 必须扩展**（现有 `EvidenceRecord` 追加字段，**不新建平行账本**）：新增 `document_id: str | None`、`page: int | None`、`bbox: tuple | None`、`normalized_fact_id: str | None` 四个可空字段。快照型证据这四项全 None，保留原 `provider/field_path/snapshot_id`（通过现有 `add_fact` 入参传递 snapshot 身份）；文档型证据携带四项定位字段。
- **Claim 的 evidence_ids 可以指向两条链任意来源**，图谱 trace() 按 EvidenceRecord 上哪个定位字段非空决定回溯目标：有 document_id/page/bbox → 跳 PDF 页；否则跳 snapshot available_at。
- 混源 Claim（一个结论引用文档链指标+快照链指标）必须标注 `confidence_source: "mixed"` + 两类来源的清单；Validator 对此类 Claim 不加阻断，但报告输出时显式说明“部分数据来自快照不可回跳原文”。

### 3.3 Claim（CARD-09）

`claim_id, claim_type(fact|inference|opinion), text, evidence_ids, calculation_ids, derived_from, confidence, validation_status`

- fact：必须直接绑定 Evidence
- inference：必须可追踪 derived_from 的 fact
- opinion：必须显式标注假设或主观判断来源

### 3.4 Calculation

`calculation_id, formula, inputs[]（每个 input 绑定 evidence_id 或 calculation_id）, output, unit, executed_at, tool_version` —— 计算过程可独立复核。

### 3.5 RunManifest（CARD-07）

`run_id, started_at, finished_at, input_document_sha256[], snapshot_id, model, model_provider, model_version, temperature, prompt_hash, skill_hash, parser_name, parser_version, git_commit, tool_versions, random_seed, execution_mode`

同一输入 + 同一配置 → 重新执行（审计回放的基础）。

### 3.6 ConflictRecord（CARD-13）

`conflict_id, source_a, source_b, selected_source, reason, resolver, timestamp` —— 冲突永不静默覆盖。

### 3.7 Assumption（Assumption Registry，CARD-08/16）

`assumption_id, value, source, reason, valid_from` —— 每个估值假设显式登记，结果可追溯 数据→公式→假设→输出。

## 4. LLM 边界（实现层面的强制点）

| 允许 | 强制点 |
|---|---|
| 自然语言 → 结构化 Claim 提取 | 提取输出过 schema 校验；逐条携带原句 |
| 检索综合、推论生成 | 推论必须标 inference + derived_from |
| 报告组织 | 数值只能来自确定性渲染段落 |

| 禁止 | 拦截机制 |
|---|---|
| LLM 产出数值进入结论 | unverified_number 检查（trace_validator） |
| quote 被改写 | 逐字一致性校验 |
| inference 冒充 fact | claim_type 校验 + validator 遍历 |

## 5. 模块与路径规划

```text
src/cn/documents/          # CARD-01: registry.py, parsers/(pdf_text, table, ocr_fallback),
                          #         statement_parser.py, announcement_parser.py, draft_parser.py
src/cn/normalization/     # CARD-02: units.py, periods.py(扩展), scope.py, convert.py
src/cn/analysis/          # CARD-03/04: trends.py, diagnostics.py, scope_signals.py
src/cn/checker/            # CARD-05: claim_extractor.py(LLM), checker.py(确定性), findings.py
src/cn/retrieval/          # CARD-06: corpus.py, bm25.py, hybrid.py, citation.py
src/cn/runs/              # CARD-07: manifest.py, events.py
src/cn/graph/              # CARD-09: claims.py, graph.py, traversal.py
src/cn/memo.py             # CARD-10
src/cn/conflict.py         # CARD-13
src/cn/valuation.py        # CARD-08 扩展（现有文件增量改）
src/agents/prompts/        # CARD-14: registry.py + templates/
src/cn/valuation_dcf.py    # CARD-16（决赛）
src/cn/multiagent/         # CARD-18/19（决赛）
src/mcp_server/            # CARD-20（决赛，P3）
data/documents/            # 真实文档（gitignore）
data/benchmark_real/       # 真实基准材料（gitignore，配下载脚本+校验和）
tests/fixtures/documents/  # 合成文档（入库，生成脚本一并提交）
```

## 6. 明确不做的事

- 不迁移 React / 微服务 / Kubernetes / 消息队列
- 不引入 MongoDB / Redis / LangGraph / 向量数据库（FAISS/Chroma）
- 不做 OCR 深度自研（pdfplumber 基线 + 可选 MinerU/PaddleOCR，决赛再说）
- 不为覆盖七赛题堆功能；不为 PPT 上的名词增加无业务价值的协议层
- 不用无理论依据的公式（多空评分、估值区间取交集/并集、虚构权重总分）

## 7. 与 v2 架构的差异

1. 数据入口从"快照优先"变为"真实文档优先"（快照保留，服务估值与市场数据）
2. 新增 Normalization / Claim / Calculation / RunManifest / ConflictRecord 五个一等公民数据模型
3. "事实/推论/观点"从 Section 级下沉到 Claim 级
4. 检索 chunk 与 Evidence 解耦（只有被引用才入账）
5. Multi-Agent / MCP / Skill / DCF 从核心链移除，降为决赛可选且须证明收益
