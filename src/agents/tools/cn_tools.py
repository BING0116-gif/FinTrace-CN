"""Offline-first A-share tools backed by a versioned FinTrace-CN snapshot."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.cn.evidence import EvidenceLedger
from src.cn.providers.snapshot import SnapshotProvider
from src.cn.peer_workflow import PeerCandidate, result_to_dict, value_with_peers
from src.cn.report import CnResearchReportBuilder
from src.cn.research import ResearchState
from src.cn.valuation import PeerValuationInput
from src.cn.symbols import CanonicalSymbol, normalize_cn_symbol

from .base import Tool, tool_error, tool_ok


DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[3] / "data" / "snapshots" / "cn" / "600519.SH_20260810_tushare_v1.json"
_ALIASES = {"贵州茅台": "600519.SH", "茅台": "600519.SH", "KWEICHOW MOUTAI": "600519.SH"}


def _snapshot_path(path: Optional[Path | str] = None) -> Path:
    configured = os.getenv("FINTRACE_CN_SNAPSHOT", "").strip()
    return Path(path or configured or DEFAULT_SNAPSHOT)


class ResolveCnSymbolTool(Tool):
    name = "resolve_cn_symbol"
    description = "Resolve a Chinese A-share company name or code to its canonical symbol, e.g. 贵州茅台 → 600519.SH."
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Chinese company name or A-share code."}},
        "required": ["query"],
    }

    def __init__(self, snapshot: Optional[SnapshotProvider] = None):
        self.snapshot = snapshot

    async def execute(self, query: str) -> str:
        text = (query or "").strip()
        resolved = _ALIASES.get(text) or _ALIASES.get(text.upper())
        try:
            symbol = normalize_cn_symbol(resolved or text)
        except Exception as exc:
            return tool_error(str(exc), query=text)
        profile = None
        if self.snapshot:
            try:
                profile = self.snapshot.get_profile(symbol)
            except Exception:
                pass
        return tool_ok(
            query=text,
            symbol=str(symbol),
            asset_class="A_SHARE",
            company_name=profile.name if profile else None,
            snapshot_available=bool(profile),
        )


class _SnapshotTool(Tool):
    def __init__(self, snapshot: SnapshotProvider):
        self.snapshot = snapshot

    def _symbol(self, value: str) -> CanonicalSymbol:
        return normalize_cn_symbol(value)


class GetCnPricesTool(_SnapshotTool):
    name = "get_cn_prices"
    description = "Read saved A-share RAW price bars from the verified offline snapshot. This is historical snapshot data, not a live quote."
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Canonical A-share symbol, e.g. 600519.SH."},
            "start_date": {"type": "string", "description": "Optional YYYY-MM-DD start date."},
            "end_date": {"type": "string", "description": "Optional YYYY-MM-DD end date."},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, start_date: str = "", end_date: str = "") -> str:
        try:
            symbol = self._symbol(ticker)
            bars = self.snapshot.get_daily_bars(symbol, start_date=start_date or None, end_date=end_date or None)
        except Exception as exc:
            return tool_error(str(exc), ticker=ticker)
        if not bars:
            return tool_error("No RAW bars in the configured snapshot for this range.", ticker=str(symbol))
        latest = max(bars, key=lambda item: item.trade_date)
        evidence_id = f"fact_{str(symbol).replace('.', '_')}_close_{latest.trade_date}_RAW"
        return tool_ok(
            ticker=str(symbol), snapshot_id=self.snapshot._payload["snapshot_id"], adjustment="RAW",
            latest={"trade_date": latest.trade_date, "close": latest.close, "volume": latest.volume, "amount": latest.amount},
            bars=[{"trade_date": item.trade_date, "open": item.open, "high": item.high, "low": item.low, "close": item.close} for item in bars],
            evidence_ids=[evidence_id],
            note="Offline snapshot data; do not describe it as a live quote.",
        )


class GetCnFinancialsTool(_SnapshotTool):
    name = "get_cn_financials"
    description = "Read A-share financial statements from the verified offline snapshot and return evidence IDs for each key value."
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Canonical A-share symbol, e.g. 600519.SH."},
            "research_as_of": {"type": "string", "description": "Optional ISO-8601 China-time research cutoff."},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, research_as_of: str = "") -> str:
        try:
            symbol = self._symbol(ticker)
            cutoff = research_as_of or self.snapshot._payload["research_as_of"]
            statements = self.snapshot.get_financial_statements(symbol, research_as_of=cutoff)
        except Exception as exc:
            return tool_error(str(exc), ticker=ticker)
        ledger = EvidenceLedger(snapshot_id=self.snapshot._payload["snapshot_id"])
        facts = []
        for statement in statements:
            facts.extend(ledger.add_statement_facts(symbol=str(symbol), statement=statement, provider="snapshot"))
        return tool_ok(
            ticker=str(symbol), snapshot_id=self.snapshot._payload["snapshot_id"], research_as_of=cutoff,
            statements=[{
                "type": statement.statement_type, "fiscal_period": statement.fiscal_period,
                "period_basis": statement.period_basis, "published_at": statement.published_at,
                "available_at": statement.available_at, "values": statement.values,
            } for statement in statements],
            evidence_ids=[fact.evidence_id for fact in facts],
            validation=ledger.validate(research_as_of=cutoff).valid,
        )


class GenerateCnResearchReportTool(_SnapshotTool):
    name = "generate_cn_research_report"
    description = "Generate a Chinese Markdown A-share research report from the verified offline snapshot. Includes RAW price, TTM metrics, valuation, Evidence IDs, and Validator status; it never fetches live data or calls Tushare."
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Canonical A-share symbol, e.g. 600519.SH."},
            "research_as_of": {"type": "string", "description": "Optional ISO-8601 China-time research cutoff."},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, research_as_of: str = "") -> str:
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            symbol = self._symbol(ticker)
            cutoff = research_as_of or self.snapshot._payload["research_as_of"]
            state = ResearchState.create(query=f"生成 {symbol} A股研究报告", symbol=str(symbol), research_as_of=cutoff)
            report = CnResearchReportBuilder(self.snapshot).build(symbol, research_as_of=cutoff)
        except Exception as exc:
            return tool_error(str(exc), ticker=ticker)
        evidence_ids = [line.split("`")[1] for line in report.markdown.splitlines() if line.startswith("| `")]
        state.register_evidence(evidence_ids)
        validation = {"valid": report.validation.valid, "errors": report.validation.errors, "missing_evidence": []}
        state.finalize_validation(validation)
        state.report = report.markdown
        state.record_tool(tool_name=self.name, arguments={"ticker": str(symbol), "research_as_of": cutoff}, started_at=started_at,
                          result_status="ok", provider="snapshot", evidence_ids=evidence_ids)
        return tool_ok(
            ticker=str(symbol), snapshot_id=self.snapshot._payload["snapshot_id"],
            research_as_of=cutoff, validation=validation, research_state=state.to_dict(),
            report_markdown=report.markdown,
            note="Offline snapshot report; do not describe prices as live data.",
        )


class CreateCnResearchPlanTool(Tool):
    name = "create_cn_research_plan"
    description = "Create a structured, traceable offline A-share research plan with required evidence and bounded recovery state. Use after resolving an A-share symbol."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Original user research request."},
            "ticker": {"type": "string", "description": "Canonical A-share symbol, e.g. 600519.SH."},
            "research_as_of": {"type": "string", "description": "Research cutoff in ISO-8601 China time."},
        },
        "required": ["query", "ticker", "research_as_of"],
    }

    async def execute(self, query: str, ticker: str, research_as_of: str) -> str:
        try:
            symbol = normalize_cn_symbol(ticker)
            state = ResearchState.create(query=query, symbol=str(symbol), research_as_of=research_as_of)
        except Exception as exc:
            return tool_error(str(exc), ticker=ticker)
        return tool_ok(research_state=state.to_dict())


class ValueWithPeersTool(Tool):
    name = "value_with_peers"
    description = "Calculate deterministic A-share PE/PB/PS peer valuation ranges from supplied, evidence-backed offline inputs. Returns peer selection reasons, outlier exclusions, implied prices, and validation; no market-data provider is called."
    parameters = {
        "type": "object",
        "properties": {
            "target": {"type": "object", "description": "Exactly one target OBJECT (never an array): symbol, raw_price, total_shares, net_profit, book_equity, revenue, period_basis, industry_code, evidence_ids object, and optional is_bank_or_insurer."},
            "peers": {"type": "array", "items": {"type": "object"}, "description": "Array of peer objects in the same shape as target; evidence_ids must be an object mapping field names to IDs."},
        },
        "required": ["target", "peers"],
    }

    @staticmethod
    def _candidate(raw: Dict[str, object]) -> PeerCandidate:
        if not isinstance(raw, dict):
            raise ValueError("Peer valuation target and every peer must be JSON objects, not arrays or scalars.")
        required = ("symbol", "raw_price", "total_shares", "period_basis", "industry_code")
        missing = [key for key in required if raw.get(key) is None]
        if missing:
            raise ValueError(f"Missing peer valuation fields: {', '.join(missing)}")
        valuation = PeerValuationInput(
            symbol=str(raw["symbol"]), raw_price=float(raw["raw_price"]), total_shares=float(raw["total_shares"]),
            net_profit=float(raw["net_profit"]) if raw.get("net_profit") is not None else None,
            book_equity=float(raw["book_equity"]) if raw.get("book_equity") is not None else None,
            revenue=float(raw["revenue"]) if raw.get("revenue") is not None else None,
            period_basis=str(raw["period_basis"]),
        )
        ids = raw.get("evidence_ids") or {}
        if not isinstance(ids, dict):
            raise ValueError("evidence_ids must be an object mapping fields to evidence IDs.")
        return PeerCandidate(valuation, str(raw["industry_code"]), {str(k): str(v) for k, v in ids.items()}, bool(raw.get("is_bank_or_insurer", False)))

    async def execute(self, target: Dict[str, object], peers: List[Dict[str, object]]) -> str:
        try:
            result = value_with_peers(self._candidate(target), [self._candidate(item) for item in peers])
        except (AttributeError, TypeError, ValueError) as exc:
            return tool_error(str(exc))
        return tool_ok(**result_to_dict(result))


def build_cn_snapshot_tools(snapshot_path: Optional[Path | str] = None) -> List[Tool]:
    """Always offer code resolution; only offer data tools when a local snapshot exists."""
    path = _snapshot_path(snapshot_path)
    if not path.exists():
        return [ResolveCnSymbolTool()]
    snapshot = SnapshotProvider(path)
    return [
        ResolveCnSymbolTool(snapshot), GetCnPricesTool(snapshot), GetCnFinancialsTool(snapshot),
        CreateCnResearchPlanTool(), GenerateCnResearchReportTool(snapshot), ValueWithPeersTool(),
    ]
