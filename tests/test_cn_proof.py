from dataclasses import replace

from src.cn.graph import Claim, ClaimGraph, Calculation, build_graph
from src.cn.proof import FinancialProofObject, build_financial_proof_object, verify_claim, verify_fpo

def base(**changes):
    payload = dict(
        claim_id="c1", claim_type="fact", claim_text="收入为 3", economic_period="2024FY",
        scope="consolidated", source_proof={"document_id": "d1", "evidence_ids": ["e1"], "evidence": {"e1": {"status": "active", "period": "2024FY", "scope": "consolidated", "unit": "CNY", "currency": "CNY"}}},
        accounting_context={"period": "2024FY", "scope": "consolidated", "unit": "CNY", "currency": "CNY"},
        calculation_proof={"formula": "input_0 + input_1", "inputs": [{"ref": "e1", "value": 1, "period": "2024FY", "scope": "consolidated", "unit": "CNY", "currency": "CNY"}, {"ref": "e2", "value": 2, "period": "2024FY", "scope": "consolidated", "unit": "CNY", "currency": "CNY"}], "output": {"value": 3}},
        assumption_proof={}, dependency_proof={}, validation_proof={"result": "pass"}, integrity_proof={"run_id": "r1"},
    )
    payload.update(changes)
    return FinancialProofObject(**payload)

def test_verified_and_hash_are_deterministic():
    proof = base()
    assert proof.object_hash() == proof.object_hash()
    result = verify_fpo(proof)
    assert result.overall_status == "VERIFIED"
    assert all(item["status"] in {"pass", "skipped"} for item in result.checks)

def test_five_states_are_discrete_and_fail_closed():
    assert verify_fpo(base(assumption_proof={"assumptions": [{"id": "a1", "status": "expired"}]})).overall_status == "DEGRADED"
    stale_source = {**base().source_proof, "evidence": {"e1": {"status": "superseded"}}}
    assert verify_fpo(base(source_proof=stale_source)).overall_status == "STALE"
    assert verify_fpo(base(source_proof={"document_id": "d1", "evidence_ids": ["missing"], "evidence": {}})).overall_status == "BLOCKED"
    conflict_source = {**base().source_proof, "evidence": {"e1": {"status": "unresolved"}}}
    assert verify_fpo(base(source_proof=conflict_source)).overall_status == "CONFLICTED"

def test_verify_claim_rebuilds_passport_without_llm():
    graph = build_graph("r1", claims=[Claim("c1", "fact", "historical", "收入为 3", ["e1"], ["cal1"], validation_status="supported")], calculations=[Calculation("cal1", "input_0", "1", [{"ref": "e1", "value": 1}], {"value": 1}, "test", "supported")], evidence_index={"e1": {"status": "active", "period": "2024FY", "scope": "consolidated", "unit": "CNY", "currency": "CNY"}})
    proof = build_financial_proof_object("c1", "r1")
    assert proof.claim_id == "c1"
    result = verify_claim("c1", "r1")
    assert result.overall_status in {"VERIFIED", "DEGRADED"}
