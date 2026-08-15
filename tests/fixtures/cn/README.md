# Public illustrative A-share fixtures

These files are entirely synthetic, minimal test data—not Tushare exports and
not investment research. They cover consumer, banking, healthcare, and new
energy examples, plus `600519.SH_illustrative_v1.json` for existing regression
tests. They contain no credentials, raw filings, or real market data.

The fixture layer also exercises unavailable disclosures and missing-price error
paths without any network or provider token.

These fixtures are also the snapshot backbone for the **Agent Ablation
Benchmark** (see `data/benchmarks/cn_agent_ablation_v3.json`). Seven fixture
cases — normal, expired, future-disclosure, missing-evidence, wrong-code, and
industry-boundary — are pinned to these local snapshots, making every ablation
invocation deterministic and reproducible across the four model configurations
(`direct_llm`, `agent_tools`, `agent_tools_evidence`,
`agent_tools_evidence_validator`). Run the full benchmark offline with:

```bash
python scripts/run_agent_ablation.py --dry-run --output output/agent_ablation
python -m pytest tests/test_cn_agent_ablation.py -v -p no:cacheprovider
```
