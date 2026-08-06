# Third-Party Notices

## Upstream Source

This project is a secondary development (fork) of **Agentic-Analyst/stock-analyst**:

- Upstream repository: https://github.com/Agentic-Analyst/stock-analyst
- Upstream author: Zanwen Fu, VYNN AI (https://vynnai.com)

## License History & Attribution

The upstream project has gone through several license changes. This fork's
licensing stance is documented below for transparency and compliance.

| Stage | License | Notes |
|-------|---------|-------|
| At fork base (commit `2091412`) | Apache License 2.0 | The code this fork's DeepSeek work was built upon. Copyright 2026 Zanwen Fu. |
| Upstream later relicensed to | PolyForm Noncommercial 1.0.0 | Upstream commits `f03e175` / `f15ffbf` tightened the license. |
| Upstream final state (`f15ffbf`) | VYNN AI Proprietary — All Rights Reserved | The 12 upstream commits pulled during batch-4 sync brought this in. |

**This fork (FinTrace-CN) restores and maintains the Apache License 2.0**
in its `LICENSE` file, consistent with the license under which the fork base
was originally obtained. The `LICENSE` file in this repository is the Apache
2.0 text from the fork base.

> **Compliance note:** Portions of the upstream code added *after* the
> Apache-2.0 base (the 12 commits synced in batch 4: crypto support, live
> charts, prompt-injection hardening, yfinance retry/fallback) were
> contributed by upstream under its later (PolyForm Noncommercial /
> proprietary) terms. Those portions are used here for **non-commercial,
> educational, and personal-portfolio purposes** (AI internship
> demonstration). Anyone intending commercial use must re-verify the
> upstream license terms and obtain appropriate permissions.

## Third-Party Dependencies

This project uses the following third-party libraries (see `requirements.txt`
for full versions). Each is licensed under its own terms:

| Dependency | Purpose | License |
|------------|---------|---------|
| `openai` | OpenAI-compatible LLM client (also used for DeepSeek) | Apache 2.0 / MIT |
| `anthropic` | Anthropic Claude LLM client | MIT |
| `yfinance` | Market data (prices, technicals) — keyless data tools | Apache 2.0 |
| `python-dotenv` | `.env` environment variable loading | BSD-3-Clause |
| `pandas` / `numpy` | Data manipulation & numerical computation | BSD-3-Clause |
| `openpyxl` | Excel report generation | MIT |
| `requests` | HTTP client for scraping | Apache 2.0 |
| `pytest` / `pytest-asyncio` | Testing framework | MIT |

Data sources (not software dependencies, but attributed per the project's
verifiable-research goals): yfinance (Yahoo Finance), FRED (Federal Reserve
Economic Data), SerpAPI (news search), DeepSeek / OpenAI / Anthropic LLM APIs.
