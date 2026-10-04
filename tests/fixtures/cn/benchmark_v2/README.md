# cn_agent_v2 datasets

`synthetic.json` is the only checked-in fixture. It contains illustrative,
licensed-free cases and is the default offline split. Real and holdout
materials are intentionally kept outside Git under `data/benchmark_real/` and
must be supplied with a documented SHA-256 manifest before running an
integration benchmark. The loader rejects a real/holdout file marked as an
offline fixture, preventing accidental mixing or fabricated scores.

Truth rows use the stable fields `document_id`, `metric`, `period`,
`expected_value`, `unit`, `scope`, and `page`. A missing observation is
reported as `N/A`; no target rate is inserted before a run.
