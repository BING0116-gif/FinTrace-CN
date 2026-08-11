---
name: financial-data-provenance
description: Change or review financial data ingestion, calculations, cache/retry behavior, citations, or report facts in Agentic Financial Analyst. Use when editing `src/cn/`, market-data tools, providers, financial scraping, valuation, evidence ledgers, or data-source fallbacks.
---

# Financial Data Provenance

Preserve the boundary between sourced facts, deterministic calculations, and model narrative. The deliverable is a traceable result or an explicit, typed failure—not plausible invented financial data.

## Inputs

Identify the user-facing fact or calculation, its provider/snapshot, reporting period, currency and unit. Read the affected provider, domain model, evidence/validator code, and its offline tests before editing.

## Workflow

1. Map each output field to one of: provider fact, deterministic calculation, or LLM narrative. Do not let a narrative create or alter a fact.
2. Preserve `schema_version`, `snapshot_id`, provider name, `fetched_at`, source URL when available, and evidence IDs. For A-share snapshot answers, disclose the snapshot ID and cutoff; never call it live data.
3. Normalize symbol, period basis (FY/quarter/TTM), currency, and scale before calculating. Reject or warn on mixed periods, currencies, or units.
4. Use provider-neutral contracts in `src/cn/providers/`; keep offline snapshots reproducible. Treat provider field changes, empty data, timeout, rate limit, and stale data as tested states.
5. Add bounded retry/backoff only for transient failures; make fallback order explicit. Cache successful provider responses with provenance, and never silently replace a failed source with model-generated values.
6. Recalculate reported ratios and per-share values in code. Preserve validation errors/warnings and citation coverage in the returned result.

## Required Output

State source/snapshot, cutoff, data freshness, fallback used (if any), evidence coverage, and validation outcome. Add or update focused offline tests with fixtures; mark any real network/key test with `@pytest.mark.integration`.

## Verify

Run the affected `tests/test_cn_*.py` files, then `python -m pytest -q -m "not integration" -p no:cacheprovider`. For a new provider, prove its contract using the same fixture inputs as the snapshot provider.

## Prohibitions

Do not fabricate missing prices, financials, citations, source URLs, or fallback success. Do not mix A-share snapshot data with Yahoo data. Do not weaken a validator, hide stale/partial status, commit credentials, or place paid/raw copyrighted filings in the repository.
