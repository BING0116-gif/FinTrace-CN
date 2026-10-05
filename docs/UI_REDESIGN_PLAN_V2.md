# FinTrace-CN 界面改造方案 V2（三图对齐版）

> 状态：待评审 → 待实施
> 日期：2026-10-05
> 前置文档：`FRONTEND_REDESIGN_PLAN.md`（V1，本方案在其基础上对齐三张目标设计稿）
> 目标设计稿：图1「研究工作台总览」、图2「研报核查 / Claim Passport」、图3「相对估值」

---

## 1. 目标与原则

把现有 Streamlit 工作台的呈现层对齐三张设计稿，解决当前界面的三个核心问题：

1. **导航乱**：13 个一级页面，其中 6 个演示/工程向，业务用户找不到主线。
2. **技术符号外露**：Claim ID、snapshot ID、`Missing service functions: ...`、"CARD-15"、
   "illustrative" 等英文/代码直接出现在明面上。
3. **纵向堆叠、信息密度低**：overview 是一条条 metric 往下排，设计稿是高密度卡片网格。

### 不可动摇的原则（红线）

- **数据语义不减**：evidence ID、provider/快照、cutoff、期间、单位、guardrail 提示
  **只能从"明面"降级到 hover / 详情抽屉 / 展开区，不能删除**。设计稿自身也保留了
  "缺少证据""存在疑点"等状态。
- **不改 `src/cn/`**：金融计算、证据、Validator、报告逻辑零改动；UI 只是展示层。
- **不引入 LLM 文本冒充事实**；RAW 价格口径、涨红跌绿（A 股惯例）保持。
- **不换技术栈**：留在 Streamlit + FastAPI，不迁 React/Vue。现有 57 个离线测试文件
  和 `scripts/smoke_workbench.py` 是安全网，必须持续通过。
- **测试离线原则不变**：`python -m pytest -q -m "not integration" -p no:cacheprovider`
  在每阶段收尾时全绿。

---

## 2. 设计令牌（Design Tokens）

现有 `ui/theme.py` 的 token 与设计稿基本一致，做少量扩展即可：

```python
TOKENS = {
    # 保留
    "navy": "#102A43",     # 侧栏底色
    "blue": "#1F6FEB",     # 主色 / 链接 / 主按钮
    "green": "#159570",    # 可验证 / 通过
    "amber": "#D99400",    # 需进一步核查 / 警告
    "coral": "#D9534F",    # 冲突 / 阻断 / 下跌
    "canvas": "#F7F8FA",   # 页面底色
    "card": "#FFFFFF",     # 卡片
    "border": "#E5EAF0",
    "text": "#172B4D",
    "muted": "#627D98",
    # 新增
    "red_up": "#D9534F",   # 涨（A 股红涨，与 coral 同源）
    "green_down": "#159570",
    "chip_bg": "#EEF3F8",  # 证据 chip 底色
    "chip_text": "#1F6FEB",
}
```

补充全局规则：

- 字体：默认 Streamlit 字体栈；数字用 `font-variant-numeric: tabular-nums`。
- 卡片圆角 12px、边框 1px `--ft-border`、无阴影（flat）。
- 状态色语义表（全站唯一）：

| 状态 | 颜色 | 用途 |
|---|---|---|
| 可验证 / 已验证 / 通过 | green | 徽章、图标、健康度扇区 |
| 需进一步核查 / 警告 / 待跟踪 | amber | 徽章、问题标签 |
| 冲突 / 阻断 / 不匹配 | coral | 徽章、健康度扇区 |
| 信息 / 链接 / 主操作 | blue | 按钮、chip、进度点 |
| 涨 | red_up（红） | 财务指标同比 |
| 跌 | green_down（绿） | 财务指标同比 |

---

## 3. 信息架构：导航 13 → 8 + 1

### 3.1 映射表

| 现有页面（13） | 去向 | 新导航（8） |
|---|---|---|
| 研究总览 | 改造 | ① 总览 |
| 研究任务 | 保留改名微调 | ② 研究任务 |
| 证据与校验 | 拆分：证据→③、核查→⑤ | ③ 文档与证据 |
| 研究报告 | 并入③（报告是证据链的产出视图） | ③ 文档与证据 |
| 市场与行情 | 并入④ | ④ 财务分析 |
| 财务表现 | 改造 | ④ 财务分析 |
| （新增，Claim Passport 为主视图） | 由证据与校验中的核查部分升级 | ⑤ 研判核查 |
| 同行估值 | 改造 | ⑥ 估值 |
| 研究备忘录（memo.py） | 保留 | ⑦ 投资备忘录 |
| 审计回放（audit_replay.py） | 保留 | ⑧ 审计回放 |
| 案例演示 | 降级 | 「高级」折叠分组 |
| CARD-15 Demo | 降级 | 「高级」折叠分组 |
| AI Agent 研究 | 降级 | 「高级」折叠分组 |
| Agent 执行轨迹 | 降级 | 「高级」折叠分组 |
| 评测与消融 | 降级 | 「高级」折叠分组 |
| 每日复盘 | 降级 | 「高级」折叠分组 |

### 3.2 代码改动

- `workbench.py`：
  - `NAVIGATION` 列表改为业务 8 项 + `高级` 分组（`st.navigation` 支持
    `{"高级": [...]}` 分组写法）。
  - `pages()` 注册函数按映射表重排；演示页全部移入高级分组，默认收起
    （`expanded=False` 或分组默认折叠）。
- `app_pages/`：
  - 新增 `research_review.py`（研判核查页，见 §5.2）；`documents.py` 吸收
    `demo.py`/报告相关展示逻辑，改名「文档与证据」。
  - `financial_analysis.py` 吸收 `market`（行情）页的行情区块，改名「财务分析」。
  - `legacy_compat.py` 中为旧页面名保留 1 个版本的跳转别名（防止书签失效）。
- 侧栏顶部保留快照/公司选择器，底部（navy 区）放「高级」分组入口。

---

## 4. 全局框架改造（P0 核心）

### 4.1 顶部上下文条（对应图1 顶栏）

新增 `ui/context_bar.py`，全页面共用：

```
[公司名 代码 ▾] [● 可验证] [⧉ 离线可复现]   ……   [本次研究: 2024-12-10 14:32] [开始新研究 →]
```

- 数据来源：`app_pages/_shared.py` 的 `context_or_empty()` 已有 item/summary/validation，
  直接复用，不改服务层。
- 「可验证」徽章 = `validation.conclusion_allowed`；「离线可复现」徽章 =
  快照版本信息（从 summary 取，悬浮显示 snapshot ID —— 满足"降级不删除"红线）。
- 「开始新研究」按钮跳研究任务页。

### 4.2 证据 ID chip 化（消灭"代码感"的关键）

新增 `ui/chips.py`：

- `evidence_chip(evidence_id, source_label, page=None)` → 渲染成
  `E-014 年报 p.118 [PDF]` 样式的小芯片；真实 evidence ID 收进 chip 的
  `title` 悬浮属性与点击后的展开区。
- `status_chip(status)`、`tech_chip(snapshot_id)`（灰色小字，悬浮展开）。
- 替换点（全站 grep 排查）：
  - `ui/cards.py::metric` 中 `evidence_id` 的显示方式；
  - `ui/claim_passport.py` 的 `st.caption(f"Claim ID: ...")` → 收进悬浮；
  - `overview.py` 里所有 `ft-evidence` 等宽字体输出；
  - `workbench.py::service_contract_ready` 的 `Missing service functions` caption
    → 仅在 `st.session_state.debug` 为真时显示。
- 术语中英统一：界面词汇全中文（"研判核查"而非 "Claim Passport" 作为页面名，
  Passport 英文可保留为副标题小字）；"CARD-15 Demo" 等编号只出现在高级分组内。

### 4.3 布局网格

- `ui/layout.py` 增加 `card_grid(cols, cards)` 辅助：统一 12px 间距卡片网格；
- `.block-container` 最大宽度维持 1480px；卡片内边距统一 16px。

---

## 5. 三个重点页面详细设计

### 5.1 总览页（图1，`app_pages/overview.py`）

一屏布局（自上而下）：

1. **页头**：标题「研究工作台」+ 副标题「基于公开信息的多源证据验证 …」（已有文案）。
2. **研究进度卡（横向 stepper）**：
   - 新增 `ui/stepper.py`：横向圆点连线组件，纯 HTML/CSS（`st.markdown` 注入）。
   - 步骤沿用现有 `steps` 数据（文档已登记/解析完成/证据提取/财务分析/研判核查/
     估值/备忘录），映射现有 status → ✅/⏳/❌ 三态；每步下方放计数与时间。
3. **右列·结论健康度卡**：
   - Plotly donut（可验证/需进一步核查/存在冲突受限 三扇区）+ 中心总数；
   - 数据 = 现有 `validation` 聚合，替代当前 4 个 `st.metric`。
4. **右列·证据完整度卡**：进度条 = 已匹配证据 / 证据总数（现有 `evidence.records`）。
5. **中列·财务指标卡 ×3**（营业收入 / 归母净利润 / 经营活动现金流）：
   - 每卡：大数字 + 同比（涨红跌绿）+ 近 5 期 Plotly mini bar；
   - 数据 = `research_financial_trends` + `financials.statements`（现成）；
   - 证据 chip 放卡片右下角小字。
6. **最近的研究任务卡**：取 `list_evaluations` 最近一条，字段化展示
   （类型/创建/完成/耗时/文档数/提取证据数）。
7. **底部三卡**：关键结论（复用现有 `conclusion` 卡，加状态点）/ 主要证据来源
   （来源类型计数，来自 evidence ledger）/ 风险与关注点（warnings 列表 + 计数徽章）。

验收：一屏（1080p）内可见 1–7 全部卡片；无裸露 snapshot/evidence ID。

### 5.2 研判核查页（图2，新增 `app_pages/research_review.py`）

左右双栏（`st.columns([1.05, 1])`）：

**左栏·研报草稿**
- 数据源：报告/草稿文本 + 校验结果（`research_validation`、claims 列表）。
- Claim 句子高亮：按 claim 状态着色底纹（amber/coral/green 10% 透明度）；
  行尾问题标签（编号徽章：错误数字/重复错误/计算口径/缺少证据）。
- 顶部「全文视图 / 问题视图」切换：问题视图只列出含问题的段落 + 跳转。

**右栏·Claim Passport（中文标题「声明核查护照」）**
- 重构 `ui/claim_passport.py`：
  - 顶部：声明内容卡（amber 底纹高亮数字）+ DEGRADED 状态徽章（`ui/status.badge`）。
  - 中部：八区块（Statement/Source/Accounting Context/Calculation/Assumption/
    Dependency/Validation/Integrity）改为**状态表格**：一行一块，列为
    `名称 | 中文说明 | 值 | 状态图标`；行点击展开详情（expander 内嵌），
    替代现在的 8 个平铺 expander。
  - 主按钮：「核查此声明」（复用/触发现有核查链路，不新增后端逻辑）。
  - 底部·证据与原文 tabs：证据来源 chip 列表（E-014 年报 p.118 [PDF] 样式）+
    定位到的表格/原文片段（暂以文本/表格片段呈现）。

**P2（二期）**：内嵌 PDF 高亮查看器（pdf.js + `st.components.v1`），
一期先做「点击 chip → 下方展开原文片段」。

### 5.3 估值页（图3，`app_pages/valuation.py`）

- **顶部行情条**：公司名/代码、最新价（涨红跌绿）、总市值、PE(TTM)、PB(LF)、
  ROE(TTM) —— 数据全部来自现有 `research_market` / `summary.key_metrics`（RAW 口径保留）。
- **Tab 结构**：投资要点 | 相对估值（默认）| 绝对估值 | 财务分析 | 风险提示 | 研报与数据。
- **相对估值 Tab**：
  1. Bear/Base/Bull 情景切换（`st.segmented_control` 或 radio）；
  2. 敏感性热力矩阵：PE × EPS → Plotly heatmap，中心高亮基准格；
     矩阵数据来自现有同行估值输入（不改计算逻辑，仅可视化）；
  3. 估值区间条：三档区间 + 当前价格滑标（HTML/CSS 或 Plotly indicator）；
  4. **假设注册表**：表格化（关键假设 | 基准值 | 区间范围 | 数据来源 | 验证状态），
     来源列放 chip（Wind·投研期 [2024-05-01] → 中文 chip + 悬浮原始 ID）；
  5. Thesis Fragility（投资逻辑脆弱性）：一期做**静态简化版**——假设卡片 +
     箭头连线汇聚到"投资结论"节点（SVG 注入），节点上标 中/高 风险徽章；
     交互拖拽版放二期。
- **Monitoring Plan（跟踪计划）**：右侧卡（可跟踪指标 / 触发条件 / 影响的论断 /
  重新验证），数据来自假设注册表衍生，纯展示。

---

## 6. 实施计划（三阶段）

### P0 — 结构与去噪（预计最先做，收益最大）

| # | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| P0-1 | 导航 13→8+1 重组，演示页收进「高级」 | workbench.py, app_pages/ | 侧栏仅 8 业务项 + 1 折叠组；旧链接可跳转 |
| P0-2 | 顶部上下文条组件 | ui/context_bar.py(新), _shared.py | 每页顶栏一致；徽章随 validation 状态变化 |
| P0-3 | 证据 chip / 状态 chip 组件 | ui/chips.py(新) | chip 悬浮可见完整 ID；明面无裸 ID |
| P0-4 | 全站 ID/英文外露点清理 | ui/cards.py, ui/claim_passport.py, app_pages/* | grep 无明文 snapshot/Claim ID 直出 |
| P0-5 | 卡片网格与布局统一 | ui/layout.py, ui/theme.py | 总览一屏卡片化；间距/圆角统一 |
| P0-6 | 离线回归 | tests/, scripts/smoke_workbench.py | pytest 全绿；smoke 通过 |

### P1 — 图表升级（对齐三图主干视觉）

| # | 任务 | 涉及文件 |
|---|---|---|
| P1-1 | 横向进度 stepper | ui/stepper.py(新), overview.py |
| P1-2 | 健康度 donut + 完整度进度条 | overview.py, ui/charts.py |
| P1-3 | 财务指标 mini-chart 卡 ×3 | overview.py, ui/charts.py |
| P1-4 | Passport 状态表格化 + 主按钮 | ui/claim_passport.py, research_review.py(新) |
| P1-5 | 敏感性热力矩阵 + 估值区间条 + 假设注册表 | valuation.py, ui/charts.py |

### P2 — 高交互组件（二期）

| # | 任务 | 说明 |
|---|---|---|
| P2-1 | PDF 双栏高亮核查器 | pdf.js 自定义组件；一期先 chip→原文片段展开 |
| P2-2 | Thesis Fragility 交互因果图 | 一期先静态 SVG 版 |
| P2-3 | 每日复盘并入业务导航 | 视使用频率决定是否留在高级分组 |
| P2-4 | 「开始新研究」全流程向导 | 贯穿 ①→⑧ 的进度引导 |

---

## 7. 测试与验收

- 每阶段收尾跑（AGENTS.md 标准流程）：

```powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
python scripts/smoke_workbench.py
git diff --check
git status --short
```

- UI 断言（新增离线测试）：
  - 导航注册表快照测试（业务 8 项 + 高级分组）；
  - chip 组件渲染不输出裸 evidence ID 到明面 DOM 的单测（字符串断言）；
  - overview/valuation 页面函数在 demo 快照下可离线渲染（沿用现有 golden 测试模式）。
- 人工验收清单：三张设计稿逐卡对照打勾；1080p 一屏检查；涨红跌绿抽查。

## 8. 风险与回退

| 风险 | 缓解 |
|---|---|
| 导航重组破坏旧入口 | legacy_compat 别名跳转，保留一个版本 |
| chip 悬浮承载 ID 后，审计场景找不到 ID | 详情抽屉/审计回放页仍完整展示全量 ID |
| Streamlit 自定义 HTML 在版本升级时失效 | stepper/chips 全部走 st.markdown 注入 + smoke 测试覆盖 |
| 改造范围蔓延到 src/cn | 约定：任何 PR 触碰 src/cn/ 即视为越界，回退该文件 |

## 9. 分支与提交

- 按惯例：先推 `wip-2026-10-05`（无斜杠）安全网分支，再合主干。
- 每 P0/P1 任务一个 commit，格式 `ui(p0-1): nav regroup 13->8+1`。
