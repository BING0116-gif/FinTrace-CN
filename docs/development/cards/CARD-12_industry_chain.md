# CARD-12: 产业链传导分析（industry_chain.py）

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段4 / P2 |
| 对应选题 | 选题3 产业链影响分析 |
| 依赖 | 无硬依赖（估值联动部分建议 CARD-05 后） |
| 状态 | ☐ 未开始 |

## 1. 目标

新建 `src/cn/industry_chain.py` + 静态产业链图谱数据：沿"原材料→中游→下游"路径量化价格/供需冲击的传导影响，输出带适用边界声明的传导分析。选题3 的差异化打法是"量化传导 + 边界声明"，不做定性泛泛而谈。

## 2. 竞赛考察点映射

| 选题3考察点 | 本卡落点 |
|---|---|
| 产业分析逻辑 | 静态图谱（上游/中游/下游节点+成本占比边权） |
| 证据完整性 | 边权成本占比必须挂来源（sourced 或 assumption 登记表） |
| 量化方法合理性 | 成本占比线性传导模型 + 敏感性 |
| 结论适用边界 | 每份输出强制附适用边界段（确定性模板） |

## 3. 详细设计

### 3.1 图谱数据（`data/industry_chains/*.json`，仓库内静态维护）

```json
{
  "chain_id": "lithium_battery",
  "name": "锂电产业链",
  "nodes": [
    {"node_id": "carbonate", "tier": "upstream", "name": "碳酸锂", "price_series_hint": "akshare_field_x"}
  ],
  "edges": [
    {"from": "carbonate", "to": "cathode", "cost_share": 0.4,
     "cost_share_provenance": "assumption: 行业公开研报口径，待替换为 sourced"}
  ]
}
```

首批维护 3 条链（锂电/光伏/消费电子），规模刻意小而精——答辩展示的是方法论而非数据量。

### 3.2 函数契约

```python
@dataclass
class ChainNode:
    node_id: str
    tier: str           # upstream | midstream | downstream
    name: str
    companies: list[str]   # 归属公司（复用 industries.py 的行业归属，先读其结构）

def load_chain(chain_id: str) -> ChainGraph: ...

def upstream_shocks(chain: ChainGraph, node_id: str) -> list[str]:
    """返回会传导到该节点的上游价格冲击源。"""

def pass_through_impact(chain: ChainGraph, shock_node: str,
                         price_change: float) -> "ImpactResult":
    """线性传导：对每个下游节点 cost = Σ(路径边权) × price_change，
    输出各节点成本变化率与利润敏感性（结合该节点毛利率假设，assumption 显式登记）。"""

@dataclass
class ImpactResult:
    path: list[str]             # 传导路径
    node_impacts: list[dict]     # {node_id, cost_change_pct, margin_impact}
    assumptions_used: list[str] # 全部假设 provenance 集合
    boundary_statement: str      # 确定性模板：适用范围/失效条件（线性假设/静态占比/…）
```

### 3.3 工具与集成

- `AnalyzeCnIndustryChainTool`（`cn_tools.py`）：入参 `chain_id / shock_node / price_change`；出参带 status + ImpactResult。
- 与 CARD-05 联动（可选增强）：ImpactResult 中毛利率敏感 → 目标公司利润假设扰动 → DCF 敏感性附加行。若 CARD-05 已完成则实现，否则记录待办。

## 4. 实施步骤

1. 通读 `industries.py` 行业归属结构，确定 companies 挂接方式。
2. 定义图谱 JSON schema + 3 条链数据（边权先 assumption 登记，留 sourced 替换位）。
3. 实现加载/查询/传导计算（纯函数）。
4. 测试：手工算例核对传导数值；无出边节点、环检测、边权缺失三类异常路径。
5. 注册工具 + 契约测试；边界声明文本模板化。

## 5. 验收标准

- [ ] 传导数值手工算例精确匹配（含多级路径）
- [ ] 环检测、缺失边权、未知节点三类 error 信封测试
- [ ] 每份输出含 boundary_statement 与 assumptions_used（测试断言非空且全量登记）
- [ ] 全部测试通过；图谱 JSON 可读且有 schema 校验测试

## 6. 红线（本卡特有）

- 图谱边权没有 sourced 来源时，全链输出必须带"基于假设的演示"标注（同 CARD-05 的 data_grade 机制）
- 传导模型线性假设必须出现在边界声明中；不做复杂动态模型伪装精确
- 不引入图数据库；JSON + 纯函数即止

## 7. 执行备注（agent 填写）

| 日期 | 记录（链数据来源 / 算例 / 偏差） |
|---|---|
|  |  |
