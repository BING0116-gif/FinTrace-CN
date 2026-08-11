from src.cn.peer_workflow import PeerCandidate, value_with_peers
from src.cn.valuation import PeerValuationInput


def candidate(symbol, profit=10, *, industry="BAIJIU", period="2025FY", bank=False):
    return PeerCandidate(
        valuation=PeerValuationInput(symbol, 10, 10, profit, 100, 200, period),
        industry_code=industry,
        evidence_ids={"price": "p", "shares": "s", "profit": "n", "equity": "e", "revenue": "r"},
        is_bank_or_insurer=bank,
    )


def test_workflow_records_selection_reason_and_deterministic_implied_price():
    target = candidate("TARGET", profit=20)
    result = value_with_peers(target, [candidate("A"), candidate("B", profit=5), candidate("OTHER", industry="BANK")])

    assert [item.reason for item in result.decisions] == ["same_industry_same_period", "same_industry_same_period", "industry_mismatch"]
    assert result.multiples["PE"]["median"] == 15
    assert result.multiples["PE"]["implied_price"] == 30
    assert result.validation["valid"]
    assert "peer_count_below_4_low_confidence" in result.validation["warnings"]


def test_bank_matrix_disables_ps_and_missing_evidence_is_rejected():
    target = candidate("BANK", bank=True)
    peer = candidate("P", bank=True)
    peer = PeerCandidate(peer.valuation, peer.industry_code, evidence_ids={}, is_bank_or_insurer=True)
    result = value_with_peers(target, [peer])

    assert set(result.multiples) == {"PE", "PB"}
    assert result.decisions[0].reason == "missing_evidence_ids"
