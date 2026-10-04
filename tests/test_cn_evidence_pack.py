import json
import zipfile

from src.cn.evidence_pack import (
    FAILURE_INJECTION_SCENARIOS, export_evidence_pack, list_failure_injections,
    read_replay_events, replay_timeline, validate_evidence_pack,
    inject_failure_scenario,
)


def _run(root):
    run = root / "run_1"
    run.mkdir(); (run / "charts").mkdir(); (run / "citations").mkdir()
    for name in ("report.md", "financials.xlsx", "valuation.xlsx", "corrections.xlsx"):
        (run / name).write_text("", encoding="utf-8")
    (run / "manifest.json").write_text(json.dumps({"run_id": "run_1"}), encoding="utf-8")
    (run / "report.json").write_text(json.dumps({"claim_id": "c1", "evidence_id": "e1"}), encoding="utf-8")
    (run / "claims.json").write_text(json.dumps({"claims": [{"claim_id": "c1"}]}), encoding="utf-8")
    (run / "evidence.json").write_text(json.dumps({"evidence": [{"evidence_id": "e1"}]}), encoding="utf-8")
    for name in ("calculations.json", "validation.json"):
        (run / name).write_text("{}", encoding="utf-8")
    (run / "events.jsonl").write_text(json.dumps({"run_id": "run_1", "ts": "2026-01-01", "stage": "validation", "event_type": "done", "status": "ok", "detail": {}}) + "\nnot-json\n", encoding="utf-8")
    return run


def test_pack_validation_tolerates_bad_event_line_and_export(tmp_path):
    run = _run(tmp_path)
    validation = validate_evidence_pack(run)
    assert not validation.complete
    assert "event_invalid_json:2" in validation.errors
    timeline = replay_timeline(run)
    assert timeline["stages"] == ["validation"]
    archive = export_evidence_pack("run_1", runs_root=tmp_path, output_dir=tmp_path / "out")
    assert archive.is_file()
    with zipfile.ZipFile(archive) as handle:
        assert "run_1/manifest.json" in handle.namelist()
        assert "run_1/pack_validation.json" in handle.namelist()


def test_missing_artifacts_are_explicit_and_failure_catalogue_complete(tmp_path):
    run = tmp_path / "run_empty"; run.mkdir()
    result = validate_evidence_pack(run)
    assert "report.md" in result.missing and not result.complete
    assert len(FAILURE_INJECTION_SCENARIOS) == 7
    assert len(list_failure_injections()) == 7

def test_failure_injection_copies_source_and_removes_key_evidence_only_in_copy(tmp_path):
    run = _run(tmp_path)
    injected = inject_failure_scenario(run, "deleted_evidence", tmp_path / "injected")
    assert injected != run and (injected / "failure_injection.json").is_file()
    assert json.loads((run / "evidence.json").read_text(encoding="utf-8"))["evidence"]
    assert json.loads((injected / "evidence.json").read_text(encoding="utf-8"))["evidence"] == []
