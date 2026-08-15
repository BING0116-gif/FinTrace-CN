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
from datetime import date
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
from src.cn.valuation import PeerValuationInput
from src.cn.peer_workflow import PeerCandidate, value_with_peers
from src.cn.industries import get_industry_code, is_financial_institution
from src.agents.fm.tabs.tab_peer_valuation import PeerValuationTabBuilder, PeerValuationData
from src.agents.fm.tabs.tab_validation import ValidationTabBuilder, ValidationData


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
    latest = _latest_balance_statement(statements)
    return latest.values.get(metric) if latest else None


def _latest_balance_statement(statements):
    balance = [s for s in statements if s.statement_type == "balance"]
    period_rank = {"Q1": 1, "H1": 2, "9M": 3, "FY": 4}
    def key(statement):
        period = statement.fiscal_period
        for suffix, rank in period_rank.items():
            if period.endswith(suffix):
                return int(period[:4]), rank
        return 0, 0
    return max(balance, key=key) if balance else None


def _latest_income_value(statements, metric: str) -> float | None:
    """Get the most recent income-statement cumulative value for a metric."""
    income = [s for s in statements if s.statement_type == "income"]
    if not income:
        return None
    latest = max(income, key=lambda s: s.fiscal_period)
    return latest.values.get(metric)


def _snapshot_candidate(snapshot_path: Path, *, cutoff: str) -> tuple[PeerCandidate, str]:
    """Create a valuation input entirely from one compatible local snapshot."""
    provider = SnapshotProvider(snapshot_path)
    symbol = normalize_cn_symbol(provider._payload["symbol"])
    statements = provider.get_financial_statements(symbol, research_as_of=cutoff)
    cutoff_date = cutoff[:10]
    bars = [item for item in provider.get_daily_bars(symbol) if item.trade_date <= cutoff_date]
    latest_bar = max(bars, key=lambda item: item.trade_date) if bars else None
    code = str(symbol).split(".")[0]
    industry_code = get_industry_code(code)
    if industry_code is None:
        raise ValueError(f"No frozen industry classification for {symbol}.")
    if latest_bar is None:
        raise ValueError(f"Snapshot has no RAW market bar for {symbol}.")
    valuation = PeerValuationInput(
        symbol=str(symbol), raw_price=latest_bar.close,
        total_shares=_latest_balance_value(statements, "total_shares") or 0.0,
        net_profit=_ttm(statements, "net_profit"),
        book_equity=_latest_balance_value(statements, "equity"),
        revenue=_ttm(statements, "revenue"),
        period_basis="TTM_SNAPSHOT_AS_OF",
    )
    evidence_ids = {"price": f"{provider._payload['snapshot_id']}:close:{latest_bar.trade_date}"}
    if valuation.total_shares > 0:
        evidence_ids["shares"] = f"{provider._payload['snapshot_id']}:total_shares"
    if valuation.net_profit is not None:
        evidence_ids["profit"] = f"{provider._payload['snapshot_id']}:ttm_net_profit"
    if valuation.book_equity is not None:
        evidence_ids["equity"] = f"{provider._payload['snapshot_id']}:equity"
    if valuation.revenue is not None:
        evidence_ids["revenue"] = f"{provider._payload['snapshot_id']}:ttm_revenue"
    profile = provider.get_profile(symbol)
    return PeerCandidate(valuation, industry_code, evidence_ids, is_financial_institution(code)), (profile.name if profile else str(symbol))


def _snapshot_peers(target_path: Path, *, snapshot_dir: Path, cutoff: str) -> tuple[PeerCandidate, str, list[PeerCandidate], dict[str, str]]:
    target, target_name = _snapshot_candidate(target_path, cutoff=cutoff)
    candidates: list[PeerCandidate] = []
    names = {target.valuation.symbol: target_name}
    for path in sorted(snapshot_dir.glob("*_tushare_v1.json")):
        if path.resolve() == target_path.resolve():
            continue
        # Keep the frozen cross-sectional peer window deliberately narrow.
        # A newer unrelated snapshot must not silently change this report.
        payload = json.loads(path.read_text(encoding="utf-8"))
        peer_date = str(payload.get("research_as_of", ""))[:10]
        target_date = cutoff[:10]
        if not peer_date or abs((date.fromisoformat(peer_date) - date.fromisoformat(target_date)).days) > 3:
            continue
        candidate, name = _snapshot_candidate(path, cutoff=cutoff)
        candidates.append(candidate)
        names[candidate.valuation.symbol] = name
    return target, target_name, candidates, names


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_report(
    snapshot_path: Path,
    symbol_text: str,
    output_dir: Path,
    research_as_of: str | None = None,
    peer_snapshot_dir: Path | None = None,
) -> dict:
    """Generate Markdown report + Excel tabs from a local snapshot."""
    # ------------------------------------------------------------------
    # 1. Load snapshot and build Markdown report
    # ------------------------------------------------------------------
    provider = SnapshotProvider(snapshot_path)
    symbol = normalize_cn_symbol(symbol_text)
    cutoff = research_as_of or provider._payload["research_as_of"]

    report = CnResearchReportBuilder(provider).build(symbol, research_as_of=cutoff)
    profile = provider.get_profile(symbol)
    bars = [item for item in provider.get_daily_bars(symbol) if item.trade_date <= cutoff[:10]]
    statements = provider.get_financial_statements(symbol, research_as_of=cutoff)

    # Save Markdown report
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{symbol_text}_research_report.md"
    md_path.write_text(report.markdown, encoding="utf-8")
    print(f"  OK: Markdown report saved: {md_path}")

    # ------------------------------------------------------------------
    # 2. Extract key financials from snapshot
    # ------------------------------------------------------------------
    latest_bar = max(bars, key=lambda b: b.trade_date) if bars else None
    price = latest_bar.close if latest_bar else 0.0
    latest_balance = _latest_balance_statement(statements)
    total_shares = (latest_balance.values.get("total_shares") if latest_balance else None) or 0.0
    market_cap = price * total_shares

    # TTM financials
    ttm_net_profit = _ttm(statements, "net_profit")
    ttm_revenue = _ttm(statements, "revenue")

    # Book equity (latest balance sheet equity)
    book_equity = latest_balance.values.get("equity") if latest_balance else None

    # Industry code from profile
    industry_code = profile.industry_code if profile and profile.industry_code else "150200"
    entity_type = profile.entity_type if profile else "operating_company"
    is_bank = entity_type == "financial_institution"

    print("  Key metrics:")
    print(f"      Price: {price:.2f} CNY")
    print(f"      Shares: {total_shares:,.0f}")
    print(f"      Market Cap: {market_cap:,.0f} CNY")
    print(f"      TTM Net Profit: {ttm_net_profit:,.0f} CNY" if ttm_net_profit else "      TTM Net Profit: N/A")
    print(f"      TTM Revenue: {ttm_revenue:,.0f} CNY" if ttm_revenue else "      TTM Revenue: N/A")
    print(f"      Book Equity: {book_equity:,.0f} CNY" if book_equity else "      Book Equity: N/A")

    # ------------------------------------------------------------------
    # 3. Build peer valuation from only versioned local snapshots.
    # ------------------------------------------------------------------
    peer_dir = peer_snapshot_dir or snapshot_path.parent
    target_candidate, _, candidate_peers, peer_names = _snapshot_peers(snapshot_path, snapshot_dir=peer_dir, cutoff=cutoff)
    peer_result = value_with_peers(target_candidate, candidate_peers)
    multiples = peer_result.multiples
    pv_rec = peer_result.validation
    peer_decisions = [
        {"symbol": item.symbol, "name": peer_names.get(item.symbol, item.symbol), "included": item.included, "reason": item.reason}
        for item in peer_result.decisions
    ]
    selected_peers = [item for item in candidate_peers if item.valuation.symbol in {d.symbol for d in peer_result.decisions if d.included}]

    peer_data = PeerValuationData(
        target_symbol=symbol_text,
        target_name=profile.name if profile else symbol_text,
        industry_code=target_candidate.industry_code,
        period_basis=target_candidate.valuation.period_basis,
        is_bank_or_insurer=target_candidate.is_bank_or_insurer,
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
    share_id = (
        f"fact_{symbol_text.replace('.', '_')}_total_shares_{latest_balance.fiscal_period}"
        if latest_balance else ""
    )
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
    print("  OK: Peer Valuation tab created")

    v_builder = ValidationTabBuilder(validation_data)
    v_builder.create_tab(wb)
    print("  OK: Validation tab created")

    # Save Excel
    excel_path = output_dir / f"{symbol_text}_cn_report.xlsx"
    wb.save(excel_path)
    file_size = excel_path.stat().st_size
    print(f"  OK: Excel report saved: {excel_path} ({file_size:,} bytes)")

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
    print(f"  OK: Metadata saved: {meta_path}")

    return metadata


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
    parser.add_argument("--peer-snapshot-dir", type=Path, default=PROJECT_ROOT / "data" / "snapshots" / "cn", help="Directory of compatible versioned peer snapshots.")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"  FinTrace-CN Full Report Generation")
    print(f"  Snapshot: {args.snapshot}")
    print(f"  Symbol:   {args.symbol}")
    print(f"{'='*70}\n")

    metadata = generate_report(args.snapshot, args.symbol, args.output, args.research_as_of, args.peer_snapshot_dir)

    print(f"\n{'='*70}")
    print(f"  Report generation complete!")
    print(f"  Validation: {'PASS' if metadata['validation']['valid'] else 'FAIL'}")
    if metadata["validation"]["errors"]:
        print(f"  Errors: {', '.join(metadata['validation']['errors'])}")
    print(f"  Markdown: {metadata['report_path']}")
    print(f"  Excel:    {metadata['excel_path']}")
    print(f"{'='*70}\n")

    return 0 if metadata["validation"]["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
