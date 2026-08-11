"""
Tab 12: Validation Tab Builder

Professional A-share research validation worksheet.

This module creates the "Validation" tab that presents the deterministic
Validator results for FinTrace-CN research. It covers:

- Overall validation status (PASS / FAIL)
- Recalculated financial values (market cap, implied prices, etc.)
- Evidence coverage rate
- Errors (blocking issues)
- Warnings (non-blocking concerns)
- Cross-references to source tabs and evidence IDs

The Validator is a pure-Python component; this tab merely renders its
output in a readable Excel format so analysts can inspect every check.
"""

from typing import Dict, List, Optional, Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from ..financial_model_builder import ExcelFormats


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

class ValidationData:
    """Immutable snapshot of Validator output for Excel rendering."""

    def __init__(
        self,
        *,
        symbol: str,
        research_as_of: str,
        snapshot_id: str,
        valid: bool,
        errors: List[str],
        warnings: List[str],
        recalculated_values: Dict[str, float],
        evidence_coverage: float,
        evidence_records: Optional[List[Dict[str, Any]]] = None,
        peer_validation: Optional[Dict[str, Any]] = None,
        period_consistency: Optional[Dict[str, Any]] = None,
    ):
        self.symbol = symbol
        self.research_as_of = research_as_of
        self.snapshot_id = snapshot_id
        self.valid = valid
        self.errors = errors
        self.warnings = warnings
        self.recalculated_values = recalculated_values
        self.evidence_coverage = evidence_coverage
        self.evidence_records = evidence_records or []
        self.peer_validation = peer_validation or {}
        self.period_consistency = period_consistency or {}


# ---------------------------------------------------------------------------
# Tab builder
# ---------------------------------------------------------------------------

class ValidationTabBuilder:
    """
    Builds the Validation tab from a :class:`ValidationData` instance.

    Layout:
        1   Header
        3-5 Research Context
        7   Overall Status
        9-12 Recalculated Values
       14   Evidence Coverage
       16-  Errors
       N+2  Warnings
       N+4  Evidence Records Index
    """

    def __init__(self, data: ValidationData):
        self.data = data

    # -- public API ----------------------------------------------------------

    def create_tab(self, workbook: openpyxl.Workbook) -> Worksheet:
        """Create or replace the *Validation* sheet."""
        if "Validation" in workbook.sheetnames:
            ws = workbook["Validation"]
            workbook.remove(ws)

        ws = workbook.create_sheet("Validation", 11)  # position 11 (12th tab)

        row = 1
        row = self._header(ws, row)
        row = self._research_context(ws, row)
        row = self._overall_status(ws, row)
        row = self._recalculated_values(ws, row)
        row = self._evidence_coverage(ws, row)
        row = self._errors_section(ws, row)
        row = self._warnings_section(ws, row)
        row = self._evidence_index(ws, row)
        row = self._peer_validation_section(ws, row)

        self._format(ws)
        return ws

    # -- section builders ----------------------------------------------------

    @staticmethod
    def _header(ws: Worksheet, row: int) -> int:
        ws.cell(row=row, column=1, value="VALIDATION — FINTRACE-CN RESEARCH VERIFICATION")
        ws.cell(row=row, column=1).font = Font(bold=True, size=14)
        return row + 2

    def _research_context(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="RESEARCH CONTEXT")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        context_rows = [
            ("Symbol", d.symbol),
            ("Research As-Of", d.research_as_of),
            ("Snapshot ID", d.snapshot_id),
        ]
        for label, val in context_rows:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=val)
            row += 1

        return row + 1

    def _overall_status(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="OVERALL VALIDATION STATUS")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        status = "PASS ✓" if d.valid else "FAIL ✗"
        color = "00AA00" if d.valid else "CC0000"
        ws.cell(row=row, column=1, value="Result")
        ws.cell(row=row, column=2, value=status)
        ws.cell(row=row, column=2).font = Font(bold=True, size=12, color=color)
        ws.cell(row=row, column=2).fill = PatternFill(
            start_color="FFFFCC" if d.valid else "FFCCCC",
            end_color="FFFFCC" if d.valid else "FFCCCC",
            fill_type="solid",
        )
        row += 1

        if d.valid:
            ws.cell(row=row, column=1, value="Interpretation")
            ws.cell(
                row=row, column=2,
                value="All deterministic checks passed. Numbers are traceable and internally consistent.",
            )
            row += 1
        else:
            ws.cell(row=row, column=1, value="Interpretation")
            ws.cell(
                row=row, column=2,
                value="One or more blocking checks failed. The research report should not be treated as verified.",
            )
            ws.cell(row=row, column=2).font = Font(color="CC0000")
            row += 1

        return row + 1

    def _recalculated_values(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="RECALCULATED VALUES")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        ws.cell(row=row, column=1, value="Metric")
        ws.cell(row=row, column=2, value="Value")
        for c in (1, 2):
            ws.cell(row=row, column=c).font = Font(bold=True)
            ws.cell(row=row, column=c).fill = PatternFill(
                start_color=ExcelFormats.HEADER_COLOR,
                end_color=ExcelFormats.HEADER_COLOR,
                fill_type="solid",
            )
        row += 1

        if d.recalculated_values:
            for key, val in d.recalculated_values.items():
                ws.cell(row=row, column=1, value=key)
                ws.cell(row=row, column=2, value=_fmt_num(val))
                row += 1
        else:
            ws.cell(row=row, column=1, value="—")
            ws.cell(row=row, column=2, value="No recalculated values produced by Validator.")
            row += 1

        return row + 1

    def _evidence_coverage(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="EVIDENCE COVERAGE")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        coverage = d.evidence_coverage
        ws.cell(row=row, column=1, value="Citation Coverage Rate")
        ws.cell(row=row, column=2, value=f"{coverage:.1%}")
        ws.cell(row=row, column=2).number_format = '0.0%'
        row += 1

        if coverage >= 0.95:
            ws.cell(row=row, column=1, value="Assessment")
            ws.cell(row=row, column=2, value="≥ 95% — meets FinTrace-CN target.")
            ws.cell(row=row, column=2).font = Font(color="00AA00", bold=True)
        elif coverage >= 0.80:
            ws.cell(row=row, column=1, value="Assessment")
            ws.cell(row=row, column=2, value="80–95% — acceptable but below target; review missing citations.")
            ws.cell(row=row, column=2).font = Font(color="FF8C00", bold=True)
        else:
            ws.cell(row=row, column=1, value="Assessment")
            ws.cell(row=row, column=2, value="< 80% — insufficient evidence coverage; report not verified.")
            ws.cell(row=row, column=2).font = Font(color="CC0000", bold=True)
        row += 1

        return row + 1

    def _errors_section(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="ERRORS (Blocking)")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single", color="CC0000")
        row += 1

        if d.errors:
            ws.cell(row=row, column=1, value="#")
            ws.cell(row=row, column=2, value="Error Code / Message")
            for c in (1, 2):
                ws.cell(row=row, column=c).font = Font(bold=True)
                ws.cell(row=row, column=c).fill = PatternFill(
                    start_color="FFCCCC",
                    end_color="FFCCCC",
                    fill_type="solid",
                )
            row += 1
            for idx, err in enumerate(d.errors, 1):
                ws.cell(row=row, column=1, value=idx)
                ws.cell(row=row, column=2, value=err)
                ws.cell(row=row, column=2).font = Font(color="CC0000")
                row += 1
        else:
            ws.cell(row=row, column=1, value="No errors — all blocking checks passed.")
            ws.cell(row=row, column=1).font = Font(color="00AA00", italic=True)
            row += 1

        return row + 1

    def _warnings_section(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="WARNINGS (Non-Blocking)")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single", color="FF8C00")
        row += 1

        if d.warnings:
            ws.cell(row=row, column=1, value="#")
            ws.cell(row=row, column=2, value="Warning Code / Message")
            for c in (1, 2):
                ws.cell(row=row, column=c).font = Font(bold=True)
                ws.cell(row=row, column=c).fill = PatternFill(
                    start_color="FFF2CC",
                    end_color="FFF2CC",
                    fill_type="solid",
                )
            row += 1
            for idx, w in enumerate(d.warnings, 1):
                ws.cell(row=row, column=1, value=idx)
                ws.cell(row=row, column=2, value=w)
                ws.cell(row=row, column=2).font = Font(color="FF8C00")
                row += 1
        else:
            ws.cell(row=row, column=1, value="No warnings.")
            ws.cell(row=row, column=1).font = Font(italic=True)
            row += 1

        return row + 1

    def _evidence_index(self, ws: Worksheet, row: int) -> int:
        d = self.data
        records = d.evidence_records
        if not records:
            return row

        ws.cell(row=row, column=1, value="EVIDENCE RECORDS INDEX")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        headers = ["Evidence ID", "Kind", "Metric", "Value", "Period", "Provider"]
        for col, h in enumerate(headers, 1):
            ws.cell(row=row, column=col, value=h)
            ws.cell(row=row, column=col).font = Font(bold=True)
            ws.cell(row=row, column=col).fill = PatternFill(
                start_color=ExcelFormats.HEADER_COLOR,
                end_color=ExcelFormats.HEADER_COLOR,
                fill_type="solid",
            )
        row += 1

        for rec in records:
            ws.cell(row=row, column=1, value=rec.get("evidence_id", ""))
            ws.cell(row=row, column=2, value=rec.get("kind", ""))
            ws.cell(row=row, column=3, value=rec.get("metric", ""))
            ws.cell(row=row, column=4, value=_fmt_num(rec.get("value")))
            ws.cell(row=row, column=5, value=rec.get("fiscal_period") or rec.get("published_at") or "—")
            ws.cell(row=row, column=6, value=rec.get("provider", ""))
            row += 1

        return row + 1

    def _peer_validation_section(self, ws: Worksheet, row: int) -> int:
        pv = self.data.peer_validation
        if not pv:
            return row

        ws.cell(row=row, column=1, value="PEER VALUATION VALIDATION")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        pv_valid = pv.get("valid", False)
        ws.cell(row=row, column=1, value="Peer Valuation Status")
        ws.cell(row=row, column=2, value="PASS ✓" if pv_valid else "FAIL ✗")
        ws.cell(row=row, column=2).font = Font(
            bold=True,
            color="00AA00" if pv_valid else "CC0000",
        )
        row += 1

        pv_errors = pv.get("errors", [])
        if pv_errors:
            ws.cell(row=row, column=1, value="Peer Valuation Errors")
            ws.cell(row=row, column=1).font = Font(bold=True, color="CC0000")
            row += 1
            for err in pv_errors:
                ws.cell(row=row, column=2, value=err)
                ws.cell(row=row, column=2).font = Font(color="CC0000")
                row += 1

        pv_warnings = pv.get("warnings", [])
        if pv_warnings:
            ws.cell(row=row, column=1, value="Peer Valuation Warnings")
            ws.cell(row=row, column=1).font = Font(bold=True, color="FF8C00")
            row += 1
            for w in pv_warnings:
                ws.cell(row=row, column=2, value=w)
                ws.cell(row=row, column=2).font = Font(color="FF8C00")
                row += 1

        return row + 1

    # -- formatting ----------------------------------------------------------

    @staticmethod
    def _format(ws: Worksheet) -> None:
        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 55
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 18
        ws.column_dimensions["E"].width = 16
        ws.column_dimensions["F"].width = 18
        ws.sheet_view.showGridLines = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_num(value, digits: int = 2) -> str:
    """Format a numeric value for Excel display; returns '—' for None."""
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)
