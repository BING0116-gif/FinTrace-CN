"""Offline contract tests for the agent-research HTTP API.

The shared agent executor is stubbed so tests are fully offline — a request is
queued and inspected without ever constructing a network LLM provider.
Post/queued paths verify the envelope, task life cycle and credential secrecy.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import api
from src.cn import workbench_service
from src.cn.demo_data import ensure_demo_snapshots


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
client = TestClient(api.app)

DEMO_SNAPSHOT = "600519.SH_illustrative_demo_v1"
MODEL = "deepseek-v4-flash"
PAYLOAD = {
    "query": "分析贵州茅台的收入和净利润，并引用证据。",
    "symbol": "600519.SH",
    "snapshot_id": DEMO_SNAPSHOT,
    "research_as_of": "2025-04-30T23:00:00+08:00",
    "model_name": MODEL,
}


class _StubExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args))
        return None

    def shutdown(self, *args, **kwargs):
        return None


def _noop_fixture(monkeypatch):
    base = _PROJECT_ROOT / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="dti", dir=base))
    monkeypatch.setattr(workbench_service, "SNAPSHOT_DIR", root / "snapshots")
    monkeypatch.setattr(workbench_service, "TASK_DIR", root / "tasks")
    ensure_demo_snapshots(root / "snapshots")
    monkeypatch.setattr(workbench_service, "TASK_EXECUTOR", _StubExecutor())
    yield root
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    shutil.rmtree(root, ignore_errors=True)


def test_agent_research_rejects_unconfigured_model(monkeypatch):
    _noop_fixture(monkeypatch)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    response = client.post("/api/agent/research", json=PAYLOAD)
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "AGENT_RESEARCH_INVALID"
    assert "DEEPSEEK_API_KEY" in body["error"]["message"]


def test_agent_research_rejects_unknown_snapshot(monkeypatch):
    _noop_fixture(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    response = client.post("/api/agent/research", json={**PAYLOAD, "snapshot_id": "missing"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_SNAPSHOT"


def test_agent_research_rejects_short_query(monkeypatch):
    _noop_fixture(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    response = client.post("/api/agent/research", json={**PAYLOAD, "query": "hi"})
    assert response.status_code == 422


def test_agent_research_create_query_and_trace_flow(monkeypatch):
    _noop_fixture(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    created = client.post("/api/agent/research", json=PAYLOAD, )
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "ok"
    assert body["schema_version"] == api.API_SCHEMA_VERSION
    task_id = body["data"]["task_id"]
    assert body["data"]["kind"] == "agent_research"
    assert body["data"]["task_status"] in {"queued", "running"}

    detail = client.get(f"/api/agent/research/{task_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == "ok"
    assert detail_body["data"]["kind"] == "agent_research"
    assert detail_body["data"]["snapshot_id"] == DEMO_SNAPSHOT
    assert detail_body["data"]["model_name"] == MODEL

    trace = client.get(f"/api/agent/research/{task_id}/trace")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["data"]["task_id"] == task_id
    assert any(event["event"] == "queued" for event in trace_body["data"]["events"])


def test_agent_research_response_hides_secrets_and_paths(monkeypatch):
    _noop_fixture(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    created = client.post("/api/agent/research", json=PAYLOAD)
    task_id = created.json()["data"]["task_id"]

    for url in (f"/api/agent/research/{task_id}", f"/api/agent/research/{task_id}/trace"):
        text = client.get(url).text
        assert "OPENAI_API_KEY" not in text
        assert "ANTHROPIC_API_KEY" not in text
        assert "DEEPSEEK_API_KEY" not in text
        assert "test-key" not in text
        assert "traceback" not in text.lower()
        assert "\\\\venv" not in text and ".venv" not in text
        assert "C:\\\\" not in text and "C:/" not in text


def test_agent_research_unknown_task_returns_404(monkeypatch):
    _noop_fixture(monkeypatch)
    response = client.get("/api/agent/research/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"