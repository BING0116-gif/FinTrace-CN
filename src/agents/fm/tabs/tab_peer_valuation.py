"""
Tab 11: Peer Valuation Tab Builder

Professional A-share peer multiple valuation worksheet.

This module creates the "Peer Valuation" tab that displays deterministic
peer-multiple analysis for A-share companies following the FinTrace-CN
valuation framework:

- Target company profile and period basis
- Peer selection decisions with inclusion/exclusion reasons
- Multiple summary (PE, PB, PS) with median, P25, P75, implied prices
- Industry policy notes (financial institution boundary, etc.)
- Evidence coverage metrics

All values are computed deterministically in Python; the Excel sheet
displays them as static values with cross-references to source tabs
where applicable.
"""

from typing import Dict, List, Optional, Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from ..financial_model_builder import ExcelFormats


# ---------------------------------------------------------------------------
# Data container passed from the CN peer-workflow pipeline
# ---------------------------------------------------------------------------

class PeerValuationData:
    """Immutable snapshot of peer-valuation results for Excel rendering."""

    def __init__(
        self,
        *,
        target_symbol: str,
        target_name: str,
        industry_code: str,
        period_basis: str,
        is_bank_or_insurer: bool,
        raw_price: float,
        total_shares: float,
        net_profit: Optional[float],
        book_equity: Optional[float],
        revenue: Optional[float],
        market_cap: float,
        peers: List[Dict[str, Any]],          # each: {symbol, name, included, reason}
        multiples: Dict[str, Dict[str, Any]], # key: PE|PB|PS → {median, included_symbols, excluded, confidence, implied_price}
        validation: Dict[str, Any],           # {valid, errors, warnings, recalculated_values, evidence_coverage}
    ):
        self.target_symbol = target_symbol
        self.target_name = target_name
        self.industry_code = industry_code
        self.period_basis = period_basis
        self.is_bank_or_insurer = is_bank_or_insurer
        self.raw_price = raw_price
        self.total_shares = total_shares
        self.net_profit = net_profit
        self.book_equity = book_equity
        self.revenue = revenue
        self.market_cap = market_cap
        self.peers = peers
        self.multiples = multiples
        self.validation = validation


# ---------------------------------------------------------------------------
# Tab builder
# ---------------------------------------------------------------------------

class PeerValuationTabBuilder:
    """
    Builds the Peer Valuation tab from a :class:`PeerValuationData` instance.

    Layout (rows):
        1   Header
        3-9 Target Company Profile & Financials
       11-14 Period Basis & Industry Policy
       16-N Peer Selection Decisions
      N+2-N+8 Multiple Summary (PE / PB / PS)
      N+10  Evidence Coverage & Validation Summary
    """

    def __init__(self, data: PeerValuationData):
        self.data = data

    # -- public API ----------------------------------------------------------

    def create_tab(self, workbook: openpyxl.Workbook) -> Worksheet:
        """Create or replace the *Peer Valuation* sheet."""
        if "Peer Valuation" in workbook.sheetnames:
            ws = workbook["Peer Valuation"]
            workbook.remove(ws)

        ws = workbook.create_sheet("Peer Valuation", 10)  # position 10 (11th tab)

        row = 1
        row = self._header(ws, row)
        row = self._target_profile(ws, row)
        row = self._period_and_policy(ws, row)
        row = self._peer_decisions(ws, row)
        row = self._multiple_summary(ws, row)
        row = self._validation_summary(ws, row)

        self._format(ws)
        return ws

    # -- section builders ----------------------------------------------------

    @staticmethod
    def _header(ws: Worksheet, row: int) -> int:
        ws.cell(row=row, column=1, value="PEER VALUATION — A-SHARE MULTIPLE ANALYSIS")
        ws.cell(row=row, column=1).font = Font(bold=True, size=14)
        return row + 2

    def _target_profile(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="TARGET COMPANY")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        rows_data = [
            ("Symbol", d.target_symbol),
            ("Name", d.target_name),
            ("Industry Code", d.industry_code),
            ("Entity Type", "Financial Institution" if d.is_bank_or_insurer else "Operating Company"),
            ("RAW Price (CNY)", d.raw_price),
            ("Total Shares", d.total_shares),
            ("Market Cap (CNY)", d.market_cap),
        ]
        for label, val in rows_data:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=val)
            row += 1

        # Key financials used in multiples
        ws.cell(row=row, column=1, value="")
        row += 1
        ws.cell(row=row, column=1, value="KEY FINANCIALS (Period Basis)")
        ws.cell(row=row, column=1).font = Font(bold=True)
        row += 1

        financials = [
            ("Net Profit (TTM / Period)", d.net_profit),
            ("Book Equity", d.book_equity),
            ("Revenue", d.revenue),
        ]
        for label, val in financials:
            ws.cell(row=row, column=1, value=label)
            ws.cell(row=row, column=2, value=_fmt_num(val))
            row += 1

        return row + 1

    def _period_and_policy(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="PERIOD BASIS & INDUSTRY POLICY")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        ws.cell(row=row, column=1, value="Period Basis")
        ws.cell(row=row, column=2, value=d.period_basis)
        row += 1

        if d.is_bank_or_insurer:
            ws.cell(row=row, column=1, value="⚠️ Financial-Institution Boundary")
            ws.cell(row=row, column=1).font = Font(bold=True, color="FF0000")
            row += 1
            ws.cell(row=row, column=1, value="Policy")
            ws.cell(
                row=row, column=2,
                value="Only PE and PB multiples are shown. EV/EBITDA and generic DCF are disabled for banks/insurers.",
            )
            row += 1
        else:
            ws.cell(row=row, column=1, value="Applicable Multiples")
            ws.cell(row=row, column=2, value="PE, PB, PS (EV/EBITDA available when EBITDA > 0)")
            row += 1

        return row + 1

    def _peer_decisions(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="PEER SELECTION DECISIONS")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        # Header row
        ws.cell(row=row, column=1, value="#")
        ws.cell(row=row, column=2, value="Symbol")
        ws.cell(row=row, column=3, value="Included")
        ws.cell(row=row, column=4, value="Reason")
        for c in range(1, 5):
            ws.cell(row=row, column=c).font = Font(bold=True)
            ws.cell(row=row, column=c).fill = PatternFill(
                start_color=ExcelFormats.HEADER_COLOR,
                end_color=ExcelFormats.HEADER_COLOR,
                fill_type="solid",
            )
        row += 1

        for idx, peer in enumerate(d.peers, 1):
            ws.cell(row=row, column=1, value=idx)
            ws.cell(row=row, column=2, value=peer.get("symbol", ""))
            ws.cell(row=row, column=3, value="✓" if peer.get("included") else "✗")
            ws.cell(row=row, column=4, value=peer.get("reason", ""))
            if peer.get("included"):
                ws.cell(row=row, column=3).font = Font(color="00AA00", bold=True)
            else:
                ws.cell(row=row, column=3).font = Font(color="CC0000", bold=True)
            row += 1

        return row + 1

    def _multiple_summary(self, ws: Worksheet, row: int) -> int:
        d = self.data
        ws.cell(row=row, column=1, value="MULTIPLE SUMMARY")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        # Column headers
        headers = ["Multiple", "Median", "Confidence", "Implied Price (CNY)", "Included Count", "Excluded"]
        for col, h in enumerate(headers, 1):
            ws.cell(row=row, column=col, value=h)
            ws.cell(row=row, column=col).font = Font(bold=True)
            ws.cell(row=row, column=col).fill = PatternFill(
                start_color=ExcelFormats.HEADER_COLOR,
                end_color=ExcelFormats.HEADER_COLOR,
                fill_type="solid",
            )
        row += 1

        for name in ("PE", "PB", "PS"):
            info = d.multiples.get(name, {})
            median = info.get("median")
            confidence = info.get("confidence", "unavailable")
            implied = info.get("implied_price")
            included = info.get("included_symbols", [])
            excluded = info.get("excluded", {})

            ws.cell(row=row, column=1, value=name)
            ws.cell(row=row, column=2, value=_fmt_num(median))
            ws.cell(row=row, column=3, value=confidence)
            ws.cell(row=row, column=4, value=_fmt_num(implied))
            ws.cell(row=row, column=5, value=len(included))
            ws.cell(row=row, column=6, value=", ".join(f"{k}({v})" for k, v in excluded.items()) if excluded else "—")

            # Highlight gold for final implied price
            if implied is not None:
                ws.cell(row=row, column=4).fill = PatternFill(
                    start_color="FFD700", end_color="FFD700", fill_type="solid"
                )
                ws.cell(row=row, column=4).font = Font(bold=True)

            row += 1

        return row + 1

    def _validation_summary(self, ws: Worksheet, row: int) -> int:
        d = self.data
        v = d.validation

        ws.cell(row=row, column=1, value="VALIDATION SUMMARY")
        ws.cell(row=row, column=1).font = Font(bold=True, size=11, underline="single")
        row += 1

        valid = v.get("valid", False)
        status_label = "PASS ✓" if valid else "FAIL ✗"
        status_font = Font(bold=True, size=12, color="00AA00" if valid else "CC0000")
        ws.cell(row=row, column=1, value="Status")
        ws.cell(row=row, column=2, value=status_label)
        ws.cell(row=row, column=2).font = status_font
        row += 1

        ws.cell(row=row, column=1, value="Evidence Coverage")
        ws.cell(row=row, column=2, value=f"{v.get('evidence_coverage', 0):.1%}")
        row += 1

        errors = v.get("errors", [])
        if errors:
            ws.cell(row=row, column=1, value="Errors")
            ws.cell(row=row, column=1).font = Font(bold=True, color="CC0000")
            row += 1
            for err in errors:
                ws.cell(row=row, column=2, value=err)
                ws.cell(row=row, column=2).font = Font(color="CC0000")
                row += 1
        else:
            ws.cell(row=row, column=1, value="Errors")
            ws.cell(row=row, column=2, value="None")
            row += 1

        warnings = v.get("warnings", [])
        if warnings:
            ws.cell(row=row, column=1, value="Warnings")
            ws.cell(row=row, column=1).font = Font(bold=True, color="FF8C00")
            row += 1
            for w in warnings:
                ws.cell(row=row, column=2, value=w)
                ws.cell(row=row, column=2).font = Font(color="FF8C00")
                row += 1

        # Recalculated values
        recalcs = v.get("recalculated_values", {})
        if recalcs:
            ws.cell(row=row, column=1, value="")
            row += 1
            ws.cell(row=row, column=1, value="Recalculated Implied Prices")
            ws.cell(row=row, column=1).font = Font(bold=True)
            row += 1
            for key, val in recalcs.items():
                ws.cell(row=row, column=1, value=key)
                ws.cell(row=row, column=2, value=_fmt_num(val))
                row += 1

        return row + 2

    # -- formatting ----------------------------------------------------------

    @staticmethod
    def _format(ws: Worksheet) -> None:
        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 22
        ws.column_dimensions["C"].width = 16
        ws.column_dimensions["D"].width = 28
        ws.column_dimensions["E"].width = 14
        ws.column_dimensions["F"].width = 30
        ws.sheet_view.showGridLines = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_num(value: Optional[float], digits: int = 2) -> str:
    """Format a numeric value for Excel display; returns '—' for None."""
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"
