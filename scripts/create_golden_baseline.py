"""Materialize the two offline interview cases and their golden artifact bundle.

This script intentionally copies only already-local, versioned inputs and measured
outputs.  It never calls a data provider or a model.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "snapshots" / "cn"
OUTPUT = ROOT / "output"
BASELINE = OUTPUT / "golden_baseline"
SUCCESS_SNAPSHOT = "600519.SH_20260810_tushare_v1"
BLOCKED_SNAPSHOT = "600519.SH_demo_missing_evidence_v1"


def _copy(source: Path, destination: Path) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "path": destination.relative_to(BASELINE).as_posix(),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "bytes": destination.stat().st_size,
    }


def _blocked_snapshot() -> Path:
    source = SNAPSHOTS / f"{SUCCESS_SNAPSHOT}.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["snapshot_id"] = BLOCKED_SNAPSHOT
    payload["data_quality"] = "demo_fixture_missing_total_shares_not_for_investment"
    payload["data"]["profile"]["name"] = "贵州茅台（缺关键证据演示）"
    for statement in payload["data"].get("statements", []):
        statement.get("values", {}).pop("total_shares", None)
    target = SNAPSHOTS / f"{BLOCKED_SNAPSHOT}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    BASELINE.mkdir(parents=True, exist_ok=True)
    files = []
    files.append(_copy(SNAPSHOTS / f"{SUCCESS_SNAPSHOT}.json", BASELINE / "snapshots" / f"{SUCCESS_SNAPSHOT}.json"))
    files.append(_copy(_blocked_snapshot(), BASELINE / "snapshots" / f"{BLOCKED_SNAPSHOT}.json"))
    for suffix in ("_research_report.md", "_cn_report.xlsx", "_cn_report.metadata.json"):
        files.append(_copy(OUTPUT / "demo" / "600519" / f"600519.SH{suffix}", BASELINE / "artifacts" / f"600519.SH{suffix}"))
    for source in (OUTPUT / "benchmark" / "results.json", OUTPUT / "agent_ablation" / "real_gate_run_001" / "ablation_results.json"):
        files.append(_copy(source, BASELINE / "evaluations" / source.name))
    manifest = {
        "baseline_version": "2026-08-14-demo-v1",
        "success_case": {"snapshot_id": SUCCESS_SNAPSHOT, "expected_validation": "pass"},
        "blocked_case": {"snapshot_id": BLOCKED_SNAPSHOT, "expected_validation": "blocked", "reason": "missing_total_shares"},
        "files": files,
    }
    (BASELINE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Golden baseline written to {BASELINE}")


if __name__ == "__main__":
    main()
