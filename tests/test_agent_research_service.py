"""Offline application-service tests for the agent_research task.

These keep the shared executor stubbed so nothing ever reaches a real LLM: a
"queued" task is created and inspected without building a network provider.
Snapshot and task directories are isolated to a temp dir per test.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from src.cn import agent_service, workbench_service
from src.cn.agent_service import AgentResearchRequest, AgentResearchError
from src.cn.demo_data import ensure_demo_snapshots


# The system temp dir is restricted on this machine, so tests keep their
# isolated data under the (git-ignored) ``tmp/`` tree of the repo.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEMO_SNAPSHOT = "600519.SH_illustrative_demo_v1"
DIFFERENT_SNAPSHOT = "000858.SZ_illustrative_demo_v1"
MODEL = "deepseek-v4-flash"


class _StubExecutor:
    """Capture submitted work and never execute it (offline, no network)."""

    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args, **kwargs):
        self.submitted.append((fn, args))
        return None

    def shutdown(self, *args, **kwargs):
        return None


@pytest.fixture()
def isolated(monkeypatch):
    base = _PROJECT_ROOT / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="dt", dir=base))
    snapshot_dir = root / "snapshots"
    task_dir = root / "tasks"
    ensure_demo_snapshots(snapshot_dir)
    monkeypatch.setattr(workbench_service, "SNAPSHOT_DIR", snapshot_dir)
    monkeypatch.setattr(workbench_service, "TASK_DIR", task_dir)
    executor = _StubExecutor()
    monkeypatch.setattr(workbench_service, "TASK_EXECUTOR", executor)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    yield executor
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    shutil.rmtree(root, ignore_errors=True)


def _request(**overrides) -> AgentResearchRequest:
    params = dict(
        query="分析贵州茅台的收入和净利润，并引用证据。",
        symbol="600519.SH",
        snapshot_id=DEMO_SNAPSHOT,
        research_as_of="2025-04-30T23:00:00+08:00",
        model_name=MODEL,
    )
    params.update(overrides)
    return AgentResearchRequest(**params)


def test_query_too_short(isolated):
    with pytest.raises(AgentResearchError):
        agent_service.start_agent_research(_request(query="ab"))


def test_unknown_model_is_rejected(isolated):
    with pytest.raises(AgentResearchError) as exc:
        agent_service.start_agent_research(_request(model_name="does-not-exist"))
    assert "Unknown model" in str(exc.value)


def test_model_without_key_is_rejected(isolated, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(AgentResearchError) as exc:
        agent_service.start_agent_research(_request())
    assert "DEEPSEEK_API_KEY" in str(exc.value)


def test_invalid_symbol_is_rejected(isolated):
    with pytest.raises(AgentResearchError):
        agent_service.start_agent_research(_request(symbol="NOT_A_CODE"))


def test_unknown_snapshot_is_rejected(isolated):
    with pytest.raises(KeyError):
        agent_service.start_agent_research(_request(snapshot_id="missing_snapshot"))


def test_snapshot_symbol_mismatch_is_rejected(isolated):
    with pytest.raises(AgentResearchError):
        agent_service.start_agent_research(_request(snapshot_id=DIFFERENT_SNAPSHOT))


def test_valid_request_queues_agent_research_task(isolated):
    task = agent_service.start_agent_research(_request())

    assert task["kind"] == "agent_research"
    assert task["status"] == "queued"
    assert task["symbol"] == "600519.SH"
    assert task["snapshot_id"] == DEMO_SNAPSHOT
    assert task["model_name"] == MODEL
    assert task["max_steps"] == 6
    assert task["temperature"] == 0.0

    # The task was submitted to the (stubbed) shared executor, not run inline.
    assert isolated.submitted

    public = agent_service.get_agent_task(task["id"])
    assert public["status"] == "queued"
    # Browser-safe view must not leak server-local paths.
    for secret_key in ("report_path", "metadata_path", "snapshot_path", "probe_dir"):
        assert secret_key not in public


def test_agent_task_only_for_agent_kind(isolated):
    task = agent_service.start_agent_research(_request())
    with pytest.raises(KeyError):
        agent_service.get_agent_task(task["id"].replace("agent_research", "research"))


def test_agent_task_events_returns_safe_stream(isolated):
    task = agent_service.start_agent_research(_request())
    stream = agent_service.agent_task_events(task["id"])
    assert stream["task_id"] == task["id"]
    assert stream["status"] == "queued"
    assert isinstance(stream["events"], list)
    assert any(event["event"] == "queued" for event in stream["events"])