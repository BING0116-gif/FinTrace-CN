# CARD-10: 买方投资备忘录（memo.py）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段3 / P0 |
| 对应选题 | 选题6 买方投资备忘录编制 |
| 依赖 | CARD-08（必须）、CARD-09（推荐，反向验证条件素材） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/memo.py`：消费多智能体轨迹（opinions + debate + risk review），生成结构化买方投资备忘录，markdown + JSON 双格式输出，全文事实/推论/观点三级标注，注册为工具并接入报告校验。

## 2. 竞赛考察点映射（选题6 原文）

| 考察点 | 备忘录段落 |
|---|---|
| 投资逻辑 | §1 投资论点（来自辩论强度占优方 + 证据链） |
| 事实依据 | §2 关键数据表（全部来自工具结果，挂 evidence_id） |
| 风险因素 | §5 风险因素（risk review 双清单） |
| 反向验证条件 | §6 反向验证（unresolved_conflicts + 可证伪指标） |
| 持续跟踪指标 | §7 跟踪指标（确定性生成：估值分位、背离信号复现等） |

## 3. 详细设计

### 3.1 备忘录结构（JSON schema 即文档）

```python
@dataclass
class MemoSection:
    section_id: str           # thesis / data / valuation / assumptions / risks / falsification / tracking
    tier: str                 # fact | inference | opinion   ← 每节强制声明
    body_markdown: str
    evidence_ids: list[str]
    source_claims: list[str]  # 引用的 AgentClaim.claim_id（推论/观点节必填）

@dataclass
class InvestmentMemo:
    symbol: str
    as_of: str
    sections: list[MemoSection]
    data_grade: str           # sourced | mixed | assumption_only（沿用 CARD-05 分级）
    generator: str             # multiagent:<run_id> | offline
```

### 3.2 生成函数

```python
def build_investment memo(trace: MultiAgentTrace, snapshot) -> InvestmentMemo:
    """组装各节：
    - data 节：确定性模板渲染关键财务/估值表（复用 report.py 渲染约定）
    - valuation/assumptions 节：CARD-05 的 DcfResult/SensitivityGrid 直接嵌入，假设表带 provenance
    - thesis/risks/falsification 节：LLM 叙述 CARD-08/09 的结构化产物，模板限制其只能引用已有 claims
    - tracking 节：规则生成（背离信号阈值、估值分位回撤线、下期报告日）
    """

def render_memo_markdown(memo: InvestmentMemo) -> str: ...
def render_memo_json(memo: InvestmentMemo) -> dict: ...
```

关键纪律：LLM 撰写节（thesis/risks/falsification）的 prompt 输入**只含结构化 claims 与证据摘要**，不含快照原始数字——其输出中任何数值都会因无对应工具来源被 `trace_validator` 拦截。数值只出现在确定性渲染的 data/valuation 节。

### 3.3 校验与工具

- `src/validation/report_validator.py` 扩展 memo 规则：每节 tier 合法、evidence_ids 存在、fact 节零 LLM 来源、跟踪指标含可计算阈值。扩展方式：先读现有 validator 结构再增量添加。
- 工具 `GenerateCnInvestmentMemoTool`（`cn_tools.py`）：入参 `symbol`（内部走编排器）；出参 `status / memo(markdown+json)`。
- workbench 增加"投资备忘录"页面/入口（复用 CARD-01 页面骨架与 CARD-02 任务系统）。

## 4. 实施步骤

1. 通读 `report.py` 的渲染与导出约定（markdown/excel），memo 渲染保持一致风格。
2. 实现 dataclass 与确定性渲染节（data/valuation/assumptions/tracking）。
3. 实现 LLM 撰写节（prompt 模板 + claims 注入 + 输出解析）。
4. 扩展 report_validator 的 memo 规则 + 测试。
5. 注册工具 + workbench 页面 + api 端点（沿用 CARD-08 的任务接入）。
6. `tests/test_cn_memo.py`：三 tier 标注完整性、fact 节数值 100% 有 evidence、离线模式 generator=offline 标注、validator 规则用例。
7. 离线端到端样例贴执行备注。

## 5. 验收标准

- [ ] 备忘录全部七个段落齐全，tier 标注正确（fact 节零 LLM 来源有测试断言）
- [ ] 全部数字字段可回溯：随机抽取 memo 中的 10 个数字，evidence_id 均有效（自动化测试）
- [ ] assumption_only 数据下 memo 带整体警示横幅
- [ ] markdown/JSON 双输出一致性测试；全部测试通过

## 6. 红线（本卡特有）

- 备忘录不是研报复刻：投资结论必须带"推论/观点"标注与适用边界，不构成投资建议的免责声明由模板固定渲染
- 跟踪指标必须可机器复核（阈值+计算方式），不得写"持续关注基本面"这类空话
- 离线生成必须标注 generator=offline

## 7. 执行备注（agent 填写）

| 日期 | 记录（渲染对接 / validator 规则 / 偏差） |
|---|---|
|  |  |
