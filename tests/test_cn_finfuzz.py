from src.cn.checker import DraftClaim, check_report
from src.cn.finfuzz import MutationOperators, MutationResult, MutationSpec, compute_metrics, generate_mutation_specs, run_finfuzz, run_suite

BASE = {"claim_id": "c1", "sentence": "公司2025年营收120元", "metric": "revenue", "period": "2025FY", "value": 120, "unit": "元", "growth": 20, "source_reference": "f_rev_2025", "claim_type": "factual", "scope": "consolidated"}
FACTS = [{"fact_id": "f_rev_2024", "metric": "revenue", "value": 100, "unit": "CNY", "fiscal_period": "2024FY", "scope": "consolidated", "version": "AS_REPORTED"}, {"fact_id": "f_rev_2025", "metric": "revenue", "value": 120, "unit": "CNY", "fiscal_period": "2025FY", "scope": "consolidated", "version": "AS_REPORTED"}]

def checker(claim):
    return check_report([DraftClaim(**{key: value for key, value in claim.items() if key in DraftClaim.__dataclass_fields__})], FACTS)

def test_all_ten_mutation_operators_are_deterministic_and_seed_reproducible():
    operators = list(MutationOperators)
    first = generate_mutation_specs([BASE], operators, seed=42)
    second = generate_mutation_specs([BASE], operators, seed=42)
    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert {item.operator for item in first} == {item.value for item in operators}
    assert first[0].source_claim != first[0].mutated_claim

def test_suite_separates_extractor_failure_from_checker_miss():
    specs = generate_mutation_specs([BASE], [MutationOperators.NUMERIC, MutationOperators.CAUSAL])
    results = run_suite(specs, {"checker": checker})
    assert all(result.detected for result in results)
    failed = run_suite(specs[:1], {"checker": lambda _: {"extractor_failed": True}})[0]
    assert failed.extractor_failed and not failed.detected

def test_metrics_keep_negative_samples_and_per_type_denominators():
    specs = [MutationSpec("p", "numeric", BASE, {**BASE, "value": 130}, "changed", True), MutationSpec("n", "numeric", BASE, BASE, "no-op", False)]
    results = [MutationResult(specs[0], "checker", True, 0, "numeric_error"), MutationResult(specs[1], "checker", True, 0, "numeric_error")]
    report = compute_metrics(results)
    assert report.overall["precision"] == 0.5
    assert report.overall["recall"] == 1.0
    assert report.overall["false_positive_rate"] == 1.0
    assert report.per_error_type["numeric"]["n"] == 1

def test_run_finfuzz_reports_unmeasured_holdout_as_empty_not_fake_score():
    report = run_finfuzz("offline-suite", [BASE], [MutationOperators.NUMERIC], {"checker": checker})
    assert report.suite_id == "offline-suite"
    assert report.baseline_holdout == {}
    assert report.seed == 42
