# DEMO_FLOW.md — 5 分钟比赛 Demo 主故事

> 版本：v3.0 Competition Edition ｜ 2026-09-16
> 本文是 FinTrace-CN 初赛视频与决赛现场的**唯一**演示剧本。CARD-15 的每个页面、CARD-11 的每项指标、CARD-12 的 Evidence Pack，最终都以"能否支撑本剧本"为验收依据。

---

## 0. 演示总原则：演示即证据

1. **只用真实材料**：演示输入必须是真实 A 股年报 PDF + 真实研报草稿（人为注入错误），不得用 synthetic fixtures 演示。
2. **不美化失败**：blocked / failed / warning 状态原样展示。Demo 要证明的不是"系统永远正确"，而是——**"错误的时候，系统知道自己不能下结论"**。
3. **每个数字可回跳**：演示中出现的每一个重要数字，都能点击跳回原始 PDF 页码/表格位置。
4. **不预演 LLM 输出**：解析、提取、计算、核查全部现场执行；LLM 叙事部分允许预先缓存，但 Validator 结果必须现场产生。
5. **离线可复现**：演示环境不依赖外网（数据 snapshot + 本地文档），网络故障不影响剧本走完。

---

## 1. 演示资产准备（Demo 前置条件）

| 资产 | 要求 | 治理 |
|---|---|---|
| `data/demo/annual_report.pdf` | 一家真实 A 股上市公司年度报告（建议制造业，避免金融行业触发 ValuationApplicabilityGate 降级，除非刻意展示） | 存 `data/`（gitignore），登记 sha256 + 下载来源 + 下载日期；**必须文本型 PDF**（扫描版 OCR 不可用→Demo 降级，预检） |
| `data/demo/report_draft.md` | 同一公司的"研报草稿"，**人为注入至少 8 处错误**（见 §2 错误清单） | 自建内容可入 Git；引用的年报数字必须与 PDF 一致 |
| snapshot | 演示公司对应的行情/股本 snapshot | 入 `tests/fixtures/` 或 `data/`，run manifest 记录 snapshot_id |
| 备份 run | 提前一天完成的完整彩排 run（含全部产物） | 本地保存 Evidence Pack zip + 录屏视频，**现场故障时切换展示** |

**含错研报草稿的 8 处注入清单**（编写草稿时逐项登记，彩排时逐项核对系统是否检出）：

| # | 错误类型 | 示例设计 | 预期系统行为 |
|---|---|---|---|
| E1 | numeric_error | 营业收入写 35.2 亿元（实际 32.6 亿） | checker 定位 + 给出正确值 + 跳原文页 |
| E2 | unit_error | 净利润 3.1 亿元写成 31,000 万元口径混用错误 | unit checker 报错 |
| E3 | calculation_error | 直接用 H1 累计值算 Q2 QoQ（YTD 未转单季） | 系统展示正确单季换算过程 |
| E4 | valuation_multiple_error | 目标 PE 用了银行业可比值 | ValuationApplicabilityGate / multiple 校验 |
| E5 | wrong_citation | 引用"年报第 45 页"（实际在第 118 页） | wrong_page 检出 + 跳正确页 |
| E6 | stale_citation | 引用上一年度旧披露值 | revision/staleness 检出 |
| E7 | unsupported_causal_claim | "利润增长主要因海外订单放量"（年报无此表述，证据不足） | 标记 unsupported，要求 evidence 绑定 |
| E8 | scope_error | 母公司口径数据当成合并口径使用 | scope checker 报错 |

---

## 2. 5 分钟主故事（11 步）

> 总时长 300 秒。列"评委看到什么"与"话术要点"。所有页面见 CARD-15 页面清单。

### 延迟预案（必彩排实测，解决 H7 点）

| 步骤 | 真实耗时 | 展示策略 | 话术 |
|---|---|---|---|
| ①② 上传 | ≈30s | **预 ingest 缓存命中**（DocumentRegistry 按 sha256 秒级返回已注册文档） | "这个 PDF 我昨天已经上传过，Registry 记录了 sha256 和解析结果——同输入同配置不会重解析，这就是可复现性的第一步。" |
| ③④ 解析+提取 | 200页PDF≈1–3min / 长草稿LLM≈30–90s | **快进展示缓存**（Events 页展示缓存 run 的事件流；若必须现场跑 LLM，只展示草稿提取） | "解析用 pdfplumber 定位，每个事实带 page/bbox——今天这份文档我昨天已经完整 ingest 过，秒级出结果；换一份新 PDF 也能跑，只是需要一点时间。" |
| ⑤ 财务分析 | ≈10s | 实时 | 快 |
| ⑥⑦ 研报纠错 | ≈30s | 实时展示预 ingest 的草稿提取结果 + 现场确定性核查 | "LLM 只做一件事：把自然语言句子结构化成 Claim。之后全部由确定性 Checker 判断——错误类型、原始值、正确值、证据、建议。" |
| ⑧ 估值 | ≈10s | 实时 | 快 |
| ⑨⑩ 备忘录 | ≈30–60s LLM / ≈5s 模板 | 缓存命中；或展示预生成版本 | "备忘录 11 段，每一句都有三级标注。" |
| ⑪ 删证据阻断 | ≈15s | 实时 | 快 |

**彩排验收**：全剧本（含预 ingest 命中）必须实测 < 5 分钟（含话术）。任何超 5 分钟的步骤必须精简——**可以剪掉⑧估值环节（已在纠错环节展示了 CARD-02/03），保留①②③④⑤⑥⑦⑨⑩⑪**，把估值挪到答辩追问环节。

### 开场（0:00–0:25）｜Upload Task 页

**步骤 1+2**：上传真实年报 PDF；上传含错研报草稿。

- 话术："FinTrace-CN 是面向 A 股投研的**可验证金融智能体**。今天演示两个输入：一份真实年报，一份故意写了 8 处错误的研报草稿。"
- 评委看到：DocumentRegistry 登记 document_id / sha256 / parser 版本（上传即入账，执行轨迹页可查）。

### 解析与提取（0:25–0:55）｜Execution Trace 页（快进展示）

**步骤 3+4**：系统解析 PDF 与财务表格，自动提取收入、利润、现金流指标。

- 话术："解析用 pdfplumber 定位到页和表格坐标，每个事实记录 page/bbox/单位/期间/口径，不是一段无来源的文本。"
- 评委看到：事件流按时间顺序滚出 parse → extract → normalize，每条事件可展开 input/output。

### 财务分析（0:55–1:35）｜Financial Analysis 页

**步骤 5**：计算 YoY、**单季度 QoQ**、盈利质量指标。

- 话术（核心金融专业性 40 秒）："A 股利润表披露的是 YTD 累计值。Q1 100、H1 230、Q3 累计 390、全年 540——系统先做确定性单季换算得到 100/130/160/150，再算 QoQ。直接对累计值算环比是常见错误。"
- 评委看到：指标表可展开公式与 Evidence；若有扣非/口径问题，可比性横幅（CARD-04）原样显示。

### 研报纠错（1:35–2:35）｜Report Corrections 页 ★高潮一

**步骤 6+7**：检测草稿中的错误数字、错误单位、错误同比、错误估值倍数、错误引用、无证据因果推断；点击错误跳转原始 PDF 页。

- 话术："LLM 只做一件事：把自然语言句子结构化成 Claim。之后全部由确定性 Checker 判断对错——错误类型、原始值、正确值、证据、建议修改。"
- 现场操作：逐条点开 2–3 处错误（优先 E1 数字错、E3 YTD 环比错、E7 无证据因果），**点击跳转 PDF 第 N 页**。
- 评委看到：8 处错误全部检出，每处给出 Evidence ID 与修改建议。

### 估值（2:35–3:05）｜Valuation 页

**步骤 8**：生成相对估值与敏感性分析。

- 话术："Bear/Base/Bull 三档假设全部进 Assumption Registry，EPS×PE 敏感性矩阵每个格子可追溯到数据→公式→假设→输出。DCF 区间不做交并集拼凑，分别展示并报告方法间 dispersion。"
- 评委看到：区间条 + 矩阵 + 假设展开（含来源与理由）。

### 投资备忘录（3:05–3:45）｜Investment Memo 页 ★高潮二

**步骤 9+10**：生成 Investment Memo；点击任一结论展示 Claim→Calculation→Evidence→PDF Page。

- 话术："备忘录每一句话都有三级标注：fact 绑定证据，inference 标注依赖哪些 fact，opinion 标注假设来源。系统不把推论冒充事实。"
- 现场操作：点击"盈利质量下降"结论 → 图谱逐层展开：Claim C18 → CFO/NI 计算 CAL12 → Evidence E51/E37 → 年报 P118/P96（与 CARD-09 示例一致）。
- 评委看到：Claim-Evidence Graph 页的结论回溯链。

### 终极证据（3:45–4:15）｜Validator 页 ★高潮三

**步骤 11（剧本终点）**：人为删除一个关键 Evidence → 系统 Validator 阻断对应结论。

- 话术："最后 30 秒是 FinTrace 的核心承诺。我现在删掉支撑'盈利质量下降'的关键证据——Validator 立即把该 Claim 置为 invalid，备忘录中对应结论被阻断而不是悄悄保留。**错误的时候知道自己不能下结论，这才是可验证。**"

### 收尾（4:15–5:00）｜Audit Replay + Export 页

- 话术："整个 run 的 manifest 记录了模型、prompt hash、parser 版本、git commit、snapshot——同一输入同一配置可重放。最后导出 Evidence Pack：报告、claims、evidence、calculations、events 全量打包，评委可离线复核。"
- 现场操作：Audit Replay 选当前 run_id 展示时间线 → 点击 Export Evidence Pack 导出 zip。

---

## 3. 失败注入场景（决赛现场 / 答辩加分环节）

> 初赛视频结尾可放 1–2 个；决赛现场作为"评委挑战环节"主动邀请评委选题。目标：证明系统在异常输入下 fail-closed，而非静默出错。剧本见 CARD-12 §4。

| # | 注入操作 | 预期行为 |
|---|---|---|
| F1 | 删除总股本数据 | 阻断每股估值（block，不猜股本） |
| F2 | 删除 PDF 某页 | citation incomplete 警告，受影响 Claim 降级 |
| F3 | 单位从万元改成亿元 | unit checker 报错，计算中止 |
| F4 | 研报给出错误同比 | report checker 定位到句 + 给出正确值 |
| F5 | 旧财报 + 更正公告同时在场 | Source Conflict Resolver 展示冲突记录，不静默覆盖 |
| F6 | 删除某关键 Evidence | Claim invalid，Validator 阻断（即主故事步骤 11） |
| F7 | 改写为无证据因果结论 | 标记 unsupported causal inference，要求绑定证据 |

**挑战环节话术**："各位评委可以任选一个场景，或者现场给我一个更刁难的输入——如果系统不知道自己错了还硬给结论，那才是失败。"

---

## 5. 现场保障清单

- [ ] 演示机离线冒烟通过（snapshot + 本地文档 + 缓存 LLM 叙事路径）
- [ ] 备份：昨日彩排 run 的 Evidence Pack zip + 录屏视频（极端故障时播放）
- [ ] `python scripts/smoke_workbench.py` 演示前当天运行通过
- [ ] 含错草稿 8 处错误检出率彩排核对（8/8 检出方可上台）
- [ ] 浏览器控制台零报错（CARD-15 验收硬项）
- [ ] PDF 页码跳转逐条核对（E1/E3/E5/E7 四处必点）

**断网演示预案**（专项7 场景）：现场网络故障时切换——①展示"离线模式"徽章（manifest 的 `execution_mode="offline"`）；②所有确定性环节（解析/归一化/分析/核查）走本地缓存与预 ingest 结果；③LLM 环节（提取/叙述段）若不可用则展示预生成版本并显式标注"cached offline run"；④话术："FinTrace 的确定性层全部本地可跑；LLM 环节断网时用预缓存——评审环境装好后可以从零 ingest 一份新 PDF 体验完整链路。"

## 6. 答辩高频问题预演

| 评委问题 | 回答要点 |
|---|---|
| 和普通 RAG 投研助手区别？ | chunk≠evidence；LLM 不做财务算术；fact/inference/opinion 三级区分；fail-closed Validator |
| 数字错了怎么办？ | 现场演示 F6：删证据→阻断。错误自知是设计目标不是缺陷。 |
| 为什么不用多 Agent？ | 主链 Planner→Tools→Evidence→Validator→Memo 已闭环；Multi-Agent 是 P2 且必须过消融四问（CARD-18）。 |
| 结果可复现吗？ | Run Manifest 17 字段 + Audit Replay + Evidence Pack 离线重放。 |
| 数据准确性怎么保证？ | benchmark 三级测试集 + 24 指标（CARD-11），阈值待 baseline 冻结，不编数字。 |

## 6. 验收

- [ ] 全剧本 5±0.5 分钟彩排 ≥3 次零卡点
- [ ] 初赛视频按本剧本拍摄（可剪辑加速解析过程，不得剪掉错误检出与 Validator 阻断）
- [ ] 任何对本剧本的修改必须同步更新 CARD-15 页面清单
