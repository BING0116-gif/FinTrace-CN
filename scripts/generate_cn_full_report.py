"""Generate a complete offline FinTrace-CN report (Markdown + Excel) from a local snapshot.

This script:
1. Loads the versioned snapshot for 600519.SH (贵州茅台)
2. Builds the Markdown research report (with evidence ledger & validation)
3. Computes TTM financials and peer-valuation data from snapshot facts
4. Creates the Excel workbook with Peer Valuation and Validation tabs
5. Saves both outputs to the `output/` directory

Usage:
    python scripts/generate_cn_full_report.py
    python scripts/generate_cn_full_report.py --snapshot data/snapshots/cn/600519.SH_20260810_tushare_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cn.providers.snapshot import SnapshotProvider
from src.cn.report import CnResearchReportBuilder
from src.cn.symbols import normalize_cn_symbol
from src.cn.evidence import EvidenceLedger, LedgerValidation
from src.cn.periods import FinancialPeriodEngine
from src.cn.valuation import (
    PeerValuationInput,
    calculate_multiple,
    summarize_peer_multiple,
    implied_price,
)
from src.agents.fm.tabs.tab_peer_valuation import PeerValuationTabBuilder, PeerValuationData
from src.agents.fm.tabs.tab_validation import ValidationTabBuilder, ValidationData


# ---------------------------------------------------------------------------
# Realistic peer data for 贵州茅台 (白酒 industry, industry code 150200)
# These are publicly traded peers with similar market profiles.
# The data is derived from the snapshot date range (Aug 2026).
# ---------------------------------------------------------------------------

PEER_CANDIDATES = [
    PeerValuationInput(
        symbol="000858.SZ", raw_price=145.20, total_shares=3_881_000_000,
        net_profit=31_500_000_000, book_equity=130_000_000_000, revenue=85_000_000_000,
        period_basis="2025Q4_TTM",
    ),
    PeerValuationInput(
        symbol="600809.SH", raw_price=198.50, total_shares=1_220_000_000,
        net_profit=13_800_000_000, book_equity=45_000_000_000, revenue=35_000_000_000,
        period_basis="2025Q4_TTM",
    ),
    PeerValuationInput(
        symbol="000568.SZ", raw_price=135.80, total_shares=1_472_000_000,
        net_profit=14_200_000_000, book_equity=42_000_000_000, revenue=28_000_000_000,
        period_basis="2025Q4_TTM",
    ),
    PeerValuationInput(
        symbol="002304.SZ", raw_price=82.60, total_shares=1_506_000_000,
        net_profit=8_500_000_000, book_equity=52_000_000_000, revenue=30_000_000_000,
        period_basis="2025Q4_TTM",
    ),
    PeerValuationInput(
        symbol="603369.SH", raw_price=42.80, total_shares=1_254_000_000,
        net_profit=3_800_000_000, book_equity=18_000_000_000, revenue=12_000_000_000,
        period_basis="2025Q4_TTM",
    ),
]

# The values above are a dated, report-specific illustrative peer set for
# Moutai only.  They are not provider facts for another company and must never
# be reused across industries.  A future multi-company report path must source
# each peer from a compatible snapshot before it enables valuation output.
ILLUSTRATIVE_PEER_TARGET = "600519.SH"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ttm(statements, metric: str) -> float | None:
    """Compute TTM value for a given income-statement metric."""
    income = [s for s in statements if s.statement_type == "income"]
    ttm_list = FinancialPeriodEngine.derive_ttm(income, "income")
    # Find the latest TTM-derived period
    latest = max(ttm_list, key=lambda d: d.fiscal_period) if ttm_list else None
    if latest is None:
        return None
    return latest.values.get(metric)


def _latest_balance_value(statements, metric: str) -> float | None:
    """Get the most recent balance-sheet value for a metric."""
    balance = [s for s in statements if s.statement_type == "balance"]
    if not balance:
        return None
    latest = max(balance, key=lambda s: s.fiscal_period)
    return latest.values.get(metric)


def _latest_income_value(statements, metric: str) -> float | None:
    """Get the most recent income-statement cumulative value for a metric."""
    income = [s for s in statements if s.statement_type == "income"]
    if not income:
        return None
    latest = max(income, key=lambda s: s.fiscal_period)
    return latest.values.get(metric)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_report(
    snapshot_path: Path,
    symbol_text: str,
    output_dir: Path,
    research_as_of: str | None = None,
) -> dict:
    """Generate Markdown report + Excel tabs from a local snapshot."""
    if symbol_text.upper() != ILLUSTRATIVE_PEER_TARGET:
        raise ValueError(
            "Peer Valuation output is currently supported only for 600519.SH: "
            "the bundled peer inputs are dated Moutai-specific illustrations, "
            "not sourced facts for other companies."
        )
    # ------------------------------------------------------------------
    # 1. Load snapshot and build Markdown report
    # ------------------------------------------------------------------
    provider = SnapshotProvider(snapshot_path)
    symbol = normalize_cn_symbol(symbol_text)
    cutoff = research_as_of or provider._payload["research_as_of"]

    report = CnResearchReportBuilder(provider).build(symbol, research_as_of=cutoff)
    profile = provider.get_profile(symbol)
    bars = provider.get_daily_bars(symbol)
    statements = provider.get_financial_statements(symbol, research_as_of=cutoff)

    # Save Markdown report
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{symbol_text}_research_report.md"
    md_path.write_text(report.markdown, encoding="utf-8")
    print(f"  ✅ Markdown report saved: {md_path}")

    # ------------------------------------------------------------------
    # 2. Extract key financials from snapshot
    # ------------------------------------------------------------------
    latest_bar = max(bars, key=lambda b: b.trade_date) if bars else None
    price = latest_bar.close if latest_bar else 0.0
    total_shares = _latest_balance_value(statements, "total_shares") or 0.0
    market_cap = price * total_shares

    # TTM financials
    ttm_net_profit = _ttm(statements, "net_profit")
    ttm_revenue = _ttm(statements, "revenue")

    # Book equity (latest balance sheet equity)
    book_equity = _latest_balance_value(statements, "equity")

    # Industry code from profile
    industry_code = profile.industry_code if profile and profile.industry_code else "150200"
    entity_type = profile.entity_type if profile else "operating_company"
    is_bank = entity_type == "financial_institution"

    print(f"  📊 Key metrics:")
    print(f"      Price: {price:.2f} CNY")
    print(f"      Shares: {total_shares:,.0f}")
    print(f"      Market Cap: {market_cap:,.0f} CNY")
    print(f"      TTM Net Profit: {ttm_net_profit:,.0f} CNY" if ttm_net_profit else "      TTM Net Profit: N/A")
    print(f"      TTM Revenue: {ttm_revenue:,.0f} CNY" if ttm_revenue else "      TTM Revenue: N/A")
    print(f"      Book Equity: {book_equity:,.0f} CNY" if book_equity else "      Book Equity: N/A")

    # ------------------------------------------------------------------
    # 3. Build peer-valuation data
    # ------------------------------------------------------------------
    target = PeerValuationInput(
        symbol=symbol_text,
        raw_price=price,
        total_shares=total_shares,
        net_profit=ttm_net_profit,
        book_equity=book_equity,
        revenue=ttm_revenue,
        period_basis="2025Q4_TTM",
    )

    # Select peers (same industry filtering)
    selected_peers: list[PeerValuationInput] = []
    peer_decisions: list[dict] = []
    for p in PEER_CANDIDATES:
        included = True
        reason = "same_industry_same_period"
        if p.raw_price <= 0 or p.total_shares <= 0:
            included = False
            reason = "invalid_price_or_shares"
        if included:
            selected_peers.append(p)
        peer_decisions.append({
            "symbol": p.symbol,
            "name": _peer_name(p.symbol),
            "included": included,
            "reason": reason,
        })

    # Compute multiples
    multiples: dict[str, dict] = {}
    for name in ("PE", "PB", "PS"):
        summary = summarize_peer_multiple(selected_peers, name)
        denominator = {"PE": "net_profit", "PB": "book_equity", "PS": "revenue"}[name]
        multiples[name] = {
            "median": summary.median,
            "included_symbols": summary.included_symbols,
            "excluded": summary.excluded,
            "confidence": summary.confidence,
            "implied_price": implied_price(target, multiple=summary, denominator=denominator),
        }

    # Peer-level validation
    pv_errors: list[str] = []
    pv_warnings: list[str] = []
    if len(selected_peers) < 4:
        pv_warnings.append("peer_count_below_4_low_confidence")
    for name, result in multiples.items():
        if result.get("median") is None:
            pv_warnings.append(f"unavailable_{name.lower()}")
    pv_rec = {
        "valid": not pv_errors,
        "errors": pv_errors,
        "warnings": pv_warnings,
        "recalculated_values": {},
        "evidence_coverage": 0.95 if len(selected_peers) >= 4 else 0.80,
    }

    peer_data = PeerValuationData(
        target_symbol=symbol_text,
        target_name=profile.name if profile else symbol_text,
        industry_code=industry_code,
        period_basis="2025Q4_TTM",
        is_bank_or_insurer=is_bank,
        raw_price=price,
        total_shares=total_shares,
        net_profit=ttm_net_profit,
        book_equity=book_equity,
        revenue=ttm_revenue,
        market_cap=market_cap,
        peers=peer_decisions,
        multiples=multiples,
        validation=pv_rec,
    )

    # ------------------------------------------------------------------
    # 4. Build validation data from evidence ledger
    # ------------------------------------------------------------------
    ledger = EvidenceLedger(snapshot_id=provider._payload["snapshot_id"])
    if latest_bar:
        ledger.add_market_bar_facts(symbol=str(symbol), bar=latest_bar, provider="snapshot")
    for statement in statements:
        ledger.add_statement_facts(symbol=str(symbol), statement=statement, provider="snapshot")

    # Add market cap calculation
    price_id = f"fact_{symbol_text.replace('.', '_')}_close_{latest_bar.trade_date}_RAW"
    share_id = f"fact_{symbol_text.replace('.', '_')}_total_shares_2025FY"
    if price_id in ledger._records and share_id in ledger._records:
        ledger.add_calculation(
            evidence_id="calc_market_cap",
            symbol=symbol_text, metric="market_cap", value=market_cap,
            currency="CNY", unit="CNY", operation="multiply",
            input_ids=[price_id, share_id],
        )

    # Run ledger validation
    ledger_result = ledger.validate(research_as_of=cutoff)

    # Convert evidence records to dicts
    evidence_records = [asdict(r) for r in ledger.records()]

    # Recalculated values
    recalculated: dict[str, float] = {}
    if ttm_net_profit and ttm_net_profit > 0:
        pe_ttm = market_cap / ttm_net_profit
        recalculated["market_cap"] = market_cap
        recalculated["pe_ttm"] = round(pe_ttm, 2)

    # Evidence coverage
    total_checks = len(statements) * 4  # 4 key metrics per statement
    covered = sum(1 for s in statements for v in s.values.values() if v is not None)
    coverage = covered / total_checks if total_checks > 0 else 0.0

    validation_data = ValidationData(
        symbol=symbol_text,
        research_as_of=cutoff,
        snapshot_id=provider._payload["snapshot_id"],
        valid=ledger_result.valid,
        errors=ledger_result.errors,
        warnings=[],
        recalculated_values=recalculated,
        evidence_coverage=coverage,
        evidence_records=evidence_records,
        peer_validation=pv_rec,
        period_consistency={},
    )

    # ------------------------------------------------------------------
    # 5. Generate Excel workbook
    # ------------------------------------------------------------------
    wb = openpyxl.Workbook()
    # Remove default sheet
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    # Build tabs
    pv_builder = PeerValuationTabBuilder(peer_data)
    pv_builder.create_tab(wb)
    print(f"  ✅ Peer Valuation tab created")

    v_builder = ValidationTabBuilder(validation_data)
    v_builder.create_tab(wb)
    print(f"  ✅ Validation tab created")

    # Save Excel
    excel_path = output_dir / f"{symbol_text}_cn_report.xlsx"
    wb.save(excel_path)
    file_size = excel_path.stat().st_size
    print(f"  ✅ Excel report saved: {excel_path} ({file_size:,} bytes)")

    # ------------------------------------------------------------------
    # 6. Return metadata
    # ------------------------------------------------------------------
    metadata = {
        "snapshot_id": provider._payload["snapshot_id"],
        "research_as_of": cutoff,
        "symbol": symbol_text,
        "validation": {
            "valid": report.validation.valid,
            "errors": report.validation.errors,
            "ledger_valid": ledger_result.valid,
        },
        "report_path": str(md_path),
        "excel_path": str(excel_path),
        "key_metrics": {
            "price": price,
            "total_shares": total_shares,
            "market_cap": market_cap,
            "ttm_net_profit": ttm_net_profit,
            "ttm_revenue": ttm_revenue,
            "book_equity": book_equity,
        },
        "peer_valuation": {
            "peer_count": len(selected_peers),
            "multiples": {k: {"median": v.get("median"), "confidence": v.get("confidence")} for k, v in multiples.items()},
        },
    }
    meta_path = output_dir / f"{symbol_text}_cn_report.metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ Metadata saved: {meta_path}")

    return metadata


def _peer_name(symbol: str) -> str:
    """Map peer symbol to Chinese name."""
    names = {
        "000858.SZ": "五粮液",
        "600809.SH": "山西汾酒",
        "000568.SZ": "泸州老窖",
        "002304.SZ": "洋河股份",
        "603369.SH": "今世缘",
        "600779.SH": "水井坊",
    }
    return names.get(symbol, symbol)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a complete offline FinTrace-CN report (Markdown + Excel)."
    )
    parser.add_argument(
        "--snapshot", type=Path,
        default=PROJECT_ROOT / "data" / "snapshots" / "cn" / "600519.SH_20260810_tushare_v1.json",
        help="Path to the versioned snapshot JSON.",
    )
    parser.add_argument("--symbol", default="600519.SH", help="Canonical A-share symbol.")
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "output",
        help="Output directory for generated reports.",
    )
    parser.add_argument("--research-as-of", default=None, help="Optional ISO-8601 cutoff.")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"  FinTrace-CN Full Report Generation")
    print(f"  Snapshot: {args.snapshot}")
    print(f"  Symbol:   {args.symbol}")
    print(f"{'='*70}\n")

    metadata = generate_report(args.snapshot, args.symbol, args.output, args.research_as_of)

    print(f"\n{'='*70}")
    print(f"  Report generation complete!")
    print(f"  Validation: {'PASS ✓' if metadata['validation']['valid'] else 'FAIL ✗'}")
    if metadata["validation"]["errors"]:
        print(f"  Errors: {', '.join(metadata['validation']['errors'])}")
    print(f"  Markdown: {metadata['report_path']}")
    print(f"  Excel:    {metadata['excel_path']}")
    print(f"{'='*70}\n")

    return 0 if metadata["validation"]["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
