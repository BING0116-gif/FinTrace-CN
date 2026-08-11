# FinTrace-CN Evaluation

Default evaluation is offline. A benchmark executor returns one real
`ResearchState` per `BenchmarkCase`; `BenchmarkRunner.run()` scores its
`tool_trace` and writes `results.json` and `results.csv`.

Pass `metadata` with at least `benchmark_version` and `snapshot_id` when
capturing a run. Use `baseline_path` plus `max_regression` to fail a build if a
metric drops more than its allowed absolute amount.

Use `write_ablation_report()` with the captured `results.json` payloads for
`direct_llm`, `agent_tools`, `agent_tools_evidence`, and
`agent_tools_evidence_validator`. It produces `ablation.json`, `ablation.csv`,
and `ablation.md`, marks unmeasured variants as missing, and rejects runs whose
benchmark or snapshot metadata disagree. It never invents a score for an
unexecuted variant.

Run the offline checks with:

```powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
```
