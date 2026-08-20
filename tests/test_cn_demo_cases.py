"""Golden demo cases must preserve their real Validator outcomes."""

import json

from src.cn import workbench_service as service
from src.cn.demo_data import BLOCKED_DEMO_SNAPSHOT_ID, DEMO_SNAPSHOT_ID


def test_moutai_demo_case_is_a_reportable_research_success():
    result = service.research_validation(DEMO_SNAPSHOT_ID)

    assert result["status"] in {"pass", "warning"}
    assert result["conclusion_allowed"] is True


def test_missing_total_shares_fixture_is_blocked_and_hides_valuation(tmp_path, monkeypatch):
    source = service.SNAPSHOT_DIR / f"{BLOCKED_DEMO_SNAPSHOT_ID}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    target = tmp_path / source.name
    target.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(service, "SNAPSHOT_DIR", tmp_path)
    service.load_snapshot.cache_clear()

    validation = service.research_validation(payload["snapshot_id"])
    valuation = service.research_valuation(payload["snapshot_id"])

    assert validation["status"] == "blocked"
    assert "key_metrics" in validation["blocked"]
    assert valuation["conclusion_allowed"] is False
    assert valuation["gated_reason"] == "validator_blocked"
    service.load_snapshot.cache_clear()


def test_special_security_and_suspension_status_are_preserved_without_inference(tmp_path):
    payload = {
        "schema_version": "1.0.0", "snapshot_id": "920001.BJ_special_status_v1",
        "provider": "illustrative_fixture", "symbol": "920001.BJ",
        "research_as_of": "2026-08-14T15:00:00+08:00", "fetched_at": "2026-08-14T15:00:00+08:00",
        "data": {"profile": {"name": "*ST 北交所演示", "currency": "CNY", "industry_name": "测试"},
                 "bars": [{"trade_date": "2026-08-14", "open": 10.0, "high": 10.0, "low": 10.0,
                           "close": 10.0, "volume": 0.0, "amount": 0.0, "adjustment": "RAW",
                           "trading_status": "SUSPENDED"}], "statements": []},
    }
    path = tmp_path / "special.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    from src.cn.providers.snapshot import SnapshotProvider
    from src.cn.symbols import normalize_cn_symbol

    bars = SnapshotProvider(path).get_daily_bars(normalize_cn_symbol("920001.BJ"))

    assert str(bars[0].symbol) == "920001.BJ"
    assert bars[0].trading_status == "SUSPENDED"
    assert bars[0].close == 10.0


def test_market_service_exposes_special_security_flags_from_stored_snapshot(tmp_path, monkeypatch):
    payload = {
        "schema_version": "1.0.0", "snapshot_id": "920001.BJ_special_status_v1",
        "provider": "illustrative_fixture", "symbol": "920001.BJ",
        "research_as_of": "2026-08-14T15:00:00+08:00", "fetched_at": "2026-08-14T15:00:00+08:00",
        "data": {"profile": {"name": "*ST 北交所演示", "currency": "CNY", "industry_name": "测试"},
                 "bars": [{"trade_date": "2026-08-14", "open": 10.0, "high": 10.0, "low": 10.0,
                           "close": 10.0, "volume": 0.0, "amount": 0.0, "adjustment": "RAW",
                           "trading_status": "SUSPENDED"}], "statements": []},
    }
    (tmp_path / "special.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(service, "SNAPSHOT_DIR", tmp_path)
    service.load_snapshot.cache_clear()

    flags = service.research_market(payload["snapshot_id"])["security_flags"]

    assert flags == {
        "exchange": "BJ", "beijing_exchange": True, "special_treatment_name_flag": True,
        "latest_trading_status": "SUSPENDED", "latest_trade_date": "2026-08-14",
    }
    service.load_snapshot.cache_clear()
