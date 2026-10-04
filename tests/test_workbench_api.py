"""Offline contract tests for the versioned workbench HTTP API."""

from fastapi.testclient import TestClient

import api


client = TestClient(api.app)
SNAPSHOT_ID = "600519.SH_20260810_tushare_v1"
REQUIRED_META = {
    "snapshot_id", "research_as_of", "provider", "currency", "unit", "period_basis",
    "evidence_ids", "validation_status", "data_coverage", "freshness",
}


def _assert_ok(response):
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == api.API_SCHEMA_VERSION
    assert body["status"] == "ok"
    assert body["error"] is None
    assert set(body["meta"]) == REQUIRED_META
    return body


def test_research_endpoints_share_versioned_envelope_and_provenance():
    endpoints = ["summary", "market", "financials", "evidence", "valuation", "validation", "trace", "report", "artifacts"]

    for endpoint in endpoints:
        body = _assert_ok(client.get(f"/api/research/{SNAPSHOT_ID}/{endpoint}"))
        assert body["meta"]["snapshot_id"] == SNAPSHOT_ID
        assert body["meta"]["research_as_of"]
        assert body["meta"]["provider"] == "tushare"
        assert body["meta"]["currency"] == "CNY"
        assert body["meta"]["validation_status"] in {"pass", "warning", "blocked"}


def test_card15_readiness_endpoint_uses_shared_status_contract():
    body = _assert_ok(client.get("/api/demo/readiness", params={"snapshot_id": SNAPSHOT_ID}))
    assert body["data"]["status"] in {"missing_assets", "partial", "blocked", "ready"}
    assert "checks" in body["data"]
    assert "C:\\" not in str(body["data"])


def test_financial_period_query_exposes_ttm_basis_and_calculation_evidence():
    body = _assert_ok(client.get(f"/api/research/{SNAPSHOT_ID}/financials?period_basis=TTM"))

    assert body["data"]["period_basis"] == "TTM"
    assert body["data"]["points"]
    assert any(
        point["evidence_ids"]["net_profit"].startswith("calc_")
        for point in body["data"]["points"] if point["evidence_ids"]["net_profit"]
    )


def test_trace_marks_legacy_missing_trace_as_unavailable_instead_of_fabricating_steps():
    body = _assert_ok(client.get(f"/api/research/{SNAPSHOT_ID}/trace"))

    if not body["data"]["available"]:
        assert body["data"]["events"] == []
        assert body["data"]["unavailable_reason"] == "trace_not_recorded_for_legacy_task"


def test_artifact_contract_does_not_expose_server_file_paths():
    body = _assert_ok(client.get(f"/api/research/{SNAPSHOT_ID}/artifacts"))

    for artifact in body["data"]["artifacts"]:
        assert set(artifact) == {"kind", "filename", "media_type", "size_bytes"}
        assert "\\" not in artifact["filename"]


def test_document_register_parse_and_read_endpoints(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("营业收入：12.5 亿元\f归母净利润：3.1 亿元", encoding="utf-8")
    registered = client.post("/api/documents/register", json={
        "path": str(path), "symbol": "600519.SH", "fiscal_period": "2025FY",
        "published_at": "2026-04-01T00:00:00+08:00",
    })
    assert registered.status_code == 200
    document_id = registered.json()["data"]["document_id"]

    parsed = client.post(f"/api/documents/{document_id}/parse")
    assert parsed.status_code == 200
    assert parsed.json()["data"]["document"]["status"] == "complete"
    assert len(parsed.json()["data"]["fragments"]) == 2

    facts = client.get(f"/api/documents/{document_id}/facts")
    assert facts.status_code == 200
    assert {fact["metric"] for fact in facts.json()["data"]} == {"revenue", "net_profit"}


def test_document_api_hides_registration_failure(tmp_path):
    response = client.post("/api/documents/register", json={"path": str(tmp_path / "missing.pdf")})
    assert response.status_code == 400
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == "DOCUMENT_REGISTRATION_FAILED"


def test_document_parse_rejects_content_changed_after_registration(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("营业收入：1 亿元", encoding="utf-8")
    registered = client.post("/api/documents/register", json={"path": str(path)})
    document_id = registered.json()["data"]["document_id"]
    path.write_text("营业收入：99 亿元", encoding="utf-8")
    response = client.post(f"/api/documents/{document_id}/parse")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_CONTENT_CHANGED"


def test_unknown_snapshot_and_invalid_query_use_safe_typed_errors():
    missing = client.get("/api/research/not-a-snapshot/summary")
    invalid = client.get(f"/api/research/{SNAPSHOT_ID}/financials?period_basis=FUTURE")

    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "SNAPSHOT_NOT_FOUND", "message": "Research snapshot was not found.", "retryable": False,
    }
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    assert invalid.json()["data"] is None


def test_task_detail_and_progress_endpoints_use_persisted_service_contract(monkeypatch):
    monkeypatch.setattr(api.service, "get_task", lambda task_id: {"id": task_id, "status": "running"})
    monkeypatch.setattr(api.service, "get_task_progress", lambda task_id: {
        "task_id": task_id, "status": "running", "progress_percent": 40,
    })

    detail = _assert_ok(client.get("/api/tasks/task-1"))
    progress = _assert_ok(client.get("/api/tasks/task-1/progress"))
    assert detail["data"]["status"] == "running"
    assert progress["data"]["progress_percent"] == 40


def test_task_rerun_endpoint_uses_accepted_envelope(monkeypatch):
    monkeypatch.setattr(api.service, "rerun_task", lambda task_id: {
        "id": "retry-1", "retry_of": task_id, "status": "queued", "symbol": "600519.SH",
        "snapshot_id": SNAPSHOT_ID,
    })

    response = client.post("/api/tasks/task-1/rerun")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["retry_of"] == "task-1"
    assert body["meta"]["snapshot_id"] == SNAPSHOT_ID


def test_task_api_does_not_expose_server_artifact_paths(monkeypatch):
    monkeypatch.setattr(api.service, "get_task", lambda task_id: {
        "id": task_id, "status": "succeeded", "snapshot_id": SNAPSHOT_ID,
        "report_path": "C:\\private\\report.md", "metadata_path": "C:\\private\\metadata.json",
    })

    body = _assert_ok(client.get("/api/tasks/task-1"))

    assert "report_path" not in body["data"]
    assert "metadata_path" not in body["data"]


def test_task_cancel_endpoint_uses_accepted_envelope(monkeypatch):
    monkeypatch.setattr(api.service, "cancel_task", lambda task_id: {
        "id": task_id, "status": "cancelled", "message": "cancelled",
    })

    response = client.post("/api/tasks/task-1/cancel")

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "cancelled"


def test_task_diagnostics_endpoint_returns_safe_summary(monkeypatch):
    monkeypatch.setattr(api.service, "task_diagnostics", lambda task_id: {
        "task_id": task_id, "status": "failed", "error_type": "RuntimeError",
        "error_summary": "safe diagnostic", "trace": [],
    })

    body = _assert_ok(client.get("/api/tasks/task-1/diagnostics"))

    assert body["data"]["error_summary"] == "safe diagnostic"
    assert "report_path" not in body["data"]


def test_evaluation_endpoints_return_measured_artifacts(monkeypatch):
    monkeypatch.setattr(api.service, "list_evaluations", lambda: [{"id": "benchmark/run/results.json"}])
    monkeypatch.setattr(api.service, "evaluation_detail", lambda evaluation_id: {
        "id": evaluation_id, "kind": "benchmark", "summary": {"cases": 2}, "results": [],
    })

    listing = _assert_ok(client.get("/api/evaluations"))
    detail = _assert_ok(client.get("/api/evaluations/benchmark/run/results.json"))

    assert listing["data"]["items"][0]["id"] == "benchmark/run/results.json"
    assert detail["data"]["summary"]["cases"] == 2


def test_card15_run_endpoints_use_persisted_service_contract(monkeypatch):
    monkeypatch.setattr(api.service, "list_demo_runs", lambda: [{
        "run_id": "run-1", "validation": {"complete": True},
    }])
    monkeypatch.setattr(api.service, "demo_run_detail", lambda run_id: {
        "run_id": run_id, "validation": {"complete": True}, "timeline": {"events": []},
        "artifacts": {"finfuzz": None},
    })

    listing = _assert_ok(client.get("/api/demo/runs"))
    detail = _assert_ok(client.get("/api/demo/runs/run-1"))

    assert listing["data"]["items"][0]["run_id"] == "run-1"
    assert detail["data"]["run_id"] == "run-1"


def test_card15_export_endpoint_streams_service_bytes_without_paths(monkeypatch):
    monkeypatch.setattr(api.service, "export_demo_evidence_pack", lambda run_id: {
        "run_id": run_id, "filename": "run-1.zip", "media_type": "application/zip", "content": b"zip-bytes",
    })

    response = client.post("/api/demo/runs/run-1/export")

    assert response.status_code == 200
    assert response.content == b"zip-bytes"
    assert response.headers["content-type"] == "application/zip"
    assert "run-1.zip" in response.headers["content-disposition"]


def test_openapi_publishes_stable_envelope_meta_and_error_schemas():
    document = client.get("/openapi.json").json()
    schemas = document["components"]["schemas"]

    assert {"ApiEnvelope", "ApiMeta", "ApiError"}.issubset(schemas)
    assert set(schemas["ApiEnvelope"]["properties"]) == {"schema_version", "status", "data", "meta", "error"}
    assert REQUIRED_META == set(schemas["ApiMeta"]["properties"])


def test_health_is_live_without_provider_or_credentials():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "schema_version": api.API_SCHEMA_VERSION}
