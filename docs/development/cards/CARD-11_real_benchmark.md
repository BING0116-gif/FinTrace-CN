# CARD-11: Real-world Benchmark（真实基准评测）

| 属性 | 值 |
|---|---|
| 优先级 | P0（从第一个模块开发起持续建设，不是最后补） |
| 竞赛阶段 | 贯穿初赛（10/12–10/15 收口） |
| 对应赛题 | 赛题7 内部评价机制 + 全部评分项的量化证据 |
| 依赖 | 无（与各业务卡互为配套，业务卡完成一块接一块） |
| 实现复杂度 | 高（约 6 人日，分散投入） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-agent-evaluation |

## 1. 目标

在现有 benchmark/real_benchmark/ablation 基础上（`benchmarks/cn_agent_v1.json` 保持不动）新建 `cn_agent_v2` 三级评测体系：**Synthetic Test Set / Real Public A-share Test Set / Holdout Set**，覆盖 24 项指标。任何 LLM 新能力必须与 baseline 对比。评分项的量化证据全部出自本卡。

## 2. 对应竞赛评分点

结果稳定性、数据准确性、计算准确性——以及"不编造 benchmark 结果"的红线。

## 3. 为什么需要这个模块

竞赛答辩必被追问"你怎么证明准确？"。没有真实材料基准就无法回答；v2 把 benchmark 排在阶段4（赛后）是重大排期错误，本卡纠偏为贯穿建设。

## 4. 输入 / 输出

- **输入**：三级测试集 + 各模块运行结果
- **输出**：`output/benchmark/cn_agent_v2/` 评测报告（markdown + json），含环境 fingerprint

## 5. 数据模型（三级测试集）

| 集合 | 内容 | 存储 |
|---|---|---|
| Synthetic | 合成年报/公告/研草稿 + planted 错误 + 封闭算例真值 | `tests/fixtures/`（入库，生成脚本随附） |
| Real | 公开披露的真实年报/半年报/季报/公告/研报草稿 + 人工标注真值 | `data/benchmark_real/`（**gitignore**；提交下载脚本 + sha256 清单；版权材料不进 Git） |
| Holdout | Real 的扣留子集，只在收口评测用 | 同上，目录隔离 |

真值标注格式：`{document_id, metric, period, expected_value, unit, scope, page}`——每条可回查原文页。

## 6. API / Tool Contract

```python
# 扩展 src/cn/benchmark.py（沿用现有任务注册格式，先读现状）
python -m src.cn.benchmark --suite cn_agent_v2 --set synthetic --out output/benchmark/
python -m src.cn.benchmark --suite cn_agent_v2 --set real --out output/benchmark/   # integration
```

## 7. 金融逻辑（24 项指标）

**提取组**：Extraction Precision / Recall / F1；Numeric Exact Match；Unit Accuracy；Period Accuracy；Scope Accuracy；Page Attribution Accuracy
**引用组**：Citation Precision；Citation Recall
**计算组**：Calculation Accuracy（含 YTD 单季化、同比状态迁移）
**核查组**：Checker Precision / Recall / F1；False Positive Rate
**智能体组**：Tool Selection Accuracy；Parameter Accuracy；Task Completion Rate；Evidence Coverage
**安全组**：Unsafe Conclusion Leakage（inference 冒充 fact 的泄漏率）
**复现组**：Replay Success Rate；Multi-run Consistency
**成本组**：Latency；Token Cost

阈值纪律：**所有目标值待各模块 baseline 测试后冻结**，评测报告里 baseline 数字如实呈现，禁止预填 95%/98% 类目标。

## 8. Edge Cases

1. 真实材料无法下载（链接失效）→ 下载脚本多源（巨潮/交易所）+ sha256 校验失败报错
2. 人工标注量有限 → Real 集先覆盖 2–3 家公司全披露链，标注规范文档化，宁小勿错
3. LLM 采样波动 → multi-run 指标固定 n≥3，报告含方差
4. Holdout 泄漏 → 收口前 Holdout 不参与任何开发调试（目录权限+流程纪律）

## 9. Failure Mode

某模块指标无法计算（如无真实材料）→ 报告该指标标 N/A + 原因，不删除行——**评测报告的诚实性本身是被评审的对象**。

## 10. Validator Rules

- 真实/离线结果物理隔离：文件名 real 前缀 + 摘要页运行环境标注（模型/温度/日期/git commit），混排时报错
- 每份报告含环境 fingerprint（沿用现有机制）
- 评测代码不得为通过率特判任务

## 11. Unit Tests

指标计算器正确性（构造已知 P/R/F1 的假结果核对）；报告生成格式；fingerprint 稳定性。

## 12. Integration Tests

synthetic 集全链离线跑通；real 集 integration 标记（需凭证与授权）。

## 13. Benchmark

本卡自身即 benchmark 体系；对 LLM 新能力（如 CARD-05 提取器）强制跑 baseline 对比（无对比不合并）。

## 14. Demo Method

答辩材料附评测报告表：各模块 baseline 数字 + 环境指纹 + "真实/合成"分列。演示中可展示评测命令一键复跑。

## 15. 验收标准

- [ ] 三级测试集建立（Real ≥2 家公司全披露链 + 人工标注）
- [ ] 24 项指标计算器全部有单测
- [ ] cn_agent_v1 零回归；v2 synthetic 全离线可跑
- [ ] 真实/离线隔离与标注机制有测试
- [ ] 阈值冻结流程文档化（baseline → 冻结 → 版本化）

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
