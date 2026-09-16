# CARD-23: Financial Claim Passport & Proof Verifier（金融AI结论护照 / 财务证明对象）

| 属性 | 值 |
|---|---|
| 优先级 | P0（第一冻结点前） |
| 竞赛阶段 | 初赛版（10/7–10/11） |
| 对应赛题 | 北京赛：全链路证据可核验（创新二）；华北五省：Trustworthy AI / Proof-Carrying Computation |
| 依赖 | CARD-09（Claim-Evidence Graph）、CARD-07（Run Manifest）、CARD-13（版本状态） |
| 实现复杂度 | 中（约 4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

> 本卡前身：v3.1 的 "Financial Proof Object / Verifier (PCIR)"。v3.2 正式命名为 **Financial Claim Passport（对外名称"金融AI结论护照"）**，底层技术对象仍为 Financial Proof Object（FPO），并**新增独立 `verify_claim()` 五态验证接口**——这不是普通 Citation，而是让一个金融 Claim 能够被追溯、重新计算、重新验证、判断是否仍然有效。

## 1. Objective（目标）

新建 `src/cn/proof/`：为每个重要金融 Claim 生成机器可验证的 **Financial Proof Object（FPO / 结论护照）**，并提供**独立于 LLM** 的 `verify_claim(claim_id)` 验证接口。一个 FPO 必须让一个金融 Claim 能够被：**追溯、重新计算、重新验证、判断是否仍然有效**。

## 2. Competition relevance（双赛分别解决什么评审问题）

| 比赛 | 解决的评审问题 |
|---|---|
| 华北五省计算机设计大赛 | 展示 **Proof-Carrying / Trustworthy AI**：点击一条结论 → 展示完整证明对象（Claim→Calculation→Evidence→PDF 页→假设→依赖）→ 点击 VERIFY → 系统**脱离 LLM 重新执行证明**，输出五态结果 |
| 北京市大学生金融人工智能竞赛 | 回答"证据可核验 / 结果可复现"：每条结论不是"LLM 说它来自第几页"，而是可独立重算、可判定有效性的机器证明对象 |

## 3. Why this is not a gimmick（为什么不是点缀）

普通 RAG / Chatbot / Citation 只能提供"引用来源"——"这句话来自第 45 页"，无法回答：数字对不对？公式是什么？依赖证据还有效吗？假设条件是什么？FPO 提供的是**完整证明链 + 可独立执行的验证器**：

- 普通 Citation：`claim → source page`（引用）
- FPO：`claim → source_proof + calculation_proof + assumption_proof + dependency_proof + validation_proof + integrity_proof`（证明），且 `verify_claim()` 能**重新检查全部依赖与重算结果**并给出离散状态（VERIFIED/DEGRADED/STALE/BLOCKED/CONFLICTED）

## 4. Inputs / 5. Outputs

- **输入**：`Claim` + `Calculation[]` + `Evidence[]`（CARD-09）、`Assumption[]`（CARD-08）、`RunManifest`（CARD-07）、版本谱系（CARD-13/25）
- **输出**：`FinancialProofObject`（护照）+ `VerificationResult`（验证结果，五态）

## 6. Data Models（数据模型——FPO 至少包含的部分）

```python
@dataclass
class FinancialProofObject:
    # --- Claim 本体 ---
    claim_id: str
    claim_type: str              # fact | inference | opinion
    claim_text: str
    economic_period: str         # 如 "2025Q2"
    scope: str                   # consolidated | parent
    version_status: str          # AS_REPORTED | RESTATED | CORRECTED | SUPERSEDED

    # --- Source Proof（来源证明）---
    source_proof: dict = {}      # {document_id, sha256, page, locator, evidence_ids, available_at}
    accounting_context: dict = {}  # {period, single_quarter|ytd|ttm, consolidated/parent, currency, unit, as_reported/restated/corrected}

    # --- Calculation Proof（计算证明）---
    calculation_proof: dict = {} # {calculation_id, formula, formula_version, inputs[{ref,value}], output, code_version}

    # --- Assumption Proof（假设证明）---
    assumption_proof: dict = {}  # {assumption_ids[], sources[], rationale}

    # --- Dependency Proof（依赖证明）---
    dependency_proof: dict = {}  # {upstream_claims[{role: REQUIRED|SUPPORTING|OPTIONAL, target_id}], dependencies[]}

    # --- Validation Proof（验证证明）---
    validation_proof: dict = {}  # {validator_rules[], result, blocked_reasons[]}

    # --- Integrity Proof（完整性证明）---
    integrity_proof: dict = {}   # {object_hash, audit_chain_ref, run_id, git_commit}

@dataclass
class VerificationResult:
    proof_id: str
    overall_status: str          # VERIFIED | DEGRADED | STALE | BLOCKED | CONFLICTED
    status_reasons: list[str]    # 逐条原因
    checks: list[dict]           # [{check: str, status: str, message: str}]
    verify_source_version: str   # 验证器版本（代码版本）
    verified_at: str
```

**五态定义（必须与依赖传播联动）**：

| 状态 | 含义 | 触发示例 |
|---|---|---|
| VERIFIED | 全部证明项通过 | 来源/期间/单位/公式/依赖全部有效 |
| DEGRADED | 有非阻断项失效 | SUPPORTING 证据缺失；页码模糊但可解析 |
| STALE | 数据过期待刷新 | 上游 evidence 被 superseded、period 更新、新 snapshot 进入 |
| BLOCKED | 关键证明项失败 | REQUIRED 依赖 blocked；document_hash 失效；公式重算不一致 |
| CONFLICTED | 证据冲突未决 | 同期间同口径出现冲突值且 CARD-13 未裁决 |

## 7. Algorithms（算法）

**verify_claim(claim_id) 至少重新检查**（全部确定性，不调用 LLM）：
1. document hash（重新计算输入文档 sha256 比对）+ evidence existence（evidence_id 是否仍存在且 active）
2. source version（版本状态是否 superseded / restated → STALE）
3. period 一致性（economic_period 与 inputs period 一致）
4. scope 一致性（consolidated/parent 一致）
5. unit 一致性（unit/currency 一致）
6. formula + calculation result（按公式用 inputs 重算，比对 deterministic_output，容差内视为通过）
7. required dependencies（上游 REQUIRED claim/evidence 状态 → 未通过则 BLOCKED）
8. assumptions 有效性（assumption 是否仍有效/过期）
9. validator state（当前 validator 规则下 claim 是否 supported）

**状态合并规则**：任一 REQUIRED 项 BLOCKED → 整体 BLOCKED；任一证据 superseded/stale → STALE；存在未决 conflict → CONFLICTED；非阻断 warning → DEGRADED；全部通过 → VERIFIED。

## 8. API / Tool Contract

```python
# src/cn/proof/passport.py
def build_financial_proof_object(claim_id, run_id) -> FinancialProofObject: ...
def verify_claim(claim_id) -> VerificationResult: ...   # ★ 核心：不依赖 LLM 重新回答
def verify_fpo(fpo: FinancialProofObject) -> VerificationResult: ...  # 复用 verify_claim 内部检查项
# 检查函数（verify_claim 内部逐项）
def verify_source(...) -> dict: ...
def verify_period(...) -> dict: ...
def verify_scope_unit(...) -> dict: ...
def verify_calculation(...) -> dict: ...
def verify_dependencies(...) -> dict: ...
def verify_assumptions(...) -> dict: ...
def verify_validator_state(...) -> dict: ...
```

Agent 工具 `VerifyCnClaimTool`：入参 `claim_id`；出参 `status / passport / verification_result`。

## 9. Deterministic vs LLM boundary（确定性与 LLM 边界）

- `verify_claim()` **零 LLM**——全部项为确定性检查与确定性重算
- LLM 曾做的：生成 Claim 的文本解释（passport 只引用 claim_text）
- 明确契约：验证结果**不得**被 LLM 修改；UI 可让 LLM 解释失败原因，但状态本身由验证器产生

## 10. Dependencies（依赖）

CARD-09（Claim/Calculation/Evidence + 依赖语义）、CARD-07（run manifest / audit chain 引用）、CARD-13 + CARD-25（版本谱系与超期状态 → STALE/CONFLICTED）、CARD-08（assumption registry）。

## 11. Failure Modes

- FPO 构建失败 → claim 标记 `proof_build_failed`，不阻断其余
- 验证失败 → 如实返回 BLOCKED，不降标通过
- 校验器自身 bug → 版本化 verify_source_version + 单测覆盖，不允许"验证器永远通过"

## 12. Edge Cases

1. 纯 fact 无 Calculation → calculation_proof 空，该检查 PASS（跳过）
2. 非 opinion 无 Assumption → assumption 检查 PASS
3. 孤儿 Claim（evidence 缺失）→ source 检查 BLOCKED
4. 计算输入缺失 → calculation 检查 BLOCKED
5. 上游 REQUIRED 依赖 blocked → dependency 检查 BLOCKED → 整体 BLOCKED
6. 新公告使 evidence superseded → STALE（不是 BLOCKED——还有历史价值）
7. proof_hash 重算失败 → integrity 标记 invalid

## 13. Validator Rules

- 每个 passport 的 proof_hash 可重算验证（断言）
- verification_result.overall_status 与各子项一致（合并规则有单测）
- BLOCKED/CONFLICTED 的 claim **不得进入最终 Memo 的结论段落**（Validator 遍历检查）；STALE 只允许带显式"待刷新"标注

## 14. Unit Tests

- passport 构建（fact/inference/opinion 各一例）
- verify_claim 五态各一例（VERIFIED/DEGRADED/STALE/BLOCKED/CONFLICTED）
- 各检查函数正反例（source/period/scope/unit/calculation/dependency/assumption/validator）
- proof_hash 稳定性；状态合并规则表驱动测试

## 15. Integration Tests

CARD-09 → CARD-23 全链；验证 supersession 后 verify_claim 返回 STALE（与 CARD-25 联动）；冲突未决返回 CONFLICTED（与 CARD-13 联动）。

## 16. Benchmark

**指标（接入 CARD-11，带 ablation）**：
- FPO Verification Pass Rate
- **Ablation**：`citation only` vs `FPO verifier`，比较 unsupported claim detection / stale claim detection / calculation reproducibility
- Orphan Claim Rate / Evidence Coverage
**测试集**：Synthetic + Real（人工标注 verification failures）。目标值待冻结，禁止编造。

## 17. Demo Flow

Demo 步骤 7b（DEMO_FLOW.md）：点击一条核心 Claim → 展示 Financial Claim Passport（完整证明链）→ 点击 **VERIFY CLAIM** → 系统脱离 LLM 重新验证 → 展示五态结果（VERIFIED 绿色通过，或注入 supersession 后变 STALE）。

## 18. Acceptance Criteria（验收标准）

- [ ] verify_claim() 零 LLM（代码断言：验证路径无模型调用）
- [ ] 五态各有一例测试通过
- [ ] proof_hash 稳定性与可重算性测试
- [ ] BLOCKED/CONFLICTED 不得进入 Memo 结论段（Validator 断言）
- [ ] ablation"citation only vs FPO verifier"可运行出真实数字
- [ ] 全部测试离线通过

## 19. Priority

**P0**（第一冻结点前必须：完整 FPO + verify_claim + Validator integration）

## 20. Competition Stage

初赛基础版；决赛增强：advanced visualization（证明链图）、批量验证面板。

## 21. Estimated Complexity

约 4 人日。

## 22. Fallback / Degradation Strategy

- 时间不足：verify_claim 先实现最小集（source/calculation/required-dependency 三项），其余检查标记 `not_checked`
- demo 彩排若五态场景太多，保留 VERIFIED / BLOCKED / STALE 三态演示即可，CONFLICTED/DEGRADED 答辩补充
- 断网不影响（全部本地确定性）

## 23. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |