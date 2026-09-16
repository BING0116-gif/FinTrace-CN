# CARD-04: Accounting Scope & Restatement Detection（会计口径与重述检测）

| 属性 | 值 |
|---|---|
| 优先级 | P1（初赛窗口内完成） |
| 竞赛阶段 | 初赛版（9/23–9/29） |
| 对应赛题 | 赛题2（会计口径变化识别）/ 赛题5（scope_error） |
| 依赖 | CARD-01（文档解析）、CARD-02（version 标注） |
| 实现复杂度 | 中（约 3 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

新建 `src/cn/analysis/scope_signals.py`：从文档中检测会计口径变化与重述信号，绑定原始 Evidence，并在存在口径变化时**阻断直接同比 / 使用调整后比较数据 / 输出可比性警告**。不再假设 periods.py 能解决口径问题。

## 2. 对应竞赛评分点

金融专业性（口径意识是专业评委必考）、数据准确性（重述数据误用是典型错误）、分析逻辑。

## 3. 为什么需要这个模块

真实披露中"原披露→更正公告→重述"很常见；v2 方案对此完全失明，会在旧值上计算同比并输出错误结论——这在赛题5 的 scope_error 检查中也会漏报。

## 4. 输入 / 输出

- **输入**：`ExtractedFact[]` + 文档段落（更正公告文本、年报附注"会计政策变更"章节）
- **输出**：`AccountingScopeSignal[]` + 可比性决策

## 5. 数据模型

```python
class ScopeSignalType(str, Enum):
    restated                       # 重述
    accounting_policy_change       # 会计政策变更
    prior_period_error_correction  # 前期差错更正
    consolidation_scope_change     # 合并范围变化
    comparable_period_adjusted     # 可比期间已调整
    unknown                        # 无法判定

@dataclass
class AccountingScopeSignal:
    signal_type: ScopeSignalType
    company: str
    periods_affected: list[str]
    evidence_ids: list[str]        # 必须绑定原始 Evidence（更正公告段落/附注页）
    detected_at: str
    detector_rule: str             # 触发规则说明
```

## 6. API / Tool Contract

```python
def detect_scope_signals(facts, documents) -> list[AccountingScopeSignal]: ...

def comparability_decision(signal: AccountingScopeSignal) -> str:
    """返回 'block_yoy' | 'use_adjusted' | 'warning'：
    - prior_period_error_correction + 有更正后数据 → use_adjusted
    - restated 且比较数据可得 → use_adjusted（用重述后比较值）
    - consolidation_scope_change → warning（可比性受损）
    - unknown + 影响重大 → block_yoy
    决策规则集中在模块常量表。"""
```

Agent 工具 `DetectCnScopeSignalsTool`：入参 `document_id`；出参 `status / signals / comparability[]`。

## 7. 金融逻辑

1. 检测规则（确定性文本匹配，先读真实样例再固化关键词表）：更正公告标题模式、年报附注"会计政策变更/前期差错更正"章节、表格"调整后/调整前"双列、重述声明段落
2. use_adjusted 时比较值必须取"调整后"列（CARD-02 的 Version.CORRECTED/RESTATED）
3. LLM 不参与信号判定；关键词表外的可疑段落 → unknown 信号 + 人工复核提示

## 8. Edge Cases

1. 更正公告与原报告分属两个文档 → 跨文档信号关联（依赖 CARD-13 冲突解决时按优先级取更正值）
2. 表格同时有"调整前/调整后"两列 → 两套 facts 分别标 AS_REPORTED / RESTATED
3. 附注影响金额不重大（披露了但金额小）→ 仍出信号，severity 字段区分
4. 检测到信号但比较数据不可得 → block_yoy

## 9. Failure Mode

检测不到 ≠ 不存在：本卡输出附带"检测覆盖范围声明"（哪些规则、哪些章节）；无法判定时给 unknown 信号并阻断相关同比——**宁可阻断也不误算**。

## 10. Validator Rules

- block_yoy 期间出现百分比同比 → validator 报错（这是本卡存在的意义）
- 每个 signal 的 evidence_ids 必须可解析到文档页
- use_adjusted 的计算必须引用 Version != AS_REPORTED 的比较值

## 11. Unit Tests

合成更正公告 + 双列重述表样例：信号类型正确；use_adjusted 取调整后列；block_yoy 生效；unknown 不放行。

## 12. Integration Tests

CARD-01→02→04→03：含更正的场景下同比走调整后或被阻断，全链不产出错误百分比。

## 13. Benchmark

Scope Accuracy 指标接入 CARD-11（合成集 planted 信号识别率）。

## 14. Demo Method

财务分析页顶部出现"可比性警告"横幅，点击展开：哪个公告、哪一页、影响哪些期间、系统做了什么决策（阻断/用调整值）。

## 15. 验收标准

- [ ] 6 类信号检测各有测试用例
- [ ] 三种决策路径（block/use_adjusted/warning）全部有测试
- [ ] 信号 100% 绑定 Evidence
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
