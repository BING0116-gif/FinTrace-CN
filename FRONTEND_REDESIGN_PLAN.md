# FinTrace-CN 前端重构设计方案

## 1. 目标

将现有 Streamlit 工作台重构为一套专业、清晰、可信、易上手的 A 股研究工作台。

重构重点不是增加装饰，而是把现有系统的真实能力组织成完整的研究流程：

```text
新建研究
  → 文档登记
  → 文档解析与证据提取
  → 财务分析
  → 研报核查
  → Claim Passport 验证
  → 估值分析
  → 投资备忘录
  → 审计回放与 Evidence Pack
```

保持现有技术边界：

- 继续使用 Streamlit + FastAPI。
- 不迁移到 React，不重写后端业务层。
- 不改变 `src/cn/` 中的金融计算、证据、Validator 和报告逻辑。
- UI 只负责展示和交互，不在前端重新计算金融事实。
- 所有结论必须保留状态、来源、期间、单位、证据和验证信息。

## 2. 设计定位

产品定位为：

> 面向 A 股投研人员的可验证金融研究工作台。

整体风格参考专业 fintech SaaS：

- 明亮、克制、可信。
- 信息密度高，但层级清晰。
- 用状态和证据帮助用户判断，而不是用复杂图表制造压力。
- 允许失败、警告和阻断状态自然出现。
- 重要数字和结论都可以回溯到证据和原始文档。

## 3. 全局信息架构

### 3.1 左侧导航

```text
总览
研究任务
文档与证据
财务分析
研报核查
估值分析
投资备忘录
审计回放
每日复盘
系统评测
```

当前的“案例演示”和“CARD-15 Demo”保留为演示模式入口，不作为日常研究主导航。

### 3.2 顶部上下文栏

顶部固定展示当前研究上下文：

- 公司名称和股票代码。
- 研究日期和数据截止时间。
- 当前 Run ID。
- 当前验证状态：可验证 / 警告 / 阻断。
- 数据模式：离线可复现 / 在线数据。
- 新建研究按钮。
- 导出 Evidence Pack 或研究报告入口。

### 3.3 页面上下文原则

用户在任何页面都能看到：

- 当前公司。
- 当前研究快照。
- 当前研究状态。
- 当前数据时点。
- 当前结论是否允许输出。

## 4. 核心页面设计

## 4.1 研究总览

目标：用户进入系统后，立即知道研究进行到哪里、结论是否可信、下一步该做什么。

页面模块：

### 研究进度

```text
文档已登记 → 解析完成 → 证据提取 → 财务分析 → 研报核查 → 估值 → 备忘录
```

每个步骤显示：

- 完成时间。
- 状态。
- 产物数量。
- 是否存在警告。
- 点击后的详情入口。

### 结论健康度

显示：

- 可验证结论数量。
- 需要进一步核查数量。
- 已阻断数量。
- 证据完整度。
- 受影响的结论。

### 关键指标卡片

- RAW 收盘价。
- 市值。
- TTM P/E。
- TTM 归母净利润。
- 营业收入。
- 经营活动现金流。

每张卡片支持：

- 展示数值、期间和单位。
- 显示同比或环比变化。
- 点击跳转 Evidence。
- 缺失或阻断时显示明确原因，不展示猜测值。

### 关键结论

每条结论显示：

- fact / inference / opinion 类型。
- 验证状态。
- Evidence 数量。
- 关联 Calculation。
- 点击进入 Claim 详情。

### 风险与关注点

集中展示：

- Validator 警告。
- ACME 约束违反。
- 数据过期或期间混用。
- 估值适用性问题。
- Thesis Fragility 关键节点。

## 4.2 研究任务

目标：把上传材料、选择公司和启动研究变成清晰的任务创建流程。

采用三步向导：

### 第一步：选择研究对象

- 公司名称。
- 股票代码。
- 研究目的。
- 研究截止日期。
- 研究类型：公司研究 / 估值 / 研报核查 / 每日复盘。

### 第二步：上传材料

- 年报 PDF。
- 研报草稿。
- 公告。
- 其他 TXT / Markdown 材料。

上传后显示：

- 文件名。
- SHA256。
- 文件类型。
- 页数。
- 解析状态。
- 已发现的警告。

### 第三步：确认并启动

- 数据口径。
- 研究时点。
- Provider / Snapshot。
- 是否使用缓存。
- 是否允许生成投资备忘录。

任务详情页显示：

- 当前步骤。
- 事件流。
- 任务耗时。
- 缓存命中情况。
- 错误与警告。
- 暂停、取消、重试操作。

## 4.3 文档与证据

目标：让用户明确每个数据来自哪里，为什么可以或不可以用于结论。

采用“文档列表 + 证据详情 + 原文预览”布局。

### 左侧：文档列表

- 年报。
- 研报草稿。
- 公司公告。
- 数据快照。
- 行业数据。
- 其他来源。

### 中间：文档详情

- document_id。
- 文件名。
- SHA256。
- parser 版本。
- 页数。
- 研究期间。
- 发布时间。
- 来源。
- 解析状态。
- 警告。

### 右侧：原文预览

- PDF 页码。
- 证据定位。
- 高亮原文片段。
- 表格单元格。
- 关联 Evidence 和 Claim。

### 证据表

字段包括：

- Evidence ID。
- 指标。
- 数值。
- 单位。
- 期间。
- 口径。
- 来源。
- 页码。
- 验证状态。
- 关联 Claim。

## 4.4 财务分析

目标：展示结果，同时让用户理解计算过程和数据口径。

页面模块：

- 收入趋势。
- 利润趋势。
- 现金流趋势。
- 年同比。
- 单季度 QoQ。
- 盈利质量。
- 现金转换。
- 核心诊断信号。
- 公式与证据抽屉。

每个指标都可以展开为：

```text
指标结果
  ↓
计算公式
  ↓
输入数据
  ↓
Evidence ID
  ↓
原始文档页码
```

重点突出 A 股研究特性：

- YTD 累计值转换为单季度值。
- RAW 价格纪律。
- 合并口径与母公司口径区分。
- 单位和期间匹配。
- 数据时效检查。
- 缺失数据时不生成强结论。

## 4.5 研报核查

这是最重要的产品界面之一。

采用左右分栏：

### 左侧：研报草稿

高亮显示：

- 错误数字。
- 数字量级错误。
- 单位错误。
- YTD / 单季度计算错误。
- 错误引用。
- 过期引用。
- 无证据因果判断。
- 合并口径 / 母公司口径错误。

### 右侧：Financial Claim Passport

每个 Claim 展示以下 proof 区块：

1. Statement。
2. Source。
3. Accounting Context。
4. Calculation。
5. Assumption。
6. Dependency。
7. Validation。
8. Integrity。

状态统一使用：

- VERIFIED。
- DEGRADED。
- STALE。
- BLOCKED。
- CONFLICTED。

核心操作：

- VERIFY CLAIM。
- 跳转原文。
- 查看计算。
- 查看依赖。
- 标记待处理。
- 导出核查报告。

界面明确区分：

- LLM 提取出的 Claim。
- 确定性 Checker 的结果。
- 证据和计算过程。
- 最终是否允许用于报告。

## 4.6 估值分析

采用三层结构。

### 第一层：估值摘要

- Bear。
- Base。
- Bull。
- 当前价格。
- 估值区间。
- 上行 / 下行空间。
- Validator 状态。

### 第二层：估值计算

- PE / PB / PS。
- EPS × PE 敏感性矩阵。
- BPS × PB 敏感性矩阵。
- 可比公司分布。
- 方法间 dispersion。
- 价格区间。

### 第三层：假设注册表

每个假设显示：

- 假设名称。
- 基准值。
- 区间范围。
- 数据来源。
- 证据。
- 验证状态。
- 影响的 Claim。

页面不只展示一个目标价，而要展示目标价依赖的输入、假设和风险。

## 4.7 投资备忘录

采用阅读型布局。

每段显示认识论标记：

- `FACT`。
- `INFERENCE`。
- `OPINION`。

点击段落后展示：

```text
Memo 段落
  ↓
Claim
  ↓
Calculation
  ↓
Evidence
  ↓
PDF 原文
```

当关键证据失效时，对应段落自动显示：

- 已阻断。
- 需要重新验证。
- 结论不可用。

## 4.8 审计回放

采用时间线布局：

```text
Run 创建
  ↓
文档登记
  ↓
解析
  ↓
事实提取
  ↓
ACME 检查
  ↓
财务计算
  ↓
研报核查
  ↓
估值
  ↓
Memo 生成
  ↓
Validator
  ↓
Evidence Pack 导出
```

每个事件可以展开查看：

- 输入。
- 输出。
- 时间。
- 版本。
- Provider。
- Prompt hash。
- Snapshot ID。
- 状态。
- 错误信息。

同时保留：

- Replay Run。
- Failure Injection。
- Evidence Pack 下载。

## 5. 视觉设计系统

### 5.1 色彩

| 用途 | 色值 |
|---|---|
| 主色 | `#102A43` |
| 强调蓝 | `#1F6FEB` |
| 可验证绿色 | `#159570` |
| 警告琥珀 | `#D99400` |
| 阻断珊瑚红 | `#D9534F` |
| 页面背景 | `#F7F8FA` |
| 卡片背景 | `#FFFFFF` |
| 边框 | `#E5EAF0` |
| 正文 | `#172B4D` |

### 5.2 视觉原则

- 使用轻边框卡片。
- 卡片圆角约 10–12px。
- 使用少量阴影增加层次。
- 标题清晰，辅助信息克制。
- 状态颜色只用于验证状态和风险提示。
- 不使用密集黑底终端风格。
- 不大量使用涨跌红绿。
- 重要操作统一使用深蓝主按钮。
- 导航和动作使用 Material Symbols 图标。
- 使用中文句式标题，避免过度标题化。
- 使用空状态、Skeleton 和明确的错误说明。

### 5.3 Streamlit 实现原则

- 使用 `.streamlit/config.toml` 配置主题。
- 使用 `st.container(border=True)` 组织卡片。
- 使用 `st.metric` 展示关键指标。
- 使用 `st.badge` 展示验证状态。
- 使用 `st.status` 展示任务进度和事件流。
- 使用 `st.segmented_control` 实现场景切换。
- 使用 `st.popover` 承载轻量筛选器。
- 使用 `st.dialog` 承载确认和短表单。
- 使用 `st.fragment` 处理独立刷新区域。
- 使用 `st.cache_data` 缓存快照和计算结果。
- 使用 `st.session_state` 保存当前公司、Run、Claim 和页面状态。
- 新代码不使用已废弃的 `use_container_width`。
- 只在原生 Streamlit 组件无法满足需求时使用自定义组件。

## 6. 前端代码组织

当前 `workbench.py` 是单文件大型入口，建议逐步拆分为：

```text
workbench.py
app_pages/
  overview.py
  research_tasks.py
  documents.py
  financial_analysis.py
  report_checker.py
  valuation.py
  memo.py
  audit_replay.py
  daily_review.py
  evaluations.py
ui/
  theme.py
  layout.py
  cards.py
  status.py
  evidence.py
  charts.py
  claim_passport.py
services/
  research_loader.py
  navigation.py
  session_state.py
```

拆分原则：

- `src/cn/` 继续负责业务逻辑。
- `workbench_service.py` 继续负责数据契约。
- `app_pages/` 只负责页面编排。
- `ui/` 负责统一视觉组件。
- `services/` 负责 UI 数据加载、路由和 session state。
- 不在 UI 层重新计算金融事实。
- 不让 UI 自己生成不存在的证据或结论。

建议使用 Streamlit 的 `st.navigation` 和 `st.Page` 组织页面，避免继续扩展大型 `if page == ...` 分支。

## 7. 实施阶段

### Phase 1：应用壳层

- 新主题配置。
- 深色侧边栏。
- 顶部公司上下文栏。
- 统一状态 Badge。
- 统一卡片和页面标题。
- 统一 session state。
- 统一导航。
- 保留原页面作为兼容入口。

### Phase 2：核心研究流程

- 研究总览。
- 研究任务。
- 文档与证据。
- 财务分析。
- 估值分析。

### Phase 3：核心差异化能力

- 研报核查。
- Financial Claim Passport。
- VERIFY CLAIM。
- Claim-Evidence Graph。
- 投资备忘录。

### Phase 4：可信与复现

- 审计回放。
- Evidence Pack。
- Failure Injection。
- Temporal Revalidation。
- 每日复盘。

### Phase 5：体验优化

- 页面加载 Skeleton。
- 缓存和局部 rerun。
- 统一空状态。
- 统一错误状态。
- 页面级导出。
- 可访问性检查。
- 浏览器回归检查。

## 8. 页面与现有能力映射

| 新页面 | 主要现有来源 |
|---|---|
| 研究总览 | `research_summary`、`research_market`、`research_financials`、`research_validation` |
| 研究任务 | `agent_service`、`workbench_service` 任务接口 |
| 文档与证据 | `research_evidence`、Documents Service、Evidence Ledger |
| 财务分析 | `research_financials`、`research_financial_trends`、analysis 模块 |
| 研报核查 | Checker、Claim、Finding、Validator |
| Claim Passport | `src/cn/proof/`、Claim Passport Verifier |
| 估值分析 | `research_valuation`、Relative Valuation、Assumption Registry |
| 投资备忘录 | `src/cn/memo.py`、Claim-Evidence Graph |
| 审计回放 | `research_trace`、Demo Run、Evidence Pack |
| 每日复盘 | `daily_review` 服务和报告模块 |
| 系统评测 | `list_evaluations`、`evaluation_detail` |

## 9. 交互状态规范

所有页面统一使用以下状态：

### 可验证

表示当前数据和证据满足输出条件，可以显示确定性结果。

### 警告

表示结果可以阅读，但存在时效、覆盖、口径或可比性限制。

### 降级

表示部分依赖缺失，结果只能用于有限范围，不得被包装成完整结论。

### 阻断

表示关键证据或输入缺失，系统必须隐藏或标记不可用结论。

### 冲突

表示不同来源或版本之间存在无法自动解决的冲突，需要人工处理。

状态卡片必须同时展示：

- 状态名称。
- 具体原因。
- 受影响的结果。
- 下一步操作。

## 10. 验收标准

- 用户可以在 30 秒内理解当前研究状态。
- 用户可以从任意关键数字跳到 Evidence。
- 用户可以从任意 Claim 跳到计算过程和原文页。
- Validator 阻断时，页面不会继续显示确定性结论。
- 页面不混淆事实、推论和观点。
- 离线快照和真实数据状态有明显区分。
- 研报核查、Claim Passport、估值、Memo、Replay 能够形成完整链路。
- 原有离线测试和 smoke test 不受影响。
- 浏览器控制台无新增错误。
- 页面整体风格与产品概念图一致。
- 所有新增页面都能显示空数据、部分数据、警告和阻断状态。

## 11. 验证命令

每个阶段完成后运行：

```powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
python scripts/smoke_workbench.py
git diff --check
git status --short
```

涉及浏览器界面时，额外进行：

- 新建研究流程验证。
- 快照切换验证。
- Evidence 跳转验证。
- Claim Passport 验证。
- Validator 阻断验证。
- Evidence Pack 导出验证。
- 页面刷新和 session state 验证。

## 12. 推荐下一步

下一轮开发从 Phase 1 开始：

1. 建立新的 Streamlit theme。
2. 建立统一应用壳层。
3. 建立侧边栏和顶部上下文栏。
4. 抽取通用状态、卡片和证据组件。
5. 重构研究总览页。
6. 保留旧页面作为兼容回退。

完成 Phase 1 后，再逐页接入真实 service 数据，避免一次性重写整个工作台。
