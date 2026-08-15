from pathlib import Path
import json
import subprocess
import sys

from scripts.generate_cn_full_report import _snapshot_candidate, _snapshot_peers, generate_report


ROOT = Path(__file__).parents[1]
SNAPSHOTS = ROOT / "data" / "snapshots" / "cn"
FULL_REPORT_SCRIPT = ROOT / "scripts" / "generate_cn_full_report.py"


def test_snapshot_candidate_keeps_only_available_facts_and_evidence():
    candidate, name = _snapshot_candidate(
        SNAPSHOTS / "600519.SH_20260810_tushare_v1.json",
        cutoff="2026-08-10T23:00:00+08:00",
    )

    assert candidate.valuation.symbol == "600519.SH"
    assert name
    assert candidate.valuation.raw_price > 0
    assert set(candidate.evidence_ids) == {"price", "shares", "profit", "equity", "revenue"}


def test_full_report_uses_only_snapshot_peer_facts(tmp_path):
    metadata = generate_report(
        SNAPSHOTS / "600519.SH_20260810_tushare_v1.json",
        "600519.SH",
        tmp_path,
        peer_snapshot_dir=SNAPSHOTS,
    )

    assert metadata["snapshot_id"] == "600519.SH_20260810_tushare_v1"
    assert metadata["peer_valuation"]["peer_count"] == 4
    assert (tmp_path / "600519.SH_cn_report.xlsx").exists()


def test_snapshot_peer_selection_excludes_other_industries():
    target, _, candidates, _ = _snapshot_peers(
        SNAPSHOTS / "600519.SH_20260810_tushare_v1.json",
        snapshot_dir=SNAPSHOTS,
        cutoff="2026-08-10T23:00:00+08:00",
    )

    assert target.industry_code == "L1_01"
    assert any(item.industry_code != target.industry_code for item in candidates)


def test_snapshot_peer_selection_excludes_snapshots_collected_after_cutoff(tmp_path):
    future_peer = json.loads((SNAPSHOTS / "000568.SZ_20260812_tushare_v1.json").read_text(encoding="utf-8"))
    future_peer["snapshot_id"] = "000568.SZ_20260814_tushare_v1"
    future_peer["research_as_of"] = "2026-08-14T10:45:00+08:00"
    path = tmp_path / "000568.SZ_20260814_tushare_v1.json"
    path.write_text(json.dumps(future_peer), encoding="utf-8")

    _, _, candidates, _ = _snapshot_peers(
        SNAPSHOTS / "600519.SH_20260810_tushare_v1.json",
        snapshot_dir=tmp_path,
        cutoff="2026-08-10T23:00:00+08:00",
    )

    assert candidates == []


def test_documented_offline_demo_generates_valid_report_excel_and_metadata(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(FULL_REPORT_SCRIPT), "--snapshot",
         str(SNAPSHOTS / "600519.SH_20260810_tushare_v1.json"), "--output", str(tmp_path)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )

    metadata = json.loads((tmp_path / "600519.SH_cn_report.metadata.json").read_text(encoding="utf-8"))
    assert "Validation: PASS" in completed.stdout
    assert metadata["validation"]["valid"]
    assert (tmp_path / "600519.SH_research_report.md").exists()
    assert (tmp_path / "600519.SH_cn_report.xlsx").exists()
