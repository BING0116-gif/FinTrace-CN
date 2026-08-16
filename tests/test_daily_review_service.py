"""Offline contract tests for the daily review service layer and HTTP API.

Mirrors ``tests/test_workbench_api.py``: no network, no API budget, and the new
endpoints reuse the same ``ApiEnvelope`` contract as the existing research API.
The market snapshot directory is redirected to a temp dir so the tests never
depend on (or mutate) the committed offline demo snapshot.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.cn import workbench_service as service
from src.cn.daily_review.collector import collect_daily_review, write_market_snapshot

import api

client = TestClient(api.app)
REVIEW_DATE = "20260814"
SNAPSHOT_ID = "MARKET_20260814_synthetic_demo_v1"


@pytest.fixture
def market_dir(tmp_path, monkeypatch):
    directory = tmp_path / "market"
    monkeypatch.setattr(service, "MARKET_SNAPSHOT_DIR", directory)
    monkeypatch.setattr(api.service, "MARKET_SNAPSHOT_DIR", directory)
    write_market_snapshot(collect_daily_review(REVIEW_DATE), directory)
    return directory


# --- service layer ---------------------------------------------------------
def test_list_daily_reviews_finds_snapshot(market_dir):
    items = service.list_daily_reviews()
    assert len(items) == 1
    assert items[0]["id"] == SNAPSHOT_ID
    assert items[0]["synthetic_demo"] is True


def test_daily_review_summary(market_dir):
    summary = service.daily_review_summary(SNAPSHOT_ID)
    assert summary["is_synthetic_demo"] is True
    assert summary["index_count"] == 9
    assert summary["breadth"]["up_count"] == 2987
    assert summary["validation"]["conclusion_allowed"] is True


def test_daily_review_detail_paths(market_dir):
    pano = service.daily_review_detail(SNAPSHOT_ID, "panorama")
    hot = service.daily_review_detail(SNAPSHOT_ID, "hotspots")
    assert len(pano["sections"]) == 8
    assert len(hot["sections"]) == 6
    assert pano["is_synthetic_demo"] is True


def test_start_daily_review_writes_snapshot_and_returns_task(market_dir):
    for path in market_dir.glob("*.json"):
        path.unlink()
    task = service.start_daily_review(REVIEW_DATE)
    assert task["status"] == "succeeded"
    assert task["snapshot_id"] == SNAPSHOT_ID
    assert any(market_dir.glob("MARKET_*.json"))


def test_start_daily_review_rejects_bad_date(market_dir):
    with pytest.raises(ValueError):
        service.start_daily_review("not-a-date")


def test_load_unknown_market_review_raises(market_dir):
    with pytest.raises(KeyError):
        service.load_market_review("does-not-exist")


# --- HTTP API --------------------------------------------------------------
def _assert_ok(response):
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == api.API_SCHEMA_VERSION
    assert body["status"] == "ok"
    assert body["error"] is None
    assert set(body["meta"]) >= {"snapshot_id", "provider", "validation_status", "evidence_ids"}
    return body


def test_api_list_and_detail_endpoints(market_dir):
    listing = _assert_ok(client.get("/api/daily-review"))
    assert listing["data"]["items"]
    assert listing["meta"]["snapshot_id"] is None

    summary = _assert_ok(client.get(f"/api/daily-review/{SNAPSHOT_ID}/summary"))
    assert summary["meta"]["snapshot_id"] == SNAPSHOT_ID
    assert summary["meta"]["provider"] == "synthetic_demo"
    assert summary["meta"]["validation_status"] in {"pass", "warning", "blocked"}

    pano = _assert_ok(client.get(f"/api/daily-review/{SNAPSHOT_ID}/panorama"))
    assert "sections" in pano["data"]
    hot = _assert_ok(client.get(f"/api/daily-review/{SNAPSHOT_ID}/hotspots"))
    assert "sections" in hot["data"]


def test_api_acquire_endpoint(market_dir):
    resp = client.post("/api/daily-review/acquire", json={"review_date": REVIEW_DATE})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["status"] == "succeeded"


def test_api_unknown_review_returns_404(market_dir):
    resp = client.get("/api/daily-review/nope/summary")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "MARKET_REVIEW_NOT_FOUND"


def test_api_invalid_acquire_returns_422(market_dir):
    resp = client.post("/api/daily-review/acquire", json={"review_date": "xx"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
