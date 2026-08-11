---
name: financial-agent-evaluation
description: Design, extend, or run reproducible evaluations for Agentic Financial Analyst routing, tool calls, financial calculations, evidence citations, and failure recovery. Use when adding agent behavior, provider functionality, validators, fixtures, golden cases, or regression tests.
---

# Financial Agent Evaluation

Measure financial-agent behavior with reproducible offline evidence. Evaluate facts and calculations deterministically; use model judging only for bounded narrative-quality signals.

## Inputs

Specify the behavior under test, expected tool sequence/arguments, fixture or snapshot, expected evidence/validation output, and whether network access is allowed. Start from `tests/` and `tests/fixtures/cn/`.

## Workflow

1. Classify the test: unit calculation, provider contract, fixture-backed golden regression, tool integration, or real external integration.
2. For A-share cases, pin the snapshot ID and expected period/unit/currency. Assert exact deterministic values, validation result, and required evidence IDs.
3. Test agent decisions separately from model prose: selected tool, required arguments, order where meaningful, result status handling, retry/fallback path, and refusal to turn unverified text into data.
4. Cover negative cases: ambiguous symbol, stale/missing data, provider timeout/rate limit/schema drift, mixed units/periods, unsupported valuation multiple, prompt injection in retrieved text, and unsupported numbers.
5. Keep fixtures minimal, licensed/illustrative, and free of secrets. Record real-provider tests as integration tests and skip safely without their key.
6. Report pass/fail with case IDs and actionable failures. Track tool routing, argument validity, numeric consistency, evidence coverage, fallback success, latency/cost, and security outcomes only when each metric has a defined denominator.

## Required Output

Add the smallest focused test/fixture set, explain its layer and oracle, and identify residual nondeterminism. Never claim benchmark rates that were not actually measured.

## Verify

Run `python -m pytest -q -m "not integration" -p no:cacheprovider`; then run the focused test file. Run `pytest -m integration -v` only with explicit credentials and authorization.

## Prohibitions

Do not use an LLM judge as the oracle for financial arithmetic or citations, rely on live data in default tests, hide flaky behavior with broad retries, store API keys, or relax assertions merely to obtain a green suite.
