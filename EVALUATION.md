# FinTrace-CN 评测与消融实验

默认评测在离线环境运行。基准执行器为每个 `BenchmarkCase` 返回真实 `ResearchState`；`BenchmarkRunner.run()` 对工具轨迹评分并写出 `results.json` 与 `results.csv`。

记录一次运行时，`metadata` 至少应包含 `benchmark_version` 和 `snapshot_id`。可通过 `baseline_path` 与 `max_regression` 在指标相对基线下降超过允许绝对值时使构建失败。

`write_ablation_report()` 接收 `direct_llm`、`agent_tools`、`agent_tools_evidence` 和 `agent_tools_evidence_validator` 四类运行的 `results.json`，输出 `ablation.json`、`ablation.csv` 与 `ablation.md`。未实际运行的变体会标记为缺失，基准或快照元数据不一致的运行会被拒绝；系统不会为未执行实验虚构分数。

离线检查：

```powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
```

## 真实离线 Agent 基准

`scripts/run_benchmark.py` 运行受限于 `cn_tools` 的真实 ReAct 工具调用循环，并在 `ResearchState` 中记录 `ToolTrace`、Evidence ID、Validator 输出、成本和最终文本。该流程不调用 Tushare 或网络。为避免意外计费，必须显式指定模型：

```powershell
python scripts/run_benchmark.py --all-snapshots --model deepseek-v4-flash --temperature 0 --max-steps 6 --output output/benchmark/real_offline
```

`--all-snapshots` 会为每份本地快照创建一个行情与证据路由案例（当前为 17 个）。模型、Prompt、温度、最大步数和快照 ID 均记录在 `results.json`；默认案例清单可用 `--list` 查看，但它不是执行模式。

每条结果都嵌入完整 `ResearchState`，包括工具轨迹、Evidence ID、校验、报告和成本轨迹。CSV 用于紧凑指标对比，审计细节应查看 `results.json`。

## 真实 Agent 消融实验

`scripts/run_agent_ablation.py` 在相同模型、Prompt、温度和最大步数下，针对 7 个固定案例运行四种配置：`direct_llm`、`agent_tools`、`agent_tools_evidence`、`agent_tools_evidence_validator`。案例覆盖正常、过期、未来披露、证据缺失、错误代码和行业边界。

Validator 是真实的阻断闸门：校验失败时，Agent 用“无法验证/拒绝结论”替代确定性财务结论。

```powershell
# 零成本、无需 API Key
python scripts/run_agent_ablation.py --dry-run --output output/agent_ablation
python -m pytest tests/test_cn_agent_ablation.py -v -p no:cacheprovider

# 真实模型运行（需要已注册模型）
python scripts/run_agent_ablation.py --model gpt-4o-mini --output output/agent_ablation
```

输出包括 `ablation_results.json`、`ablation_metrics.csv`、`ablation_details.csv` 与 `ablation_report.md`。CI 定义见 `.github/workflows/ablation.yml`。

## Validator 消融与在线冒烟测试

`python scripts/run_ablation.py --output output/ablation/validator_v2` 使用真实快照 `cn_tools`，再注入明确标识的过期、未来和证据缺失故障。评判标准是确定性 Validator 是否接受有效案例并拒绝每个注入故障，而非模型文案是否流畅。

`tests/test_cn_tushare_integration.py` 是 `Router → Tushare → 标准 Schema → EvidenceLedger` 的可选五调用冒烟测试。没有 `TUSHARE_TOKEN` 时会跳过；仅在计划验证付费数据源时，以 `pytest -m integration -v` 运行。

## 确定性结论闸门

完整 Agent 消融变体和 `OfflineCnAgent` 都会在工具循环结束后执行 `ResearchGateValidator`。出现任意工具失败、需要但缺失证据、请求指标缺失、指标在研究截止时间后才可用，或所请求估值方法不适用于该实体类型时，确定性财务结论均会被阻断。

闸门只接受本次成功工具调用实际返回、且已登记在 `ResearchState` 中的 Evidence ID；不会仅凭快照自行补造溯源信息。检查完全依据已捕获的工具轨迹和固定快照元数据，不从模型文案反推需求。
