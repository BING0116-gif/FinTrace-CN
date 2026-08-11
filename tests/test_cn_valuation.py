from src.cn.valuation import PeerValuationInput, implied_price, summarize_peer_multiple


def peer(symbol, earnings, equity=100, revenue=200, price=10, shares=10):
    return PeerValuationInput(
        symbol=symbol, raw_price=price, total_shares=shares, net_profit=earnings,
        book_equity=equity, revenue=revenue, period_basis="2025FY",
    )


def test_peer_pe_excludes_loss_makers_and_computes_median():
    summary = summarize_peer_multiple([peer("A", 10), peer("B", 5), peer("LOSS", -1)], "PE")
    assert summary.median == 15
    assert summary.included_symbols == ["A", "B"]
    assert summary.excluded["LOSS"] == "non_positive_PE_denominator"
    assert summary.confidence == "low"


def test_iqr_outlier_is_excluded_only_with_sufficient_sample_size():
    peers = [
        peer("A", 10), peer("B", 10), peer("C", 10),
        peer("D", 10), peer("E", 10), peer("F", 10),
        peer("OUTLIER", 0.1),
    ]
    summary = summarize_peer_multiple(peers, "PE")
    assert summary.excluded["OUTLIER"] == "iqr_outlier"
    assert summary.included_symbols == ["A", "B", "C", "D", "E", "F"]


def test_implied_price_uses_per_share_math():
    summary = summarize_peer_multiple([peer("A", 10), peer("B", 10, price=20)], "PE")
    target = peer("TARGET", 20, shares=10)
    assert implied_price(target, multiple=summary, denominator="net_profit") == 30
