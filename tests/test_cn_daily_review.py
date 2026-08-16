"""Offline unit tests for the daily review schema / provider / analysis / gate.

These mirror ``tests/test_cn_snapshot_provider.py``: they never touch the
network, never consume an API budget, and assert the offline-first contract,
including the explicit ``synthetic_demo`` flag and the gate behaviour.
"""

from __future__ import annotations

import pytest

from src.cn.daily_review import analysis, collector, schema
from src.cn.daily_review.gate import review_gate
from src.cn.daily_review.provider import DailyReviewSnapshotProvider
from src.cn.errors import EmptyDataError


REVIEW_DATE = "20260814"


@pytest.fixture
def payload() -> dict:
    return collector.collect_daily_review(REVIEW_DATE)


@pytest.fixture
def snapshot(payload) -> schema.MarketReviewSnapshot:
    return DailyReviewSnapshotProvider.from_payload(payload).snapshot


def test_collector_offline_is_flagged_synthetic_and_never_live():
    p = collector.collect_daily_review(REVIEW_DATE)
    assert p["provider"] == schema.SYNTHETIC_PROVIDER
    assert p["source_metadata"]["synthetic_demo"] is True
    assert p["data_quality"] == schema.SYNTHETIC_DATA_QUALITY
    # Live without a token must fall back to the flagged offline snapshot.
    p2 = collector.collect_daily_review(REVIEW_DATE, token=None, live=True)
    assert p2["source_metadata"]["synthetic_demo"] is True


def test_schema_rejects_payload_missing_required_fields():
    with pytest.raises(EmptyDataError):
        schema.MarketReviewSnapshot.from_payload({"snapshot_id": "x"})


def test_provider_loads_typed_entities_and_flags_synthetic(payload):
    provider = DailyReviewSnapshotProvider.from_payload(payload)
    assert provider.is_synthetic_demo() is True
    assert len(provider.get_indices()) == 9
    assert len(provider.get_sectors()) == 12
    assert provider.get_breadth() is not None
    assert len(provider.get_limit_up()) == 8
    assert len(provider.get_money_flow()) == 8
    assert len(provider.get_hotspots()) == 5
    # Evidence ids are present on every datum.
    assert all(i.evidence_id for i in provider.get_indices())
    assert all(s.evidence_id for s in provider.get_sectors())


def test_panorama_review_has_eight_sections_and_evidence(snapshot):
    result = analysis.panorama_review(snapshot)
    assert set(result["sections"]) == {
        "index_closing", "market_characteristics", "stock_dynamics", "core_drivers",
        "leaders_laggards", "deviation_review", "next_day_inference", "macro_snapshot",
    }
    assert len(result["evidence_records"]) > 0
    assert result["is_synthetic_demo"] is True
    # Deterministic, evidence-backed conclusions are allowed for the demo artifact...
    assert result["conclusion_allowed"] is True
    # ...but a next-day forecast cannot be supported by an offline snapshot.
    assert result["sections"]["next_day_inference"]["supported"] is False
    assert result["sections"]["next_day_inference"]["status"] == "未覆盖"
    assert result["sections"]["macro_snapshot"]["status"] == "未覆盖"
    # Deviation review is a deterministic observation, not a fabricated conclusion.
    assert result["sections"]["deviation_review"]["supported"] is True


def test_hotspot_review_has_six_sections(snapshot):
    result = analysis.hotspot_review(snapshot)
    assert set(result["sections"]) == {
        "market_overview", "sector_5d", "hot_sectors",
        "top_amount", "top_net_inflow", "top_10d_gainers",
    }
    # 5-day and 10-day series are not available from a single offline snapshot.
    assert result["sections"]["sector_5d"]["status"] == "未覆盖"
    assert result["sections"]["top_10d_gainers"]["status"] == "未覆盖"
    assert len(result["sections"]["hot_sectors"]["items"]) > 0


def test_gate_blocks_on_missing_indices():
    bad = collector.collect_daily_review(REVIEW_DATE)
    bad["data"] = {k: v for k, v in bad["data"].items() if k != "indices"}
    snap = schema.MarketReviewSnapshot.from_payload(bad)
    gate = review_gate(snap)
    assert gate.status == "blocked"
    assert gate.conclusion_allowed is False
    assert "missing_indices" in gate.errors


def test_gate_blocks_on_invalid_timestamp():
    bad = collector.collect_daily_review(REVIEW_DATE)
    bad["research_as_of"] = "not-a-timestamp"
    snap = schema.MarketReviewSnapshot.from_payload(bad)
    gate = review_gate(snap)
    assert gate.status == "blocked"
    assert "invalid_research_as_of" in gate.errors


def test_gate_warns_but_allows_for_synthetic_demo(snapshot):
    gate = review_gate(snapshot)
    assert gate.is_synthetic is True
    assert "synthetic_demo" in gate.warnings
    assert gate.status == "warning"
    assert gate.conclusion_allowed is True


def test_analysis_is_deterministic(snapshot):
    a = analysis.panorama_review(snapshot)
    b = analysis.panorama_review(snapshot)
    assert a == b


def test_load_tushare_token_from_env(monkeypatch, tmp_path):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(collector, "_project_root", lambda: tmp_path)  # no .env here
    assert collector.load_tushare_token() is None
    monkeypatch.setenv("TUSHARE_TOKEN", "dummy-token")
    assert collector.load_tushare_token() == "dummy-token"


def test_collect_live_without_token_falls_back(monkeypatch):
    # No token discoverable -> live attempt must gracefully return the offline demo.
    monkeypatch.setattr(collector, "load_tushare_token", lambda: None)
    out = collector.collect_daily_review(REVIEW_DATE, live=True)
    assert out["source_metadata"]["synthetic_demo"] is True


def test_collect_offline_flags_do_not_raise():
    out = collector.collect_daily_review(REVIEW_DATE, live=False, use_cache=False, force_refresh=True)
    assert out["source_metadata"]["synthetic_demo"] is True


def test_live_cache_reuse_returns_cached_payload(monkeypatch, tmp_path):
    import json as _json

    cache_file = tmp_path / "MARKET_20260814_tushare_v1.json"
    cached = collector.collect_daily_review(REVIEW_DATE)
    cached["provider"] = "tushare"
    cached["source_metadata"] = {"synthetic_demo": False, "live_attempted": True}
    cache_file.write_text(_json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr(collector, "_live_cache_path", lambda d: cache_file)

    out = collector.collect_daily_review(REVIEW_DATE, token="x", live=True)
    assert out["source_metadata"]["synthetic_demo"] is False
    assert out["source_metadata"].get("cached") is True
