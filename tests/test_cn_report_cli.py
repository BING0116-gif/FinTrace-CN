import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "generate_cn_snapshot_report.py"
SNAPSHOT = ROOT / "data" / "snapshots" / "cn" / "600519.SH_20260810_tushare_v1.json"
BANK_BOUNDARY_SNAPSHOT = ROOT / "tests" / "fixtures" / "cn" / "600036.SH_bank_boundary_v1.json"


def test_snapshot_report_cli_is_reproducible_and_writes_provenance(tmp_path):
    output = tmp_path / "moutai_report.md"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--snapshot", str(SNAPSHOT), "--output", str(output)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    metadata = json.loads(completed.stdout)
    assert metadata["snapshot_id"] == "600519.SH_20260810_tushare_v1"
    assert metadata["validation"]["valid"]
    assert "calc_market_cap" in output.read_text(encoding="utf-8")
    assert json.loads(output.with_suffix(".metadata.json").read_text(encoding="utf-8"))["report_path"] == str(output)


def test_snapshot_report_cli_renders_bank_boundary_case_without_network(tmp_path):
    output = tmp_path / "bank_boundary_report.md"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--snapshot", str(BANK_BOUNDARY_SNAPSHOT), "--symbol", "600036.SH", "--output", str(output)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )

    assert json.loads(completed.stdout)["validation"]["valid"]
    assert "金融机构估值边界" in output.read_text(encoding="utf-8")
