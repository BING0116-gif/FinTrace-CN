from __future__ import annotations

import json

import pytest

from src.cn.runs import EVENT_STAGES, RunRecorder, digest, replay


def test_manifest_has_required_fields_and_event_digests_are_stable(tmp_path):
    source = tmp_path / "report.txt"
    source.write_text("营业收入 12.5 亿元", encoding="utf-8")
    recorder = RunRecorder(tmp_path / "runs")
    run_id = recorder.start({"snapshot_id": "snap-v1", "execution_mode": "offline", "random_seed": 7})
    recorder.emit("file_load", "read", input_=source, output={"sha256": digest(source)}, detail={"path": str(source), "sha256": digest(source)})
    recorder.emit("calculation", "calc", input_={"x": 1}, output={"y": 2}, detail={"calculation_id": "calc_1"})
    recorder.finish("succeeded")
    manifest = json.loads((tmp_path / "runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
    required = {"run_id", "started_at", "finished_at", "input_document_sha256", "snapshot_id", "model", "model_provider", "model_version", "temperature", "prompt_hash", "skill_hash", "parser_name", "parser_version", "git_commit", "tool_versions", "random_seed", "execution_mode"}
    assert required <= manifest.keys()
    events = [json.loads(line) for line in (tmp_path / "runs" / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[1]["prev_event_hash"] == events[0]["event_hash"]
    assert all(event["input_digest"] == digest({"x": 1}) or event["stage"] != "calculation" for event in events)
    assert recorder.verify_replayable(run_id).replayable
    assert replay(run_id, recorder).status == "replayable"


def test_all_nine_stages_are_allowed_and_calculation_requires_id(tmp_path):
    recorder = RunRecorder(tmp_path / "runs")
    recorder.start()
    for stage in EVENT_STAGES - {"calculation"}:
        recorder.emit(stage, "event")
    with pytest.raises(ValueError, match="calculation_id"):
        recorder.emit("calculation", "event")


def test_interrupted_run_and_tampered_event_are_not_replayable(tmp_path):
    recorder = RunRecorder(tmp_path / "runs")
    run_id = recorder.start()
    recorder.emit("parse", "started")
    assert "interrupted_run" in recorder.verify_replayable(run_id).reasons
    events_path = tmp_path / "runs" / run_id / "events.jsonl"
    events_path.write_text(events_path.read_text(encoding="utf-8").replace('"status": "ok"', '"status": "tampered"'), encoding="utf-8")
    plan = recorder.verify_replayable(run_id)
    assert not plan.replayable
    assert any(reason.startswith("event_hash_mismatch") for reason in plan.reasons)


def test_replay_rejects_changed_input_file(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("original", encoding="utf-8")
    recorder = RunRecorder(tmp_path / "runs")
    run_id = recorder.start()
    recorder.emit("file_load", "read", detail={"path": str(source), "sha256": digest(source)})
    recorder.finish()
    source.write_text("changed", encoding="utf-8")
    result = replay(run_id, recorder)
    assert result.status == "rejected"
    assert any(reason.startswith("input_changed:") for reason in result.diff)
