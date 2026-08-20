# FinTrace-CN

## Goal

Build a trustworthy, A-share-only research agent. Provider facts, deterministic calculations, evidence, and model narrative must remain separate.

## Maintained surface

- api.py: versioned FastAPI research and daily-review API.
- workbench.py: Streamlit interview/demo workbench.
- src/agents/tools/: stable tool contracts; only A-share tools are maintained.
- src/cn/: A-share domain, providers, periods, evidence, valuation, agent state, reports, daily review, and demo data.
- src/llms/: provider-neutral model clients used by real Agent evaluation.
- src/validation/: deterministic financial, report, and conclusion gates.
- tests/: offline unit, contract, golden, API, and Agent evaluation tests.

Do not reintroduce the removed US-equity news/DCF pipeline, Yahoo Finance, crypto, prediction markets, MongoDB, Redis, or legacy supervisor agents.

## Financial-data rules

- Never present LLM text or illustrative fixtures as sourced financial facts.
- Preserve provider/snapshot, cutoff, freshness, evidence IDs, period, currency, unit, and validation.
- Use RAW prices for market-cap and peer-valuation calculations.
- Reject or label missing, partial, stale, mixed-period, mixed-unit, or unsupported data.
- Bound retries and expose fallback/partial states.
- Keep data/, output/, .env, paid data, and copyrighted filings out of Git.

## Verification

Default tests must be offline and independent of local .env, caches, wall-clock time, and network access.

~~~powershell
python -m pytest -q -m "not integration" -p no:cacheprovider
python scripts/smoke_workbench.py
git diff --check
git status --short
~~~

Run integration tests only with explicit credentials and authorization. Dry-run/mock evaluation results must never be presented as real-model performance.
