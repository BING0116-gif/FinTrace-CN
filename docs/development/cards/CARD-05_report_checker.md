# CARD-05: Report Claim Extractor & Deterministic Checker（研报纠错系统）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（9/30–10/6） |
| 对应赛题 | 赛题5 第二核心方向 |
| 依赖 | CARD-02（规范化事实）、CARD-04（口径信号） |
| 实现复杂度 | 高（约 6–7 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-agent-evaluation、financial-data-provenance |

## 1. 目标

新建 `src/cn/checker/`：从**自然语言研报草稿**中提取结构化 Claim（LLM 仅做搬运），再用**确定性规则引擎**对照事实核查，输出 13 类错误的完整纠错报告。真实比赛不会要求用户手输 DraftClaim JSON——必须支持 Raw Report 直接输入。

## 2. 对应竞赛评分点

错误识别准确性与覆盖率、误报控制、来源定位、修改建议可执行性（赛题5 全部考察点）。

## 3. 为什么需要这个模块

v2 的 checker 只接受预结构化 claims，是演示玩具。升级后这是第二核心赛题的完整答案，且是"LLM 提取 + 确定性判定"边界的最佳展示。

## 4. 输入 / 输出

- **输入**：研报草稿（PDF/TXT/MD，经 CARD-01 ReportDraftParser 解析为带页码段落）
- **输出**：`DraftClaim[]`（中间产物）→ `Finding[]` 纠错报告 + 汇总统计

## 5. 数据模型

```python
@dataclass
class DraftClaim:
    claim_id: str
    sentence: str           # 原报告句子（逐字保留，定位展示）
    page: int | None
    metric: str | None      # revenue / net_profit / pe / growth / ...
    period: str | None
    value: float | str | None
    unit: str | None
    growth: float | None
    valuation_multiple: str | None
    source_reference: str | None   # 草稿声称的引用
    claim_type: str          # factual | valuation | causal | opinion

@dataclass
class Finding:
    claim_id: str
    check_type: str          # 见第 7 节 13 类
    severity: str            # error | warning
    original: str            # 原始值
    expected: str            # 正确值（含单位/期间）
    evidence_ids: list[str]  # 来源 Evidence
    suggestion: str          # 可执行修改建议
    confidence: float        # 确定性规则给出（见 7.3），非 LLM 自评
```

**DraftClaim.claim_type → Claim.claim_type 映射**（v3.0 原方案两套枚举不一致，现已对齐）：

| DraftClaim.claim_type | Claim.claim_type | 附加约束 |
|---|---|---|
| factual | fact | 必须绑定数值类 Evidence |
| valuation | inference | 必须有 assumption_id（目标倍数登记）或行业 Gate 判定 |
| causal | inference | 双侧必须有独立 Evidence 支撑（否则 unsupported_causal_claim） |
| opinion | opinion | 必须显式标注假设/主观判断来源 |

LLM 不得直接决定映射——映射在 DraftClaim 通过 schema 校验后由确定性代码执行（checker.py 内完成）。

## 6. API / Tool Contract

```python
# claim_extractor.py（LLM，唯一允许的 LLM 环节）
def extract_claims(draft_paragraphs, llm_client) -> list[DraftClaim]:
    """LLM 提取 metric/period/value/unit/growth/valuation_multiple/
    source_reference/claim_type；输出过 schema 校验；
    每条必须携带原句 sentence（逐字），不携带原句的提取结果丢弃。"""

# checker.py（确定性规则引擎，零 LLM）
def check_report(claims, normalized_facts, scope_signals) -> list[Finding]: ...
def summarize(findings) -> dict: ...
```

Agent 工具 `CheckCnReportDraftTool`：入参 `document_id`（草稿）；出参 `status / findings / summary`。

示例（指令原文）：输入"公司2025年实现营业收入32.6亿元，同比增长18.7%。"→ 提取 `{metric: revenue, period: FY2025, value: 32.6, unit: 亿元, growth: 18.7%}` → 确定性核对快照/文档事实。

## 7. 金融逻辑

### 7.1 13 类错误

`numeric_error`（数值不符）、`unit_error`（单位错）、`period_error`（期间错配）、`scope_error`（口径错配——依赖 CARD-04 信号）、`calculation_error`（同比/环比复算不一致，复算走 CARD-03 同源函数）、`valuation_multiple_error`（**限界：仅检"引用的可比倍数与事实不符"和"行业错配"；纯分析师目标倍数跳过并计数为 opinion——把观点当事实判错是误报源头**）、`missing_citation`（无引用）、`wrong_citation`（引用错对象）、`unsupported_citation`（引用不存在）、`wrong_page`（页码错）、`stale_citation`（引用过期数据）、`revision_superseded`（引用了被更正/重述取代的旧值）、`unsupported_causal_claim`（无证据因果断言）。

### 7.2 单位换算纪律（承袭 v2 正确设计）

比对前按草稿声明单位换算到事实单位；数字量级恰好差 10^4/10^8 且单位声明不同 → 报 unit_error 而非 numeric_error（误报控制关键）。

### 7.3 confidence 语义

确定性规则给出：精确证据匹配=1.0；期间推断匹配=0.8；需单位换算后匹配=0.9 等。规则表集中常量。**不存在 LLM 自评置信度**。

### 7.4 causal 检查

claim_type=causal 的断言（"因 A 导致 B"）→ 检查因果两侧是否均有独立证据支撑；缺任一侧 → unsupported_causal_claim（warning 级，允许观点存在但必须标注）。

## 8. Edge Cases

1. LLM 提取失败/格式非法 → 该句标记 unextracted，计入 summary（不阻塞其余句子）
2. 草稿数字四舍五入显示（32.6 vs 32.58）→ 容差仅限显示位数舍入（亿级 1 位小数），禁止放宽
3. 草稿引用的指标系统事实库没有 → missing_citation 变体（标注"无法核验"而非"错误"）
4. 同一指标多个披露版本 → revision_superseded 优先于 numeric_error
5. 研报含预测值（"预计2026年营收…"）→ claim_type=forward Looking，跳过事实核查，单独计数

## 9. Failure Mode

提取环节失败 → 明确报告"X 句未能提取"而非装作没有；核查环节无对应事实 → "无法核验"状态，与"核实为错"严格区分。**误报比漏报更伤可信度**——规则倾向保守。

## 10. Validator Rules

- finding 的 evidence_ids 必须可解析（文档型带页码）
- numeric_error 的 original/expected 必须同单位口径展示
- 任何 finding 不得由 LLM 判定产生（代码审查断言：checker.py 无 LLM import）

## 11. Unit Tests

`tests/test_cn_checker.py` + `tests/fixtures/report_drafts/`（含 planted errors 的草稿集）：
- 全部 13 类错误各有 ≥1 用例
- 好草稿零误报（命中率 100% / 误报 0 的双指标测试）
- 单位量级错配判 unit_error 不判 numeric_error
- 舍入容差边界测试
- causal 单侧证据 → warning

## 12. Integration Tests

CARD-01 草稿解析 → 提取 → 核查 → finding 跳转原 PDF 页全链路；与 CARD-11 planted 集联合计算 Checker Precision/Recall/F1/FPR。

## 13. Benchmark

Checker Precision / Recall / F1 / False Positive Rate 四指标接入 CARD-11（合成 planted 集 + 真实研草稿改造集），目标值待 baseline 后冻结。

## 14. Demo Method

上传含错研报草稿 → 纠错列表（错误类型徽章 + 原句 + 正确值 + 建议）→ 点击任一 finding 跳转原始 PDF/事实来源页。**这是 5 分钟 Demo 的核心一幕**。

## 15. 验收标准

**两级验收，避免 LLM 波动卡死卡片关闭**：

**A. 核查器级（给定正确 DraftClaim 输入——纯确定性，可 100% 保证）**：
- [ ] planted 集 13 类错误检出 100%（给定正确 DraftClaim）
- [ ] 好输入零误报（纯确定性，无 LLM 参与）
- [ ] checker.py 零 LLM import（代码结构断言）

**B. 端到端级（含 LLM Claim Extractor——自然语言草稿直接输入）**：
- [ ] 自然语言输入端到端跑通（非预结构化 JSON）
- [ ] 指标只入 CARD-11 benchmark 报告（不作本卡验收门槛）：Checker Precision / Recall / F1 / FPR
- [ ] DraftClaim.claim_type → Claim.claim_type 映射全路径验证通过
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
