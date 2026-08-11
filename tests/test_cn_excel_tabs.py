"""Unit tests for FinTrace-CN Excel tab builders (Peer Valuation + Validation)."""

from __future__ import annotations

import openpyxl

from src.agents.fm.tabs.tab_peer_valuation import PeerValuationTabBuilder, PeerValuationData
from src.agents.fm.tabs.tab_validation import ValidationTabBuilder, ValidationData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_peer_data() -> PeerValuationData:
    return PeerValuationData(
        target_symbol="600519.SH",
        target_name="贵州茅台",
        industry_code="150200",
        period_basis="2025Q4_TTM",
        is_bank_or_insurer=False,
        raw_price=1500.0,
        total_shares=1_256_000_000,
        net_profit=85_000_000_000,
        book_equity=220_000_000_000,
        revenue=150_000_000_000,
        market_cap=1_884_000_000_000,
        peers=[
            {"symbol": "000858.SZ", "name": "五粮液", "included": True, "reason": "same_industry_same_period"},
            {"symbol": "600809.SH", "name": "山西汾酒", "included": True, "reason": "same_industry_same_period"},
            {"symbol": "000568.SZ", "name": "泸州老窖", "included": True, "reason": "same_industry_same_period"},
            {"symbol": "002304.SZ", "name": "洋河股份", "included": True, "reason": "same_industry_same_period"},
            {"symbol": "603369.SH", "name": "今世缘", "included": True, "reason": "same_industry_same_period"},
            {"symbol": "600779.SH", "name": "水井坊", "included": False, "reason": "industry_mismatch"},
        ],
        multiples={
            "PE": {
                "median": 28.5,
                "included_symbols": ["000858.SZ", "600809.SH", "000568.SZ", "002304.SZ", "603369.SH"],
                "excluded": {},
                "confidence": "high",
                "implied_price": 1920.0,
            },
            "PB": {
                "median": 8.2,
                "included_symbols": ["000858.SZ", "600809.SH", "000568.SZ", "002304.SZ", "603369.SH"],
                "excluded": {},
                "confidence": "high",
                "implied_price": 1440.0,
            },
            "PS": {
                "median": 12.0,
                "included_symbols": ["000858.SZ", "600809.SH", "000568.SZ", "002304.SZ", "603369.SH"],
                "excluded": {},
                "confidence": "high",
                "implied_price": 1440.0,
            },
        },
        validation={
            "valid": True,
            "errors": [],
            "warnings": [],
            "recalculated_values": {
                "implied_price_PE": 1920.0,
                "implied_price_PB": 1440.0,
                "implied_price_PS": 1440.0,
            },
            "evidence_coverage": 0.98,
        },
    )


def _make_validation_data() -> ValidationData:
    return ValidationData(
        symbol="600519.SH",
        research_as_of="2026-08-09T12:00:00+08:00",
        snapshot_id="600519.SH_20260809_v1",
        valid=True,
        errors=[],
        warnings=[],
        recalculated_values={
            "market_cap": 1_884_000_000_000,
            "pe_ttm": 22.16,
        },
        evidence_coverage=0.98,
        evidence_records=[
            {"evidence_id": "fact_600519_SH_close_20260809_RAW", "kind": "fact", "metric": "close", "value": 1500.0, "fiscal_period": None, "published_at": "2026-08-09", "provider": "snapshot"},
            {"evidence_id": "fact_600519_SH_total_shares_2025FY", "kind": "fact", "metric": "total_shares", "value": 1_256_000_000, "fiscal_period": "2025FY", "published_at": None, "provider": "snapshot"},
            {"evidence_id": "calc_market_cap", "kind": "calculation", "metric": "market_cap", "value": 1_884_000_000_000, "fiscal_period": None, "published_at": None, "provider": "fintrace_calculator"},
        ],
        peer_validation={
            "valid": True,
            "errors": [],
            "warnings": [],
            "recalculated_values": {"implied_price_PE": 1920.0},
            "evidence_coverage": 0.98,
        },
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPeerValuationTab:
    """Peer Valuation tab builder tests."""

    def test_creates_sheet(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        assert "Peer Valuation" in wb.sheetnames
        assert ws.max_row > 0
        assert ws.max_column > 0

    def test_header_present(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        assert "PEER VALUATION" in str(ws.cell(row=1, column=1).value)

    def test_target_symbol_displayed(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "600519.SH" in values

    def test_target_name_displayed(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "贵州茅台" in values

    def test_peer_count_matches(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        # Count rows with peer symbols
        peer_rows = [r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=2).value in {"000858.SZ", "600809.SH", "000568.SZ", "002304.SZ", "603369.SH", "600779.SH"}]
        assert len(peer_rows) == 6

    def test_multiple_summary_present(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "PE" in values
        assert "PB" in values
        assert "PS" in values

    def test_validation_pass_status(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "PASS ✓" in values

    def test_bank_boundary_warning(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        data.is_bank_or_insurer = True
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [str(ws.cell(row=r, column=1).value or "") for r in range(1, ws.max_row + 1)]
        assert any("Financial-Institution" in v for v in values)

    def test_none_values_displayed_as_dash(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_peer_data()
        data.net_profit = None
        builder = PeerValuationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "—" in values


class TestValidationTab:
    """Validation tab builder tests."""

    def test_creates_sheet(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        assert "Validation" in wb.sheetnames
        assert ws.max_row > 0

    def test_header_present(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        assert "VALIDATION" in str(ws.cell(row=1, column=1).value)

    def test_symbol_displayed(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "600519.SH" in values

    def test_snapshot_id_displayed(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "600519.SH_20260809_v1" in values

    def test_pass_status_shown(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "PASS ✓" in values

    def test_fail_status_shown(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        data.valid = False
        data.errors = ["calculation_mismatch:calc_market_cap"]
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "FAIL ✗" in values

    def test_errors_displayed(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        data.errors = ["error_one", "error_two"]
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "error_one" in values
        assert "error_two" in values

    def test_warnings_displayed(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        data.warnings = ["peer_count_below_4_low_confidence"]
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=2).value for r in range(1, ws.max_row + 1)]
        assert "peer_count_below_4_low_confidence" in values

    def test_evidence_records_index(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "fact_600519_SH_close_20260809_RAW" in values

    def test_recalculated_values_shown(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "market_cap" in values

    def test_peer_validation_section(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        values = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert "PEER VALUATION VALIDATION" in values

    def test_empty_evidence_records(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        data.evidence_records = []
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        # Should not crash, just skip the section
        assert ws.max_row > 0

    def test_empty_peer_validation(self):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        data = _make_validation_data()
        data.peer_validation = {}
        builder = ValidationTabBuilder(data)
        ws = builder.create_tab(wb)
        assert ws.max_row > 0
