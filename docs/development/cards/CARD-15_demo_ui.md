# CARD-15: Workbench Demo UI 增量（演示界面）

| 属性 | 值 |
|---|---|
| 优先级 | P1（贯穿，随各业务卡逐页落地） |
| 竞赛阶段 | 初赛版 |
| 对应赛题 | 现场展示（评分项） |
| 依赖 | 各业务卡（页面随能力出现） |
| 实现复杂度 | 中（分散投入，合计约 4 人日） |
| 状态 | ◐ 部分完成 |

## 1. 目标

在现有 Streamlit workbench 上做**最小增量**新增 Demo 页面，覆盖 5 分钟 Demo 主故事所需的全部界面。**禁止大规模重写**——现有 workbench.py 的既有页面不动，新页面以独立模块挂载。

## 2. 对应竞赛评分点

现场展示（Demo 流畅度直接决定评委第一印象）。

## 3. 为什么需要这个模块

Demo 是初赛视频与决赛现场的载体；但 v2 的"全量拆分 workbench"是工程洁癖，挤占竞赛窗口，本卡收敛为最小增量。

## 4. 输入 / 输出

- **输入**：各业务卡的服务接口
- **输出**：`src/cn/workbench_demo.py` + 挂载入口（新增页面不动旧代码路径）

## 5. 页面清单（对应 Demo 主故事）

| 页面 | 支撑卡片 | 关键交互 |
|---|---|---|
| Upload Task | 01 | 上传 PDF/研草稿 → ingest 进度 |
| Document Viewer | 01/09 | PDF 预览 + 点击数字跳页（bbox 高亮可选） |
| Execution Trace | 07 | 实时事件流（任务运行中） |
| Financial Analysis | 03/04 | 指标表可展开公式 + 可比性横幅 |
| Report Corrections | 05 | 纠错列表 → 点击跳原 PDF 页 |
| Valuation | 08 | 区间条 + 敏感性矩阵 + 假设展开 |
| Claim-Evidence Graph | 09 | 结论点击 → 图谱逐层展开 |
| Investment Memo | 10 | 备忘录 + 逐句三级标注 |
| Validator | 现有扩展 | 阻断/降级结果展示 |
| Audit Replay | 12 | 选 run_id → 时间线重放 |
| Export Evidence Pack | 12 | 一键导出 zip |

## 6. API / Tool Contract

```python
# workbench/demo/__init__.py
def mount_demo_pages(): ...   # 在现有入口追加挂载，不修改既有页面函数
```

实现约束：沿用现有 Streamlit 版本与组件风格；样式走现有设计约定；不引入新前端依赖。

## 7. 金融逻辑

无；但页面呈现必须如实：blocked/failed/warning 状态醒目，**不美化系统的不确定性**——这本身就是演示卖点。

## 8. Edge Cases

1. 大 PDF 预览卡顿 → 页级渲染 + 按需加载页图片，不为性能牺牲证据定位
2. 长任务（真实模型）→ 执行轨迹页轮询进度（沿用现有任务轮询机制，不引入 SSE 新依赖，除非时间允许）
3. 旧数据无新字段 → 页面兼容降级显示

## 9. Failure Mode

页面崩溃不影响后端任务（UI 与服务隔离，沿用现有服务层约定）；浏览器控制台零报错是验收硬项。

## 10. Validator Rules

- 每个新页面入口可在 smoke_workbench 中被发现（脚本扩展断言）
- Demo 页面不直接读数据库裸数据——必须走服务层接口（与现有架构一致）

## 11. Unit Tests

挂载函数不破坏既有页面（smoke 扩展）；页面路由参数校验。

## 12. Integration Tests

按 DEMO_FLOW.md 剧本人工全流程走查 + 截图；控制台零报错。

## 13. Benchmark

Latency（页面响应）粗粒度记录入执行备注即可，不设专项。

## 14. Demo Method

本卡即 Demo 的物质载体；每个页面完成后立即按 DEMO_FLOW 对应步骤验收。

## 15. 验收标准

- [x] 11 个页面全部挂载且互不干扰既有功能
- [x] smoke 通过 + 控制台零报错 + 对照原页面无回归
- [ ] 5 分钟 Demo 剧本可全程无卡点走完（彩排验证）
- [x] 新增页面代码均在 `src/cn/workbench_demo.py` 内（`workbench.py` 仅保留挂载入口）

## 16. 执行备注（agent 填写）

| 日期 | 记录 |
|---|---|
| 2026-10-03 | 新增 `src/cn/workbench_demo.py` 与工作台挂载入口，提供 11 个 CARD-15 只读页面标签、缺件降级和 Audit Replay 时间线入口。 |
| 2026-10-03 | 接入 `workbench_service.card15_demo_data()`：快照页、ACME、Claim Passport、Fragility、Temporal、FinFuzz 和 Replay 均只读服务层/持久化 run 产物；新增安全 Evidence Pack 下载，源 `runs/` 与导出目录隔离。 |
| 2026-10-03 | FastAPI 新增 `/api/demo/runs`、`/api/demo/runs/{run_id}`、`POST /api/demo/runs/{run_id}/export`；离线测试 424 passed，Workbench smoke 12/12。 |
| 2026-10-04 | Upload Task 接入 `DocumentService`：上传文档经 SHA256 注册、解析后展示页级 SourceFragment 和候选事实；候选事实不会自动升级为已验证 Evidence。离线测试 425 passed，Workbench smoke 12/12。 |
| 2026-10-04 | 上传文档解析后接入 ACME 确定性完整性检查，在 Validator 页展示 integrity report 与 review queue；不自动修正任何候选数字。 |
| 2026-10-04 | run 产物按演示语义分发到对应页面：Claim Passport→Claim-Evidence Graph、Memo→Investment Memo、Corrections→Report Corrections；JSON/Markdown/二进制缺失状态均不伪造内容。 |
| 2026-10-04 | smoke 覆盖 CARD-15 本身，13/13 页面通过；本地浏览器彩排验证 11 个标签、无 run 时的 unavailable 降级和控制台无 error/warning。稳定演示命令使用 `--server.fileWatcherType none`，避免热重载重复初始化。 |
| 2026-10-04 | 当前仓库没有可授权的真实年报与完整持久化 run；未伪造数据补齐 5 分钟真实材料彩排，该项保留待真实资产接入后验收。 |
| 2026-10-04 | 新增统一 `card15_readiness` 服务契约与 `/api/demo/readiness`：检查年报 PDF、研报草稿、snapshot、run manifest/events 及五类创新产物；UI 顶部显示 `ready/partial/blocked/missing_assets`，无持久化 run 时明确禁止导出伪造 Evidence Pack。新增正常缺失、非法路径和不完整 run 测试；真实材料彩排仍为 blocked/pending。 |
