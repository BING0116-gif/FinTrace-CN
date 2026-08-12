from pathlib import Path

import pytest

from scripts.generate_cn_full_report import generate_report


ROOT = Path(__file__).parents[1]


def test_full_report_rejects_unsourced_cross_industry_peer_valuation(tmp_path):
    with pytest.raises(ValueError, match="Moutai-specific illustrations"):
        generate_report(
            ROOT / "data" / "snapshots" / "cn" / "000333.SZ_20260812_tushare_v1.json",
            "000333.SZ",
            tmp_path,
        )
