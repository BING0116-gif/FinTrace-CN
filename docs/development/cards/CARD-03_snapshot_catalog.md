# CARD-03: 快照 Catalog 索引

| 属性 | 值 |
|---|---|
| 阶段 / 优先级 | 阶段0 / P1 |
| 对应选题 | 无（工程基建，支撑"数据来源可核验"） |
| 依赖 | 无，可独立开工（与 CARD-01/02 并行） |
| 状态 | ☐ 未开始 |

## 1. 目标

为 `data/snapshots/cn/` 下所有快照建立 SQLite 元数据索引（Catalog），让 demo / live / 错误注入数据分区可见、可查、可核验，替代"靠文件名约定管理"的现状。

## 2. 背景与现状

- 快照目录下 live（tushare/akshare 采集）、illustrative（演示）、demo_missing（错误注入）混放，无统一元数据。
- 讲解与演示时无法快速回答"这份数据哪来的、截止何时、覆盖什么"——竞赛答辩的"数据来源可核验"需要一键出示。

## 3. 设计

### 3.1 索引：`src/cn/snapshot_catalog.py`（新建）

```python
@dataclass
class SnapshotMeta:
    snapshot_id: str        # 目录名
    kind: str              # live | illustrative | demo_missing | demo_stale
    provider: str | None   # tushare / akshare / synthetic
    symbols: list[str]
    as_of: str | None       # 数据截止日
    periods: list[str]      # 覆盖报告期
    coverage: dict          # 各数据域覆盖情况（prices/financials/…）
    path: str
    checksum: str           # 目录内容指纹

class SnapshotCatalog:
    """SQLite 索引 data/catalog.db；提供扫描、查询、导出。"""
    def scan(self, root: str) -> int: ...              # 扫描快照目录重建索引
    def query(self, kind=None, symbol=None, provider=None) -> list[SnapshotMeta]: ...
    def get(self, snapshot_id) -> SnapshotMeta: ...
    def stats(self) -> dict: ...                       # 各 kind 计数，供 workbench 概览页
```

kind 判定规则：从现有快照命名/内部元数据推断（先扫描现状，把判定规则写死在模块顶部的映射表里，写入执行备注）。

### 3.2 CLI 入口

~~~powershell
python -m src.cn.snapshot_catalog scan
python -m src.cn.snapshot_catalog list --kind live
python -m src.cn.snapshot_catalog stats
~~~

### 3.3 展示接入

- `workbench/pages/snapshots.py`（CARD-01 产物；若未完成则先记录待接入点）：快照列表改为从 Catalog 读取，展示 kind / provider / as_of 徽章。

## 4. 实施步骤

1. 扫描真实快照目录结构，确定 kind 判定映射表与字段提取规则（快照内已有元数据优先）。
2. 实现 `SnapshotCatalog`（SQLite，WAL，`data/` 下不入 Git）+ 单测（tmp_path 构造假快照树验证分类与查询）。
3. 实现 CLI 三个子命令。
4. 接入 workbench 快照页（若 CARD-01 未完成，先在本卡测试内验证，接入动作记录为待办）。

## 5. 验收标准

- [ ] `scan` 后 `stats` 输出 live / illustrative / demo 分类计数，与人工点数一致
- [ ] `list --symbol <code>` 能按股票过滤；`get` 返回含 checksum 的完整元数据
- [ ] 单测全部离线（tmp_path 假快照树）
- [ ] 全部测试通过

## 6. 红线（本卡特有）

- Catalog 只读快照内容，不修改任何快照文件
- checksum 只用于展示与核验，不引入内容审查/改写逻辑
- illustrative 快照在任何展示界面必须带"演示数据"徽章，绝不能与 live 混排无标注

## 7. 执行备注（agent 填写）

| 日期 | 记录（kind 判定映射表 / 偏差 / 遗留问题） |
|---|---|
|  |  |
