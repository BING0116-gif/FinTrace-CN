# 演示案例与 golden baseline

## 两个案例

- `成功研究：贵州茅台`：`600519.SH_20260810_tushare_v1`。快照、证据账本、关键估值输入和 4 个可比同业均通过，允许展示报告。
- `Validator 阻断：缺少关键估值输入`：`600519.SH_demo_missing_evidence_v1`。由 baseline 脚本从同一固定快照生成，但刻意移除 `total_shares`。Validator 会阻断估值结论和报告，UI 只展示修复路径。

这不是实时行情或投资建议。成功和阻断状态都应从 `research_validation()` 读取，不能在界面中硬编码为真实结果。

## 首次准备与启动

```powershell
cd C:\Users\HUAWEI\Desktop\Agentic-Analyst\stock-analyst
.\.venv\Scripts\python.exe scripts\create_golden_baseline.py
.\.venv\Scripts\streamlit.exe run workbench.py
```

打开终端显示的本地地址。侧栏进入“案例演示”：先打开茅台案例，查看报告；返回后打开阻断案例，查看“证据与校验”。这可在 30 秒内呈现“快照 → 证据 → 校验 → 报告 / 阻断”的完整闭环。

`output/golden_baseline/manifest.json` 是基线索引，包含快照、Markdown 报告、Excel、元数据和两份已测量评测结果的 SHA-256。重跑脚本会以当前本地受控产物重新固化该基线。

## 少量高价值边界覆盖

- 银行：`600036.SH_20260813_tushare_v1`，估值服务会公开金融机构方法边界（仅 PE/PB），不把一般企业方法套到银行。
- 北交所、ST、停牌：应在下一次数据采集时以最小快照夹具分别覆盖交易所后缀、风险状态和 `trading_status`，并断言 UI 只显示来源状态、不推断价格或交易结论。此版本不扩大常规样本集。

## 已有提交脉络

| 提交 | 作用 |
|---|---|
| `c7a34c3` | 基于版本化快照的同业估值 |
| `a5e3344` | 快照工作流与输出卫生 |
| `47815d0` | Provider 路由、Validator、行业分类和评测 |
| `634d16f` | A 股研究基础设施与 Tushare 集成 |

本次案例打磨应作为后续独立提交，建议提交信息：`feat(demo): add reproducible success and validator-blocked cases`。
