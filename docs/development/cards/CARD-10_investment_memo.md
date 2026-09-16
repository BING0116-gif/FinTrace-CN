# CARD-10: Investment Memo（买方投资备忘录）

| 属性 | 值 |
|---|---|
| 优先级 | P0 |
| 竞赛阶段 | 初赛版（10/7–10/11） |
| 对应赛题 | 赛题6 最终业务输出 |
| 依赖 | CARD-03（财务分析）、05（纠错）、06（检索）、08（估值）、09（图谱）——**不依赖 Multi-Agent** |
| 实现复杂度 | 中高（约 4–5 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/memo.py`：从主链各模块产物组装结构化买方备忘录（11 段），markdown + JSON 双输出，每个数字经 Claim-Evidence Graph 可回溯，逐句标注事实/推论/观点。**已解除 v2 对 Multi-Agent 的强依赖**——单 Agent 主线即可产出。

## 2. 对应竞赛评分点

赛题6 全部考察点：投资逻辑、事实依据、风险因素、反向验证条件、持续跟踪指标的完整性。

## 3. 为什么需要这个模块

备忘录是全系统的最终交付物与 Demo 主角的载体；v2 版本绑死 Multi-Agent（决赛才做）导致初赛无法交付，本卡解耦。

## 4. 输入 / 输出

- **输入**：`AnalysisResult`（CARD-03）、`ValuationResult`（CARD-08）、`Finding[]`（CARD-05，草稿核查场景）、`SearchHit[]` 引用（CARD-06）、`ClaimGraph`（CARD-09）、风险信号
- **输出**：`InvestmentMemo`（结构化 + markdown 渲染）

## 5. 数据模型

```python
@dataclass
class MemoSection:
    section_id: str    # executive_summary | company_overview | financial_performance
                       # | investment_thesis | valuation | catalysts | risks
                       # | counter_thesis | falsification | tracking_kpis | evidence_appendix
    tier_marking: list[dict]   # 逐句标注 [{sentence_span, claim_id, claim_type}]
    body_markdown: str
    evidence_ids: list[str]
```

**关键升级（对 v2）**：事实/推论/观点标注从 Section 级下沉到**句子级**（每个 claim_id 对应 Claim-Evidence Graph 节点）。

## 6. API / Tool Contract

```python
def build_memo(analysis, valuation, findings, hits, graph) -> InvestmentMemo: ...
def render_memo_markdown(memo) -> str: ...
def render_memo_json(memo) -> dict: ...

# 叙述段 LLM 输出契约（句子级标注机制，v3.0 原方案缺失）
def _build_memo_prompt(section_name, analysis_dict, valuation_dict, existing_claim_ids: set) -> str:
    """注入：结构化分析/估值/信号 + 已存在 Claim ID 白名单。
    LLM 只能引用白名单中的 claim_id，禁止自造新 id。"""

# LLM 输出结构化 schema：
# [{sentence_span: str, claim_id: str | None, claim_type: "fact" | "inference" | "opinion",
#   derived_from: list[str] | None, assumption_note: str | None}]
# 每条必须携带原句逐字文本；claim_id 必须在 existing_claim_ids 中（或 None）
# 数值句必须引用已存在的 calculation_id

def _validate_memo_segment_output(llm_json, existing_claim_ids: set) -> None:
    """硬校验：
    - 每条 sentence_span 非空
    - 每条 claim_id ∈ existing_claim_ids 或为 None
    - fact 句 claim_id 非空 且 claim_type=fact
    - inference 句 claim_type=inference 时 derived_from 非空
    - 数值句必须带 calculation_id
    违反 → 该条重生成或剔除，不写入 memo。"""
```

Agent 工具 `GenerateCnInvestmentMemoTool`：入参 `symbol 或 document_id`；出参 `status / memo`。数值段（financial_performance / valuation / tracking_kpis）由确定性模板渲染；叙述段（thesis / risks / counter_thesis / catalysts）由 LLM 生成但**只能引用已注入 prompt 的结构化 claims**（白名单断言），输出数值由 unverified_number 检查拦截。

## 7. 金融逻辑（11 段与赛题6 考察点映射）

| 段 | 赛题6 考察点 | 数据来源 |
|---|---|---|
| Executive Summary | 投资逻辑摘要 | 确定性模板 + LLM 叙述（限 claims） |
| Company Overview | 事实依据 | 检索引用（quote/paraphrase 型） |
| Financial Performance | 事实依据 | CARD-03 指标表（fact） |
| Investment Thesis | 投资逻辑 | CARD-03 信号 → inference 标注 |
| Valuation | 假设与边界 | CARD-08（假设清单 + 适用边界） |
| Catalysts | 投资逻辑 | 检索 + LLM（opinion 标注） |
| Risks | 风险因素 | 诊断信号 + 双向列示 |
| Counter-thesis | 反向验证 | 与 thesis 对立的证据链（防单视角） |
| Falsification | 反向验证条件 | 可证伪指标（阈值 + 计算方式） |
| Tracking KPIs | 持续跟踪指标 | 确定性生成（背离信号阈值、估值分位线、下期报告日） |
| Evidence Appendix | 事实依据 | 全部证据清单（页码可跳） |

免责与边界：模板固定渲染"不构成投资建议"与适用边界声明。

## 8. Edge Cases

1. 任一上游缺失（如无估值数据）→ 对应段标 data_unavailable，不编造
2. LLM 叙述段输出数值 → unverified_number 拦截，该句重写或剔除
3. assumption_only 数据 → 整体警示横幅（承袭 data_grade 机制）
4. 草稿核查场景 → 备忘录引用纠错结果，注明"草稿中 X 处陈述与事实不符"
5. Counter-thesis 找不到对立证据 → 明示"未发现显著反向证据"（如实陈述，不硬凑）

## 9. Failure Mode

上游链路有 blocked claim → 备忘录对应结论标注 blocked 并在 Validation 段说明——**备忘录不掩盖系统的不可知**。

## 10. Validator Rules

- 逐句 claim 标注完整（无标注句拒绝渲染）
- fact 句 100% 绑定证据；数值句 100% 绑定 Calculation 或 Evidence
- quote 引用逐字校验（CARD-06 联动）
- Falsification 段必须含可计算阈值（禁止"持续关注基本面"空话）

## 11. Unit Tests

三段式好/缺数据/失败注入场景的渲染正确性；逐句标注完整性；unverified_number 拦截；免责声明存在性。

## 12. Integration Tests

全主链 → memo → 每个数字抽检回溯 PDF 页（自动化测试：随机抽 10 个数值，claim 图 trace 可达）。

## 13. Benchmark

Numeric Accuracy / Evidence Coverage（memo 级）接入 CARD-11。

## 14. Demo Method

Demo 第 3.5 分钟：生成备忘录 → 点击结论 → 图谱回溯（CARD-09）→ 落到 PDF 页。

## 15. 验收标准

- [ ] 11 段齐全、逐句三级标注、双格式输出一致
- [ ] 数值 100% 可回溯（自动化抽检测试）
- [ ] 无 Multi-Agent 依赖（单 Agent 主线可跑）
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
