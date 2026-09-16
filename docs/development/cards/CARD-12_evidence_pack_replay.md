# CARD-12: Evidence Pack & Audit Replay（证据包与审计回放）

| 属性 | 值 |
|---|---|
| 优先级 | P1 |
| 竞赛阶段 | 初赛版（10/12–10/15） |
| 对应赛题 | "来源可核验、执行过程可追溯、运行结果可复现"的最终交付形态 |
| 依赖 | CARD-07（events/manifest）、CARD-09（图） |
| 实现复杂度 | 中（约 3–4 人日） |
| 状态 | ☐ 未开始 |
| Skill 要求 | 动手前加载 financial-data-provenance |

## 1. 目标

实现每次任务的**标准产物目录**（Evidence Pack）与**历史任务时间线重放 UI**（Audit Replay），并内置 7 个失败注入现场演示场景。这是"可追溯/可验证/可复现"从能力变成评委可见成果的最后一公里。

## 2. 对应竞赛评分点

来源可核验、过程可追溯、结果可复现、现场展示。

## 3. 为什么需要这个模块

能力再强，评委看不到等于不存在。Evidence Pack 是可下载、可离线检查的交付物；Audit Replay 是"结果不是仅由 LLM 生成"的可视化证明。

## 4. 输入 / 输出

- **输入**：run 目录（manifest.json + events.jsonl + 各模块产物）
- **输出**：完整 Evidence Pack 目录 + UI 重放视图

## 5. 数据模型（Evidence Pack 目录结构，指令原文）

```text
runs/run_xxx/
├── report.md                # 人类可读报告（memo）
├── report.json              # 结构化报告
├── financials.xlsx          # 财务分析表
├── valuation.xlsx           # 估值与敏感性
├── corrections.xlsx         # 纠错清单（如有草稿核查）
├── claims.json              # 全部 Claim（含三级标注）
├── evidence.json            # 证据账本（含文档页码）
├── calculations.json        # 计算记录（公式+输入）
├── validation.json          # validator 结果
├── events.jsonl             # 审计事件流
├── manifest.json            # 运行清单
├── charts/                  # 图表（如有）
└── citations/               # 来源定位快照（如有）
```

## 6. API / Tool Contract

```python
def export_evidence_pack(run_id) -> Path: ...   # 打包 zip + 目录
# Audit Replay UI（workbench，走 CARD-15 页面骨架）：
# 选择 run_id → 按 events.jsonl 时间顺序展示：
# 文件加载 → hash → parser → 财务提取 → normalization → retrieval
#          → tool call → calculation → claim → validation → report
# 每步可展开：input / output / source / status / timestamp
```

## 7. 金融逻辑

本卡无金融计算；核心是**忠实呈现**：重放视图不得美化或跳过失败事件，blocked/failed 状态用醒目标记——失败注入演示正依赖于此。

## 8. Edge Cases

1. run 中断（无 report）→ Pack 仍导出，缺件标注 incomplete
2. events.jsonl 损坏行 → 跳过并标记，重放继续（不中断演示）
3. 大 run（千级事件）→ UI 分页/虚拟滚动，不牺牲完整记录
4. 多 run 对比 → 重放视图支持并排 diff 两次 run 的 manifest

## 9. Failure Mode

导出失败 → 明确报错与缺件清单。**禁止导出"看起来完整"的残包**。

## 10. Validator Rules

- Pack 完整性校验：13 类文件存在性检查（缺件降级导出需显著标注）
- manifest 与 events 的 run_id 一致性
- report 中引用的 claim/evidence id 在 Pack 文件内全部可解析（打包前校验）

## 11. Unit Tests

导出完整性；缺件降级标注；损坏 events 容错；zip 解包校验。

## 12. Integration Tests

一次含失败注入的 run → Pack 导出 → 重放 UI 展示失败事件 → 现场可复现。

## 13. Benchmark

Replay Success Rate 已由 CARD-07 测；本卡验收重放 UI 的呈现完整性（人工验收 + 截图入执行备注）。

## 14. Demo Method（失败注入演示剧本，7 场景）

| # | 注入 | 预期系统行为 |
|---|---|---|
| 1 | 缺失总股本 | 阻断每股估值，明确报缺 |
| 2 | 删除 PDF 某页 | citation incomplete 告警 |
| 3 | 单位万元→亿元 | unit checker 报错 |
| 4 | 草稿给错误同比 | report checker 定位错误并给正确值 |
| 5 | 旧财报+更正公告 | source conflict，按优先级取更正值 |
| 6 | 删除关键 Evidence | 对应 Claim 变 blocked |
| 7 | 改写无证据因果结论 | unsupported causal inference 标记 |

目标：证明 FinTrace"错误的时候知道自己不能下结论"。5 分钟 Demo 正片用 #6，其余备答辩追问。

## 15. 验收标准

- [ ] 13 类产物文件导出与完整性校验
- [ ] 重放 UI 十一阶段时间线 + 步骤展开五要素齐全
- [ ] 7 个失败注入场景全部可现场复现（脚本化，一键触发）
- [ ] 全部测试离线通过

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
|  |  |
