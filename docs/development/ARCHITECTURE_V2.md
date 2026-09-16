# FinTrace-CN 竞赛版架构（ARCHITECTURE_V2）

> 版本：v3.2 编码前冻结版 ｜ 配套 DUAL_COMPETITION_POSITIONING.md（双赛同构叙事）
> 系统定义：**面向 A 股投研的多模态可验证与可证伪金融智能体**。
> 核心理念：**让每个金融结论可证明，让每个投资逻辑可证伪，让每次信息变化可重验证。**
> 原则：技术深度来自系统可信性，不来自技术名词堆砌。Multi-Agent / MCP / Skill / DCF / RAG 均为 supporting technologies，非主创新。

## 1. 端到端主链

```text
真实金融文档（年报/半年报/季报/公告/研报草稿，PDF/TXT/MD/Excel/CSV）+ Snapshot Provider
   ↓ Document Intelligence Layer          [CARD-01]
     DocumentRegistry → Parser 组合 → ExtractedFact（带页码/bbox/表格坐标）
     + Controlled Environment Guard（untrusted data 注入防护/路径拦截/禁外网）
   ↓ Financial Normalization Engine        [CARD-02]
     单位/币种/比率 → 期间标准化（YTD→单季） → 口径标注（合并/母公司/重述）
   ↓ ACME Constraint Layer                 [CARD-22，创新一]
     六类约束族（会计恒等式/表格结构/期间/跨期/跨源/跨模态）→ 检测+定位+阻断
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
   ↓ Financial Claim Passport（FPO）      [CARD-23，创新二]
     关键 Claim → 完整证明对象 → verify_claim() 脱离 LLM 重新验证
   ↓ Claim-Evidence / Thesis Graph         [CARD-09]
     Document → Evidence → Calculation → Claim → Thesis（REQUIRED/SUPPORTING/OPTIONAL）
   ↓ Fragility Engine                       [CARD-24，创新三]
     critical dependency / minimal cut set / numeric fragility / monitoring plan
   ↓ Investment Memo                       [CARD-10]
     11 段买方备忘录，每个数字可回溯，事实/推论/观点逐句标注
   ↓ Validator（fail-closed）              [现有 src/validation 扩展]
     孤儿 claim / 无支撑计算 / 缺失证据 / 口径冲突 / 阻断或降级
   ↓ Temporal Revalidation                 [CARD-25，创新三]
     version lineage + 三态区分 + affected-subgraph 增量重算
   ↓ Evidence Pack + Audit Replay          [CARD-12]
     run_xxx/ 完整产物目录 + events.jsonl 时间线重放

━━ 系统外部：FinFuzz（CARD-26 + CARD-11 集成）对整个 Pipeline 做 adversarial testing ━━
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

`document_id, page, bbox, section, table, row, column, raw_text, raw_value, normalized_value, currency, unit, source_period, economic_period, scope, source_published_at, ingested_at, availability_precision, pit_eligible`

规范化后统一：unit → 基础单位（元）、currency 显式、source_period 标准键（原始披露期间）、economic_period（数据实际对应的经济期间）、scope 标注合并/母公司、version 标注原披露/重述/更正后。**flow item 与 stock item 语义分离**：flow（营业收入/营业利润/净利润/CFO/CapEx/费用）是期间流量,单季化需差分；stock（现金/存货/应收/总资产/总负债）是时点存量，**禁止差分**。

**期间键统一采用现有** `FinancialPeriodEngine` 格式：`YYYYQ1 / YYYYH1 / YYYY9M / YYYYFY`，TTM 推导复用现有 `derive_ttm()`。本卡**桥接而非重写**：`NormalizedFact → FinancialStatement` 适配器 + 调用现有 `derive_single_quarters()` / `derive_ttm()`。

**source_period 与 economic_period 分离**（v3.0 盲区修正）：
- source_period：原始披露期间，例如 `2025H1`
- economic_period：数据真正对应的经济期间，例如 `2025Q2`（由 H1−Q1 推导）
- 禁止使用 `2025H1 + SINGLE_QUARTER` 这种语义含混方式代表 Q2
- 必须可表示：2025Q1、2025Q2、2025Q3、2025Q4、2025H1、2025M9、2025FY、TTM period

**report_type × "本报告期"语义**（v3.0 盲区修正）：
- annual：`"本年"/"本报告期"` → FY / YTD annual period，**不得**把年报"本报告期"理解为 Q4 single
- semiannual：`"本报告期"` → H1 YTD
- Q1：`"本报告期"` → Q1 single；`"年初至报告期末"` → Q1 YTD（两者经济区间相同，但 source semantics 可不同）
- Q3：`"本报告期"` → Q3 SINGLE_QUARTER；`"年初至报告期末"` → 9M YTD
- period parser 必须添加 report_type context，补对应 unit tests

**Point-in-Time 语义修正**（v3.0 盲区修正）：
- source_published_at：文档实际发布时间（无则 unknown）
- ingested_at：系统摄入时间
- availability_precision：exact_timestamp | date_only | unknown
- pit_eligible：是否可用于 point-in-time 回测（unknown 时 false）
- **禁止**：publication date 缺失时把 ingest time 当 available_at（制造假精确）

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

`claim_id, claim_type(fact|inference|opinion), temporal_status(historical|current|forward_looking), text, evidence_ids, calculation_ids, assumption_ids, derived_from, dependency_metadata[{role: REQUIRED|SUPPORTING|OPTIONAL, target_id}], verification_status, validation_status, rationale`

**claim_type 与 temporal_status 分离**（v3.0 盲区修正）：
- claim_type：fact / inference / opinion（认识论维度）
- temporal_status：historical / current / forward_looking（时间维度）
- valuation 作为 claim subtype / domain，不与 fact/inference/opinion 混成同一维度
- **禁止**把 forward_looking 和 factual/valuation/causal/opinion 放在同一个 enum

**因果 Claim 验证逻辑修正**（v3.0 盲区修正）：
- **禁止**"因果两侧都有 Evidence，因此因果成立"的逻辑
- 必须区分三级因果：
  1. explicit_attribution：原文/公司管理层明确说明 A 导致 B
  2. analyst_inference：A 和 B 都有证据，但因果只是分析推断
  3. unsupported_causal：因果链缺乏足够证据
- 报告必须明确区分：fact / management-attributed cause / analyst inference，不能混为一谈

**verification_status 取代 confidence 数值**（v3.0 盲区修正）：
- **删除**没有校准依据的 0.8 / 0.9 / 1.0 confidence（exact=1.0, normalized=0.9, period_inferred=0.8）
- 改为离散 verification_status：EXACT_MATCH | ROUNDING_MATCH | NORMALIZED_MATCH | PERIOD_INFERRED | CONFLICTED | UNVERIFIABLE
- 如果未来需要 numerical confidence，必须有 calibration 方法

**依赖语义**（REQUIRED / SUPPORTING / OPTIONAL）：
- REQUIRED：上游依赖 blocked/stale 且未被替代 → 下游 Claim blocked/stale
- SUPPORTING：依赖失效 → coverage / support status 降级，但不自动 blocked
- OPTIONAL：不影响核心有效性
- 默认关键 Claim 上游依赖为 REQUIRED
- 必须支持 orphan claim 检测

- fact：必须直接绑定 Evidence
- inference：必须可追踪 derived_from 的 fact
- opinion：必须显式标注假设或主观判断来源

### 3.4 Calculation（与 Evidence 语义边界明确）

`calculation_id, formula_id, formula_version, inputs[]（每个 input 绑定 evidence_id 或 calculation_id）, deterministic_output, unit, period, code_version, validation_status`

**Evidence 与 Calculation 语义边界**（v3.0 盲区修正）：
1. Evidence 只表示原始来源中直接披露/观察到的证据
2. 以下内容**不得**作为原始 Evidence，必须是 Calculation output：
   - Q2 = H1 − Q1
   - Q4 = FY − 9M
   - TTM
   - YoY / QoQ
   - Margin（毛利率、净利率等）
   - PE / PB / PS
   - 财务诊断 signal
3. Calculation 必须记录：calculation_id、formula_id / formula_version、input evidence/calculation IDs、deterministic output、unit、period、code version、validation_status
4. Claim 可以依赖：Evidence、Calculation、upstream Claim、Assumption

### 3.5 RunManifest（CARD-07）

`run_id, started_at, finished_at, input_document_sha256[], snapshot_id, model, model_provider, model_version, temperature, prompt_hash, skill_hash, parser_name, parser_version, git_commit, tool_versions, random_seed, execution_mode`

同一输入 + 同一配置 → 重新执行（审计回放的基础）。

### 3.6 ConflictRecord（CARD-13）

`conflict_id, source_a, source_b, selected_source, reason, resolver, timestamp` —— 冲突永不静默覆盖。

### 3.7 Assumption（Assumption Registry，CARD-08/16）

`assumption_id, value, source, reason, valid_from` —— 每个估值假设显式登记，结果可追溯 数据→公式→假设→输出。

### 3.8 股本字段拆分（v3.0 盲区修正）

**禁止**用一个 `diluted_shares` 同时承担所有用途。至少拆分：
- `shares_outstanding_end`：期末总股本（时点值，用于 BPS / 每股净资产计算）
- `weighted_average_basic_shares`：加权平均基本股份（用于 EPS 计算）
- `weighted_average_diluted_shares`：加权平均稀释股份（用于稀释 EPS 计算）

**说明**：
- EPS 使用加权平均股份口径
- BPS / 每股净资产通常使用期末股份口径
- 估值输出必须记录使用了哪个 shares basis

### 3.9 revenue 字段不过度归一（v3.0 盲区修正）

**不得**默认"营业收入"和"营业总收入"在所有行业中完全等义。区分：
- `operating_revenue`：营业收入
- `total_operating_revenue`：营业总收入

只有在报表结构或行业规则确认可等价时才归一。

**初赛明确**：重点支持非金融 A 股上市公司；银行、保险、券商进入 special-industry gate，部分指标和估值方法降级。

### 3.10 比率的经济意义保护（v3.0 盲区修正）

对于 CFO / Net Profit、Non-recurring Profit / Net Profit 等比率指标，必须处理 net_profit <= 0 或接近 0 的情况：
- **不能**输出极端百分比后继续解释为正常"盈利质量"
- 应返回：`not_meaningful` / `turnaround` / `loss context` 或等价状态
- 报告输出时显式标注"该比率在当前盈利状态下无经济意义"

### 3.11 TTM PE 与 Forward/NTM PE 分离（v3.0 盲区修正）

**修正**任何"TTM PE 隐含未来 12 个月盈利"的表述。必须定义：
- `PE_TTM = Price / trailing twelve month EPS`（历史 12 个月）
- `PE_NTM = Price / forecast next twelve month EPS`（未来 12 个月一致预期）

**初赛**如无可靠一致预期数据，以 PE_TTM 为主，**不得**把历史 FY EPS、TTM EPS、Forward EPS 混用。

### 3.12 SourceLocator 抽象（v3.0 盲区修正）

**补齐** Parser 与 Source Locator 统一抽象，不同文档类型使用不同定位字段：

**PDF**：
- page
- bbox (x0, y0, x1, y1)
- table / row / column

**Excel**：
- sheet
- cell / range

**CSV**：
- row
- column

**TXT / Markdown**：
- line_start
- line_end

**禁止**让所有来源都硬套 page/bbox。SourceLocator 是统一接口，具体字段按文档类型适配。

### 3.13 Conflict 与 Supersession 分离（v3.0 盲区修正）

"原披露值 → 更正公告值"通常不是普通双来源 conflict，而是版本替代。

Source Resolver 必须区分：
- `data_conflict`：同期间同口径两个不同值（如两家第三方源不一致）
- `version_supersession`：新版本明确替代旧版本（如更正公告）
- `restatement`：重述（会计政策变更或前期差错更正）

**版本 lineage 至少记录**：
- version_id
- version_status（active / superseded / restated）
- supersedes（被替代的旧 version_id）
- superseded_by（替代它的新 version_id）
- reason
- source_published_at

**旧值不得静默删除**，要可回放历史视图。

### 3.14 Claim Synthesis Stage（v3.0 盲区修正）

**新增** Claim 综合阶段，Investment Memo 不得只依赖研报草稿里已有 Claim。

**数据流**：
```
Evidence / Calculation / Retrieval
  ↓
LLM proposes candidate claim
  ↓
structured Claim (with claim_type, temporal_status, evidence_ids, etc.)
  ↓
Graph / Validator validation
  ↓
approved claim whitelist
  ↓
Memo Writer (只能使用 approved claim IDs)
```

**关键约束**：
- LLM 可以提出 inference / opinion
- 但未经 Graph Validator 的 candidate claim **不得**进入最终 Memo
- Memo Writer 只能使用 approved claim IDs
- **Falsification condition**：threshold 可以为空；只有有可靠依据时才给数值阈值；**不得**为了"可计算"让 LLM 编造 10%、20% 等阈值

### 3.15 PeerSet Methodology（v3.0 盲区修正）

**相对估值还必须补 PeerSet Methodology**，比完整 DCF 更优先。

PeerSet 至少记录：
- peer_symbol
- industry
- business_similarity / rationale
- size_bucket
- profitability_status
- included
- inclusion_reason
- exclusion_reason
- as_of

**初赛**可以采用可解释规则：
- 申万/中信行业层级
- 市值区间
- 盈利状态
- 主营业务关键词
- 人工 override（必须记录原因）

估值报告必须能够回答："为什么选这几家公司作为可比公司？"

### 3.16 Financial Statement Integrity Validator（v3.0 新增）

**新增** Financial Statement Integrity Validator / Accounting Integrity Validator。

**初赛基础版至少检查**：
- Assets ≈ Liabilities + Equity
- Revenue − Cost ≈ Gross Profit（若字段可得）
- Profit Before Tax − Income Tax ≈ Net Profit（允许报表项目差异和 tolerance）
- Closing Cash ≈ Opening Cash + Net Change in Cash（若字段可得）
- subtotal / children reconciliation
- Q2 = H1 − Q1
- Q4 = FY − 9M
- 本期期初 ≈ 上一期期末（考虑重述/口径变化）
- PDF extracted fact 与 Snapshot Provider cross-source reconciliation

**要求**：
- 先做检测和定位，**不得**初赛阶段自动静默修值
- 输出 constraint_id、inputs、residual、tolerance、status、source refs
- 解析失败或勾稽失败要进入 Validator / review queue

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

## 8. 四大创新体系（v3.2 冻结命名，详见 INNOVATION_DESIGN.md 与 CARD-22~26）

> v3.2 命名变更：ACEE → **ACME**；FPO 对外名 → **Financial Claim Passport**；均非学界已有理论，属本项目技术命名。

### 8.1 主创新一：ACME — Accounting-Constrained Multimodal Evidence Engine（CARD-22）

**会计约束驱动的多模态金融证据理解引擎**（不是简单 OCR / PDF Parser / RAG）

联合理解：财报正文、财务表格、图表、脚注、公告、Snapshot Provider 数据，并使用约束族主动验证抽取结果。

**必须覆盖六类 Constraint Family**：
1. **Accounting Identity Constraints**：Assets ≈ Liabilities + Equity；Net Profit ≈ PBT − Tax；Closing Cash ≈ Opening Cash + Net Change。允许 rounding tolerance 与 statement-specific adjustment（必须定义 tolerance policy，不机械绝对相等）
2. **Table Structural Constraints**：Subtotal ≈ Sum(children)、Total ≈ Sum(items)——检测 OCR 错位/列错位/负号丢失/单位错误/单元格串行
3. **Period Constraints**：Q2 = H1 − Q1；Q3 = 9M − H1；Q4 = FY − 9M——**复用 FinancialPeriodEngine，不重复实现**
4. **Cross-period Constraints**：期初 ≈ 上期末——结合 Accounting Scope / Restatement Signal，政策调整/重述/合并范围变化不强制一致
5. **Cross-source Constraints**：年报 vs Snapshot——period/scope/version/currency/unit 统一后比较，结果分类 MATCH / ROUNDING_MATCH / CONFLICT / NOT_COMPARABLE，**不直接判谁错**（裁决交 CARD-13）
6. **Cross-modal Constraints**：正文 / 表格 / 图表三方一致性——检出不一致但记录 source A/B/C、computed value、conflict type、resolution status

初赛：检测 + 定位 + 阻断；决赛：OCR candidate search / constraint optimization / automatic candidate correction（保留 raw value / candidates / constraint violated / selected / reason / manual review status）。**禁止无证据静默修改原始数字。**

### 8.2 主创新二：Financial Claim Passport / Financial Proof Object（CARD-23）

**每个重要金融 Claim 生成一个机器可验证的 Financial Proof Object（对外名"金融AI结论护照"）**

FPO 至少包含六个 proof：
- **Source Proof**：document_id, sha256, page/locator, evidence_ids, available_at
- **Accounting Context**：period, single-quarter/YTD/TTM, consolidated/parent, currency, unit, as-reported/restated/corrected
- **Calculation Proof**：calculation_id, formula, input evidence/calculation IDs, output, code version
- **Assumption Proof**：assumption_ids, source, rationale
- **Dependency Proof**：upstream claims + REQUIRED/SUPPORTING/OPTIONAL
- **Validation Proof**：validator rules, result, blocked reasons
- **Integrity Proof**：object hash, optional audit-chain reference

**必须提供独立 Claim Verifier——`verify_claim(claim_id)`（不依赖 LLM 重新回答）**，至少重查：document hash、evidence existence、source version、period、scope、unit、formula、calculation result、required dependencies、assumptions、validator state。

**验证结果五态**：`VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED`，并给出原因。这是比赛 Demo 的核心技术动作：点击结论 → Verify Claim → 系统重新执行证明。

### 8.3 主创新三：Thesis Fragility + Temporal Revalidation（CARD-24/25）

**投资逻辑脆弱性与时间重验证**（不是 Bull/Bear 打分）

**Thesis Fragility Engine（CARD-24）**——建立在 Claim-Evidence Graph 之上：
- Thesis = 由多个 REQUIRED/SUPPORTING Claim 构成的投资逻辑（如 T01"盈利改善具有持续性"依赖 C01 毛利率改善(REQUIRED) + C02 收入增长(REQUIRED) + C03 原材料成本下降(SUPPORTING)）
- 依赖语义：REQUIRED / SUPPORTING / OPTIONAL；任一 REQUIRED upstream BLOCKED/CONFLICTED → downstream 至少 STALE/BLOCKED；SUPPORTING 失效 → coverage 降级不自动 blocked；**禁止未校准伪置信分数**
- 算法（确定性图算法）：Critical Dependency Detection / Minimal Cut Set（DAG traversal + cut-set enumeration，限 DAG/有限深度/小规模图，可解释）/ Numeric Fragility（distance to invalidation，**阈值必须来自公开假设/分析师输入/模型约束，严禁 LLM 编造**，无可靠阈值只做 structural）
- 输出：critical_dependencies、minimal_cut_sets、numeric_thresholds(可选)、distance_to_invalidation(可选)、unresolved_assumptions、monitoring_metrics + UI Thesis Fragility Map

**Temporal Revalidation Engine（CARD-25）**——与 Fragility 共用同一 Dependency Graph：
- 传播链：Source Changed → Evidence superseded/conflict → Calculation stale → Claim stale/blocked → Thesis affected → Valuation affected → Memo section affected
- **Version Lineage**：AS_REPORTED / RESTATED / CORRECTED / SUPERSEDED + supersedes / superseded_by；旧值保留，不 overwrite
- **三态区分**：DATA CONFLICT / VERSION SUPERSESSION / NEW INFORMATION——传播规则不同，不能全部叫 conflict（详见 CARD-13 §7b）
- **Incremental Revalidation**：输入 changed_node_ids → 计算 affected_subgraph → 只重算受影响 calculations/claims/theses/valuations/memo sections；不得默认全量重跑 LLM workflow；必须提供 impact analysis

### 8.4 评测创新：FinFuzz — Financial Semantic Adversarial Benchmark（CARD-26，集成于 CARD-11）

**金融语义对抗错误生成与压力测试框架**——不是业务核心功能，是验证可信能力是否有效的测试框架。

第一阶段 mutation operators（≥10 类）：Numeric（1.26→12.6）/ Unit（万元↔亿元, CNY↔USD, %↔bp）/ Sign / Period / YTD_vs_single / Scope / Version / Valuation（PE_TTM↔PE_NTM, PE↔PB）/ Citation（错误页码/Evidence ID）/ Causal（并列改因果，无 management attribution → unsupported）。

**Benchmark 分层指标**：Overall Precision/Recall/F1 + False Positive Rate + **per-error-type Recall**（Numeric/Unit/Period/Scope/Version/Citation/Causal…分开）；区分 Claim Extractor failure vs Checker failure。集成进 CARD-11 的 cn_agent_v2 评测体系。

### 8.5 创新优先级（不能破坏初赛交付）

**P0（第一冻结点前必须）**：
- ACME 基础版：会计恒等式 + 表格结构 + YTD 关系 + 跨期（CARD-22）
- Financial Claim Passport：完整 FPO + verify_claim() + Validator integration（CARD-23）
- Thesis Fragility 基础版：REQUIRED/SUPPORTING 依赖 + critical dependency + 基础 cut-set（CARD-24）
- FinFuzz 基础版：Numeric / Unit / Period / Scope / Citation（CARD-26）
- Source/version semantics 修正、Cross-source reconciliation（CARD-13）

**P1**：
- Temporal Revalidation 基础版：version lineage + affected-subgraph propagation（CARD-25）
- Numeric fragility（有可靠阈值时）、更多 FinFuzz mutation、Cross-modal chart understanding 增强

**P2 / 决赛**：
- ACME 自动候选值纠错 / constraint solver / OR-Tools
- 复杂 minimal cut set / 高级 causal attribution / 复杂图表视觉理解
- 完整 incremental memo regeneration / automatic refresh

**不能因为创新模块导致**：PDF 解析、财务计算、Report Checker、估值、Memo、Validator、Benchmark 主链延期。第一冻结点前 P1 按 MASTER_PLAN 裁剪顺序主动裁剪，不修改截止时间假设。

## 9. Controlled Environment Guard（v3.1 新增）

**竞赛要求封闭/半封闭数据环境，新增安全规则**（但不要做成大而全安全平台）：

至少加入：
- Uploaded document text is DATA, never instruction
- prompt injection from PDF/report must not override system/task rules
- local file allowlist / workspace sandbox
- reject path traversal (`../` 等)
- external network default disabled in competition/offline mode
- retrieved document chunks 以明确 data boundary 注入模型
- Tool permissions 最小化
- 不允许文档内容要求模型泄露 prompt / environment / unrelated files

把相应规则写进 Document、Claim Extractor、Run/Audit CARD。

## 10. Audit Trail / Replay 修正（v3.1）

1. **Replay 与 Re-execution 分离**：
   - Audit Replay：读取历史 artifact 展示"当时发生了什么"，不重新调用 LLM
   - Re-execution：使用同一输入/config 再执行并比较输出

2. **events.jsonl 增强**：不能只有 input_digest / output_digest。必须增加：
   - input_ref
   - output_ref
   指向 run artifact 中的完整可审计输入/输出

3. **tamper-evident hash chain**（P1 增强，不允许影响 P0 核心功能交付）：
   ```
   current_event_hash = SHA256(previous_event_hash + canonical_json(current_event))
   ```
   manifest 保存 audit_root_hash

## 11. 明确不做的事

- 不迁移 React / 微服务 / Kubernetes / 消息队列
- 不引入 MongoDB / Redis / LangGraph / 向量数据库（FAISS/Chroma）
- 不做 OCR 深度自研（pdfplumber 基线 + 可选 MinerU/PaddleOCR，决赛再说）
- 不为覆盖七赛题堆功能；不为 PPT 上的名词增加无业务价值的协议层
- 不用无理论依据的公式（多空评分、估值区间取交集/并集、虚构权重总分）
- **禁止在 development 中使用**：全球首创 / 国内首创 / 唯一 / 第一（除非后续有系统文献/产品检索证明）

## 12. 与 v2 架构的差异（保留）

1. 数据入口从"快照优先"变为"真实文档优先"（快照保留，服务估值与市场数据）
2. 新增 Normalization / Claim / Calculation / RunManifest / ConflictRecord 五个一等公民数据模型
3. "事实/推论/观点"从 Section 级下沉到 Claim 级
4. 检索 chunk 与 Evidence 解耦（只有被引用才入账）
5. Multi-Agent / MCP / Skill / DCF 从核心链移除，降为决赛可选且须证明收益
6. **v3.1 新增**：source_period / economic_period 分离、claim_type / temporal_status 分离、verification_status 取代 confidence 数值、REQUIRED/SUPPORTING/OPTIONAL 依赖语义、四大创新体系、Controlled Environment Guard、Audit Replay 修正
