# FinTrace-CN 数据来源与口径

## 默认来源：版本化本地快照

默认测试使用 `tests/fixtures/cn/*.json`，工作台演示由 `src/cn/demo_data.py` 在本地生成到 `data/snapshots/cn/`。生成数据的 Provider 为 `illustrative_fixture`，不代表真实公司价格或财报。真实 Provider 快照只保存在被 Git 忽略的 `data/` 下。

所有快照都必须显示 `snapshot_id`、`research_as_of`、Provider 与 data quality；illustrative 和历史快照均不得冒充实时行情。

## 时点一致性规则

只有 `available_at` 不晚于 `research_as_of` 的财务报表才能参与研究。这一规则避免回测或历史报告使用当时尚未公开的未来信息。

## 价格口径

FinTrace-CN 区分 `RAW`（不复权）、`QFQ`（前复权）和 `HFQ`（后复权）价格。当前市值及同行估值输入使用 RAW 价格；Validator 会拒绝在这些计算中误用复权价格。

## 可选在线 Provider

Tushare 仅在配置 `TUSHARE_TOKEN` 后启用，并通过集成测试验证。在线返回必须经过相同的标准 Schema、溯源与错误处理边界，当前离线演示不会调用 Tushare。

## 限制与数据权利

仓库不包含 API Key、付费原始数据或完整受版权保护的公告文件。Provider 覆盖、字段权限、频率限制和授权条件可能变化；刷新快照时必须保留 Provider、获取时间、字段映射和修订元数据。
