# CARD-06: 报告纠错引擎（checker.py）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段1 / P0 |
| 对应选题 | 选题5 研究报告纠错核查 |
| 依赖 | 无，可独立开工 |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/checker.py`：输入结构化报告草稿（claims 列表），对照快照事实核查数值、单位、期间口径、引用与同比计算，输出带严重级、证据定位与修改建议的 findings 清单。**纯规则引擎，零 LLM**——这是本项目相对其他参赛队最大的差异化卖点。

## 2. 竞赛考察点映射

| 选题5考察点 | 本卡落点 |
|---|---|
| 错误识别准确性与覆盖率 | 五类核查规则 + 固定评测集量化 |
| 误报控制 | 确定性规则 + 单位换算容差设计 |
| 来源定位 | 每条 finding 带 evidence_id 与快照路径 |
| 修改建议可执行性 | suggestion 字段给出修正后的正确值 |

## 3. 设计

### 3.1 输入契约（ReportDraft）

```python
@dataclass
class DraftClaim:
    claim_id: str
    field: str              # 如 "营业收入" / "市盈率" / "同比增速"
    value: float | str
    unit: str               # 元 / 万元 / 亿元 / 倍 / %
    period: str | None      # 报告期 key；估值类可为 None
    evidence_id: str | None # 草稿声称的引用
    context: str            # 原文句子（定位展示用）
```

说明：真实研报是自然语言，claims 提取（哪个模块从文本抽数字）属于后续增强；本卡先定义结构化输入契约，评测集与工具都以它为准。文本→claims 的抽取可由 LLM 辅助完成，但**抽取结果必须逐条可核、且核查本身仍是确定性规则**（LLM 只做搬运不做判定）。

### 3.2 核查规则（五类）

```python
class CheckType(str, Enum):
    value_mismatch    # 数值与快照不符（含单位换算后比对，容差仅限浮点显示位数）
    unit_error        # 数值正确但单位错（如快照"亿元"、草稿写"万元"量级数字未换算）
    period_mismatch   # 报告期口径错配（草稿引用 FY2024 数值但标注 FY2023）
    missing_evidence  # 引用的 evidence_id 不存在于账本
    calc_error        # 同比/环比/估值倍数复算不一致（复算走 CARD-04 同源函数，不重写公式）

@dataclass
class Finding:
    claim_id: str
    check_type: CheckType
    severity: str            # error | warning
    expected: str            # 快照正确值（含单位与期间）
    actual: str
    evidence_id: str          # 定位到快照事实
    suggestion: str           # 可执行修改建议
```

### 3.3 引擎入口

```python
def check_report_draft(claims: list[DraftClaim], snapshot) -> list[Finding]:
    """五类规则全跑；返回按 severity 排序的 findings。"""

def summarize_findings(findings) -> dict:
    """各类型计数 + error/warning 总数，供评分与展示。"""
```

单位换算核心纪律：比对前把草稿值按其声明单位换算到快照单位；换算后差异 > 容差才报 value_mismatch；数字量级恰好差 10^4/10^8 且草稿单位与快照单位不同 → 报 unit_error 而非 value_mismatch（这是误报控制的关键规则）。

### 3.4 固定评测集（误报率/覆盖率的量化基础）

`tests/fixtures/report_drafts/` 下构造 JSON 草稿集，每份含已知 planted errors：

| 文件 | 内容 | 预期 |
|---|---|---|
| good_draft.json | 全部正确 | findings 为空 |
| value_errors.json | 3 处数值错 | 3 条 value_mismatch |
| unit_errors.json | 2 处单位错 | 2 条 unit_error（非 value_mismatch） |
| period_errors.json | 1 处期间错配 | 1 条 period_mismatch |
| missing_evidence.json | 2 处引用不存在 | 2 条 missing_evidence |
| calc_errors.json | 2 处同比算错 | 2 条 calc_error |

### 3.5 工具注册

`CheckCnReportDraftTool`（`cn_tools.py`）：
- 入参：`symbol` + `draft`（claims 数组）
- 出参：`status / findings / summary`；快照缺失 → error 信封

## 4. 实施步骤

1. 通读 `evidence.py` 账本接口与快照财务结构，确定核对数据源。
2. 实现 `DraftClaim/Finding` 与五类规则；复算同比走 CARD-04 函数（若未完成则本卡内先实现私有 `recompute_yoy` 并标注"待切换 CARD-04 同源函数"）。
3. 构造六份评测集（基于一份 illustrative 快照的真实数值生成 planted errors，正确值记录在 fixture 的 expected 段）。
4. 写 `tests/test_cn_checker.py`：命中率 100%、误报率 0（good_draft 必须零 finding）。
5. 注册工具 + 契约测试；端到端样例贴执行备注。

## 5. 验收标准

- [ ] 六份评测集全部达预期：命中率 100%，good_draft 零误报
- [ ] 单位换算规则测试（亿元↔万元↔元互转、量级错配判 unit_error）
- [ ] 全部 findings 带 evidence_id 与 suggestion；零 LLM 调用（测试断言无网络/mock 缺席也通过）
- [ ] 工具契约测试通过；全部测试通过

## 6. 红线（本卡特有）

- 纯确定性规则引擎；绝不引入 LLM 判定对错
- 容差只允许浮点显示位级别（如 0.5% 以内的舍入差），禁止为凑命中率放宽
- 评测集 planted errors 的正确值必须可追溯到快照具体字段（写入 fixture 注释）

## 7. 执行备注（agent 填写）

| 日期 | 记录（规则补充 / 容差决定 / 偏差） |
|---|---|
|  |  |
