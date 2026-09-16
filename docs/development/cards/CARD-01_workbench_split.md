# CARD-01: Workbench 组件化拆分

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段0 / P0 |
| 对应选题 | 无（工程基建，服务全部选题的演示形态） |
| 依赖 | 无，可独立开工 |
| 状态 | ☐ 未开始 |

## 1. 目标

把 90KB / 1700+ 行的单文件 `workbench.py` 拆分为组件化包，业务逻辑零丢失，入口行为不变。这是消除"项目乱"观感的第一步。

## 2. 背景与现状

- `workbench.py` 为 Streamlit 单体：35+ 个函数平铺，页面分发、样式、任务轮询、渲染全部内联。
- 已有 `scripts/smoke_workbench.py` 冒烟脚本作为行为锚点。
- 风险：不拆分则后续每张卡都要在巨石文件里加代码，回归风险持续放大。

## 3. 目标结构

```text
workbench/
├── __init__.py
├── __main__.py      # python -m streamlit run workbench 等效入口
├── shell.py         # 页面注册与导航（保持现有导航方式）
├── ui.py            # 页头、样式注入、徽章、错误横幅等通用渲染
├── state.py         # st.session_state 读写封装（集中键名常量）
└── pages/           # 按现有页面功能 1:1 映射，不改功能
    ├── overview.py
    ├── snapshots.py
    ├── market_daily.py
    ├── financials.py
    ├── valuation.py
    ├── agent_lab.py
    ├── report_view.py
    ├── evidence_trace.py
    ├── daily_review.py
    └── settings.py
```

注意：pages/ 的实际文件划分**以现状真实页面为准**——动手前先通读 `workbench.py` 列出全部页面入口与共享函数，再确定映射表，写入执行备注。上面是预期形态，不是硬性清单。

## 4. 实施步骤

1. 通读 `workbench.py`，产出"页面 → 函数 → 依赖服务"清单（写入执行备注）。
2. 建 `workbench/` 包骨架，先迁 `ui.py` / `state.py` 中的纯展示与状态工具函数。
3. 按页面逐个迁移：每迁一页立即运行冒烟 + 手动点检该页，再迁下一页。
4. 根目录 `workbench.py` 收缩为兼容薄壳（保留 `streamlit run workbench.py` 与 `scripts/smoke_workbench.py` 两条旧路径可用），或按仓库现状选择直接替换并在脚本中同步更新路径。
5. 清理迁移后不再使用的 import 与死代码。

## 5. 验收标准

- [ ] 根目录 `workbench.py` ≤ 50 行（仅转发），或按仓库约定移除并由脚本承接
- [ ] `workbench/pages/` 每个模块 ≤ 300 行
- [ ] `python scripts/smoke_workbench.py` 通过
- [ ] 全部测试通过（第 10 节命令）
- [ ] 手动逐页对照：原有功能（任务发起、轮询、报告下载、证据展示）无一缺失

## 6. 红线（本卡特有）

- 只拆分不改写业务逻辑：不改 API 调用、任务轮询语义、快照读取路径
- 不引入前端依赖或新框架；沿用现有 Streamlit 版本与组件用法
- 不顺手修 UI 样式问题（记录到执行备注即可）

## 7. 执行备注（agent 填写）

| 日期 | 记录（页面映射表 / 偏差 / 遗留问题） |
|---|---|
|  |  |
