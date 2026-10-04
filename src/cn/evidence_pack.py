"""Evidence Pack export and loss-tolerant audit replay (CARD-12).

This module only copies and validates already-produced run artifacts.  It never
reconstructs missing financial facts or hides a failed event.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
import shutil
import zipfile
from typing import Any, Iterable, Mapping

REQUIRED_ARTIFACTS = ("report.md", "report.json", "financials.xlsx", "valuation.xlsx", "corrections.xlsx", "claims.json", "evidence.json", "calculations.json", "validation.json", "events.jsonl", "manifest.json")
REQUIRED_DIRECTORIES = ("charts", "citations")

FAILURE_INJECTION_SCENARIOS = (
    {"id": "missing_total_shares", "label": "缺失总股本", "expected": "per_share_valuation_blocked"},
    {"id": "deleted_pdf_page", "label": "删除 PDF 某页", "expected": "citation_incomplete"},
    {"id": "unit_scale_change", "label": "单位万元→亿元", "expected": "unit_checker_error"},
    {"id": "wrong_yoy_draft", "label": "草稿给错误同比", "expected": "checker_finding"},
    {"id": "corrected_filing", "label": "旧财报+更正公告", "expected": "source_conflict_superseded"},
    {"id": "deleted_evidence", "label": "删除关键 Evidence", "expected": "claim_blocked"},
    {"id": "unsupported_causal_claim", "label": "无证据因果结论", "expected": "unsupported_causal_inference"},
)

@dataclass(frozen=True)
class PackValidation:
    run_id: str
    complete: bool
    missing: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]: return asdict(self) | {"missing": list(self.missing), "errors": list(self.errors), "warnings": list(self.warnings)}

@dataclass(frozen=True)
class ReplayEvent:
    ts: str
    run_id: str
    stage: str
    event_type: str
    status: str
    input: Any = None
    output: Any = None
    source: Any = None
    detail: dict[str, Any] | None = None
    malformed: bool = False

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _json(path: Path) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return None

def _ids(payload: Any, names: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in names and isinstance(value, str): found.add(value)
            found |= _ids(value, names)
    elif isinstance(payload, list):
        for value in payload: found |= _ids(value, names)
    return found

def validate_evidence_pack(run_dir: str | Path, *, run_id: str | None = None) -> PackValidation:
    root = Path(run_dir); rid = run_id or root.name; missing: list[str] = []; errors: list[str] = []; warnings: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        if not (root / name).is_file(): missing.append(name)
    for name in REQUIRED_DIRECTORIES:
        if not (root / name).is_dir(): missing.append(name + "/")
    manifest = _json(root / "manifest.json")
    if manifest is None and (root / "manifest.json").is_file(): errors.append("manifest_invalid_json")
    if manifest and str(manifest.get("run_id")) != str(rid): errors.append("manifest_run_id_mismatch")
    events, event_errors = read_replay_events(root / "events.jsonl", expected_run_id=rid)
    errors.extend(event_errors)
    if not events and (root / "events.jsonl").is_file(): warnings.append("events_empty")
    report = _json(root / "report.json")
    claims = _json(root / "claims.json")
    evidence = _json(root / "evidence.json")
    if report is not None:
        claim_refs = _ids(report, {"claim_id", "claim_ids"})
        evidence_refs = _ids(report, {"evidence_id", "evidence_ids"})
        claim_ids = _ids(claims, {"claim_id", "id"})
        evidence_ids = _ids(evidence, {"evidence_id", "id"})
        errors.extend("unresolved_claim:" + x for x in sorted(claim_refs - claim_ids))
        errors.extend("unresolved_evidence:" + x for x in sorted(evidence_refs - evidence_ids))
    return PackValidation(rid, not missing and not errors, tuple(missing), tuple(errors), tuple(warnings))

def read_replay_events(path: str | Path, *, expected_run_id: str | None = None) -> tuple[list[ReplayEvent], list[str]]:
    """Read events in order; malformed JSON lines are retained as warnings and skipped."""
    file = Path(path); events: list[ReplayEvent] = []; errors: list[str] = []
    if not file.is_file(): return [], ["events_missing"]
    for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        try: payload = json.loads(line)
        except json.JSONDecodeError: errors.append(f"event_invalid_json:{line_no}"); continue
        rid = str(payload.get("run_id", ""))
        if expected_run_id and rid != expected_run_id: errors.append(f"event_run_id_mismatch:{line_no}")
        events.append(ReplayEvent(str(payload.get("ts", "")), rid, str(payload.get("stage", "")), str(payload.get("event_type", "")), str(payload.get("status", "")), payload.get("input_digest"), payload.get("output_digest"), payload.get("source"), dict(payload.get("detail") or {})))
    return events, errors

def replay_timeline(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir); run_id = root.name
    events, errors = read_replay_events(root / "events.jsonl", expected_run_id=run_id)
    return {"run_id": run_id, "events": [event.to_dict() for event in events], "errors": errors, "stages": [event.stage for event in events]}

def render_replay_markdown(timeline: Mapping[str, Any]) -> str:
    lines = [f"# Audit Replay: {timeline.get('run_id', '')}", "", "| 时间 | 阶段 | 事件 | 状态 | 输入 | 输出 | 来源 |", "|---|---|---|---|---|---|---|"]
    for event in timeline.get("events", []):
        lines.append("| {ts} | {stage} | {event_type} | {status} | {input} | {output} | {source} |".format(ts=event.get("ts", ""), stage=event.get("stage", ""), event_type=event.get("event_type", ""), status=event.get("status", ""), input=event.get("input", ""), output=event.get("output", ""), source=event.get("source", "")))
    if timeline.get("errors"): lines.extend(["", "⚠️ Replay warnings:", *[f"- {item}" for item in timeline["errors"]]])
    return "\n".join(lines) + "\n"

def export_evidence_pack(run_id: str, *, runs_root: str | Path = "runs", output_dir: str | Path | None = None) -> Path:
    """Copy an auditable run directory and return its zip path."""
    source = Path(runs_root) / run_id
    if not source.is_dir(): raise FileNotFoundError(f"run directory not found: {source}")
    destination = Path(output_dir or source.parent) / run_id
    if destination.exists(): shutil.rmtree(destination)
    shutil.copytree(source, destination)
    validation = validate_evidence_pack(destination, run_id=run_id)
    (destination / "pack_validation.json").write_text(json.dumps(validation.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = destination.parent / f"{run_id}.zip"
    if archive.exists(): archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(destination.rglob("*")):
            if path.is_file(): handle.write(path, path.relative_to(destination.parent))
    return archive

def list_failure_injections() -> list[dict[str, str]]: return [dict(item) for item in FAILURE_INJECTION_SCENARIOS]


def inject_failure_scenario(run_dir: str | Path, scenario_id: str, output_dir: str | Path) -> Path:
    """Create a disposable, reproducible failure-injection copy of a run.

    The source run is never modified. Missing optional artifacts are recorded in
    ``failure_injection.json`` instead of being silently invented.
    """
    scenario = next((item for item in FAILURE_INJECTION_SCENARIOS if item["id"] == scenario_id), None)
    if scenario is None:
        raise ValueError(f"unknown failure scenario: {scenario_id}")
    source = Path(run_dir)
    if not source.is_dir(): raise FileNotFoundError(source)
    destination = Path(output_dir) / f"{source.name}_{scenario_id}"
    if destination.exists(): raise FileExistsError(destination)
    shutil.copytree(source, destination)
    marker = {"scenario": dict(scenario), "source_run": source.name, "mutations": []}
    if scenario_id == "deleted_evidence":
        evidence_path = destination / "evidence.json"; payload = _json(evidence_path)
        if isinstance(payload, Mapping):
            if isinstance(payload.get("evidence"), list) and payload["evidence"]:
                removed = payload["evidence"].pop(0); marker["mutations"].append({"removed_evidence": removed.get("evidence_id")})
            evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif scenario_id == "deleted_pdf_page":
        evidence_path = destination / "evidence.json"; payload = _json(evidence_path)
        if isinstance(payload, Mapping):
            rows = payload.get("evidence", [])
            if rows and isinstance(rows[0], Mapping):
                rows[0] = {key: value for key, value in rows[0].items() if key not in {"page", "page_number"}}; marker["mutations"].append({"page_removed": True})
            evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        marker["mutations"].append({"marker_only": True, "reason": scenario["expected"]})
    (destination / "failure_injection.json").write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination
