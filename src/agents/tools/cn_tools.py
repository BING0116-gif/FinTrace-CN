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
from src.cn.valuation import AssumptionRegistry, PeerValuationInput, build_valuation_result
from src.cn.symbols import CanonicalSymbol, normalize_cn_symbol
from src.cn.normalization import NormalizationError, derive_normalized_periods, normalize_statements
from src.cn.analysis import analyze_financials
from src.cn.analysis import comparability_decision, detect_scope_signals, detection_coverage
from src.cn.documents import DocumentService
from src.cn.checker import check_raw_report, check_report, extract_claims, summarize
from src.cn.retrieval import Bm25Index, CorpusChunk
from src.cn.graph import ClaimGraph, deactivate_evidence, revalidate
from src.cn.memo import build_memo, render_memo_markdown
from src.cn.evidence_pack import export_evidence_pack, replay_timeline
from src.cn.acme import validate_multimodal_evidence
from src.cn.proof import verify_claim
from src.cn.fragility import build_fragility_report
from src.cn.temporal import TemporalEvent, ingest_temporal_event

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
                "scope": statement.scope, "version": ("RESTATED" if statement.is_restated and statement.version == "AS_REPORTED" else statement.version),
            } for statement in statements],
            evidence_ids=[fact.evidence_id for fact in facts],
            validation=ledger.validate(research_as_of=cutoff).valid,
        )


class NormalizeCnFinancialsTool(_SnapshotTool):
    name = "normalize_cn_financials"
    description = "Normalize A-share financial statements from the configured snapshot, preserving units, periods, scope warnings, and source evidence; derive single quarters and TTM only through the deterministic period engine."
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Canonical A-share symbol, e.g. 600519.SH."},
            "research_as_of": {"type": "string", "description": "Optional ISO-8601 research cutoff."},
            "scope": {"type": "string", "enum": ["consolidated", "parent"], "description": "Accounting scope when explicitly established by the source."},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, research_as_of: str = "", scope: str = "") -> str:
        try:
            symbol = self._symbol(ticker)
            cutoff = research_as_of or self.snapshot._payload["research_as_of"]
            statements = self.snapshot.get_financial_statements(symbol, research_as_of=cutoff)
            normalized = normalize_statements(
                statements, symbol=str(symbol), provider="snapshot", scope=scope or None,
                source_evidence_prefix="fact",
            )
            derived = []
            for statement_type in ("income", "cashflow"):
                derived.extend(derive_normalized_periods(
                    statements, symbol=str(symbol), provider="snapshot",
                    statement_type=statement_type, scope=scope or None,
                ))
        except (NormalizationError, ValueError) as exc:
            return tool_error(str(exc), ticker=ticker)
        return tool_ok(
            ticker=str(symbol), provider="snapshot", research_as_of=cutoff,
            normalized_facts=[fact.to_dict() for fact in normalized],
            derived_facts=[fact.to_dict() for fact in derived],
            evidence_ids=[evidence_id for fact in normalized for evidence_id in fact.source_evidence_ids],
            validation={
                "status": "warning" if any(fact.validation_status == "ambiguous" for fact in normalized) else "pass",
                "scope": scope or None,
                "warnings": sorted({warning for fact in normalized for warning in fact.warnings}),
            },
        )


class AnalyzeCnFinancialsTool(_SnapshotTool):
    name = "analyze_cn_financials"
    description = "Run deterministic A-share financial diagnostics over normalized snapshot facts. Reports earnings-state semantics and conservative cash/receivable/inventory signals; it does not infer causality."
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Canonical A-share symbol, e.g. 600519.SH."},
            "research_as_of": {"type": "string", "description": "Optional ISO-8601 research cutoff."},
            "scope": {"type": "string", "enum": ["consolidated", "parent"], "description": "Accounting scope established by the source."},
        },
        "required": ["ticker"],
    }

    async def execute(self, ticker: str, research_as_of: str = "", scope: str = "") -> str:
        try:
            symbol = self._symbol(ticker)
            cutoff = research_as_of or self.snapshot._payload["research_as_of"]
            statements = self.snapshot.get_financial_statements(symbol, research_as_of=cutoff)
            facts = normalize_statements(statements, symbol=str(symbol), provider="snapshot", scope=scope or None, source_evidence_prefix="fact")
            result = analyze_financials(facts)
        except (NormalizationError, ValueError) as exc:
            return tool_error(str(exc), ticker=ticker)
        return tool_ok(
            ticker=str(symbol), provider="snapshot", research_as_of=cutoff,
            analysis=result.to_dict(), evidence_ids=[evidence_id for fact in facts for evidence_id in fact.source_evidence_ids],
        )


class DetectCnScopeSignalsTool(Tool):
    """Inspect a registered document for accounting-scope/restatement signals."""
    name = "detect_cn_scope_signals"
    description = "Detect deterministic A-share accounting scope changes, corrections, and restatements from a registered document; unknown suspicious disclosures block YoY."
    parameters = {
        "type": "object",
        "properties": {"document_id": {"type": "string", "description": "Registered document ID."}},
        "required": ["document_id"],
    }

    def __init__(self, documents: DocumentService):
        self.documents = documents

    async def execute(self, document_id: str) -> str:
        try:
            result = self.documents.get_result(document_id)
            signals = detect_scope_signals(result.facts, (result,))
        except Exception as exc:
            return tool_error(str(exc), document_id=document_id)
        return tool_ok(
            document_id=document_id,
            signals=[signal.to_dict() for signal in signals],
            comparability=[comparability_decision(signal) for signal in signals],
            detection_coverage=detection_coverage(),
        )


class ValidateCnAcmeTool(Tool):
    """Run fail-closed ACME checks over one registered parsed document."""
    name = "validate_cn_acme"
    description = "Validate parsed A-share evidence with deterministic accounting, period, cross-source, and multimodal constraints; never silently correct values."
    parameters = {
        "type": "object",
        "properties": {"document_id": {"type": "string", "description": "Registered document ID."}},
        "required": ["document_id"],
    }

    def __init__(self, documents: DocumentService):
        self.documents = documents

    async def execute(self, document_id: str) -> str:
        try:
            result = self.documents.get_result(document_id)
            report = validate_multimodal_evidence(result.facts, document_id=document_id)
        except Exception as exc:
            return tool_error(str(exc), document_id=document_id)
        return tool_ok(
            document_id=document_id,
            integrity_report=report.to_dict(),
            violations=[item.to_dict() for item in report.violations],
            review_queue=report.review_queue,
        )


class VerifyCnClaimTool(Tool):
    """Verify a claim passport from the in-process ClaimGraph, without an LLM."""
    name = "verify_cn_claim"
    description = "Rebuild and verify an A-share Financial Claim Passport deterministically; returns VERIFIED, DEGRADED, STALE, BLOCKED, or CONFLICTED."
    parameters = {
        "type": "object",
        "properties": {
            "claim_id": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["claim_id"],
    }

    async def execute(self, claim_id: str, run_id: str = "") -> str:
        try:
            result = verify_claim(claim_id, run_id or None)
        except (KeyError, ValueError) as exc:
            return tool_error(str(exc), claim_id=claim_id, run_id=run_id)
        return tool_ok(claim_id=claim_id, run_id=run_id or None, verification_result=result.to_dict())


class AnalyzeCnThesisFragilityTool(Tool):
    """Compute deterministic critical dependencies and cut sets for a thesis."""
    name = "analyze_cn_thesis_fragility"
    description = "Analyze an A-share thesis ClaimGraph with deterministic REQUIRED dependency, minimal cut-set, and monitoring-plan rules."
    parameters = {"type": "object", "properties": {"thesis_id": {"type": "string"}, "run_id": {"type": "string"}, "thresholds": {"type": "array"}}, "required": ["thesis_id", "run_id"]}

    def __init__(self, graph=None):
        self.graph = graph

    async def execute(self, thesis_id: str, run_id: str = "", thresholds=None) -> str:
        try:
            graph = self.graph
            if graph is None:
                from src.cn.graph.graph import _RUN_GRAPHS
                graph = _RUN_GRAPHS.get(run_id)
            if graph is None:
                raise KeyError(f"Unknown run_id: {run_id}")
            report = build_fragility_report(graph, thesis_id, thresholds=thresholds or [])
        except (KeyError, TypeError, ValueError) as exc:
            return tool_error(str(exc), thesis_id=thesis_id, run_id=run_id)
        return tool_ok(thesis_id=thesis_id, run_id=run_id or getattr(graph, "run_id", ""), fragility_report=report.to_dict())


class RevalidateCnClaimsTool(Tool):
    """Apply a typed temporal event to a registered ClaimGraph incrementally."""
    name = "revalidate_cn_claims"
    description = "Propagate DATA_CONFLICT, VERSION_SUPERSESSION, or NEW_INFORMATION through the affected A-share claim subgraph without rerunning unrelated workflow steps."
    parameters = {"type": "object", "properties": {"run_id": {"type": "string"}, "event": {"type": "object"}}, "required": ["run_id", "event"]}

    async def execute(self, run_id: str, event: dict) -> str:
        try:
            parsed = TemporalEvent(**event)
            report = ingest_temporal_event(parsed, run_id=run_id)
        except (KeyError, TypeError, ValueError) as exc:
            return tool_error(str(exc), run_id=run_id)
        return tool_ok(run_id=run_id, revalidation_report=report.to_dict(), impact=report.impact)


class CheckCnReportDraftTool(Tool):
    """Extract and deterministically check claims from a registered report draft."""
    name = "check_cn_report_draft"
    description = "Check an A-share report draft against document facts. Claim extraction is an injected transport step; numeric, period, scope, citation, revision, and causal checks are deterministic."
    parameters = {
        "type": "object",
        "properties": {"document_id": {"type": "string", "description": "Registered report-draft document ID."}},
        "required": ["document_id"],
    }

    def __init__(self, documents: DocumentService, llm_client: object):
        self.documents = documents
        self.llm_client = llm_client

    async def execute(self, document_id: str) -> str:
        try:
            result = self.documents.get_result(document_id)
            paragraphs = [{"text": fragment.text, "page": fragment.page_number} for fragment in result.fragments]
            facts = [fact.to_dict() for fact in result.facts]
            checked = check_raw_report(paragraphs, self.llm_client, facts)
            claims, findings, summary = checked["claims"], checked["findings"], checked["summary"]
        except Exception as exc:
            return tool_error(str(exc), document_id=document_id)
        return tool_ok(
            document_id=document_id,
            claims=[claim.to_dict() for claim in claims],
            findings=[finding.to_dict() for finding in findings],
            summary=summary,
        )


class SearchCnCorpusTool(Tool):
    """Search pre-indexed report chunks without creating evidence records."""
    name = "search_cn_corpus"
    description = "Deterministically search indexed A-share report chunks with BM25. Results locate source text and never receive evidence IDs until explicitly cited."
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 0}},
        "required": ["query"],
    }

    def __init__(self, index: Bm25Index):
        self.index = index

    async def execute(self, query: str, top_k: int = 5) -> str:
        try:
            hits = self.index.search(query, top_k=top_k)
        except (TypeError, ValueError) as exc:
            return tool_error(str(exc), query=query)
        return tool_ok(query=query, hits=[{
            "chunk_id": hit.chunk.chunk_id, "document_id": hit.chunk.document_id,
            "page": hit.chunk.page, "section": hit.chunk.section, "text": hit.chunk.text,
            "score": hit.score, "mode": hit.mode, "rank": hit.rank,
        } for hit in hits])


class RunCnRelativeValuationTool(Tool):
    name = "run_cn_relative_valuation"
    description = "Run deterministic A-share PE/PB/PS relative valuation with Bear/Base/Bull scenarios, assumptions, and sensitivity matrices. Inputs must be TTM EPS/BPS/revenue-per-share and explicit target multiples."
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "base_inputs": {"type": "object", "description": "Explicit TTM inputs, scenarios, and optional sensitivity ranges."},
        },
        "required": ["symbol", "base_inputs"],
    }

    async def execute(self, symbol: str, base_inputs: Dict[str, object]) -> str:
        try:
            result = build_valuation_result(base_inputs, AssumptionRegistry())
        except (TypeError, ValueError, KeyError) as exc:
            return tool_error(str(exc), symbol=symbol)
        return tool_ok(symbol=symbol, valuation=result.to_dict())


class GenerateCnInvestmentMemoTool(Tool):
    name = "generate_cn_investment_memo"
    description = "Assemble an offline A-share investment memo with 11 sections, sentence-level fact/inference/opinion markings, and Claim-Evidence trace metadata. Missing upstream data is labeled data_unavailable."
    parameters = {
        "type": "object",
        "properties": {"symbol": {"type": "string"}, "document_id": {"type": "string"}},
        "required": [],
    }

    def __init__(self, *, analysis=None, valuation=None, findings=None, hits=None, graph=None):
        self.analysis, self.valuation, self.findings, self.hits, self.graph = analysis, valuation, findings, hits, graph

    async def execute(self, symbol: str = "", document_id: str = "") -> str:
        memo = build_memo(self.analysis, self.valuation, self.findings, self.hits, self.graph, symbol=symbol or document_id, run_id=getattr(self.graph, "run_id", ""))
        return tool_ok(symbol=symbol or document_id, memo=memo.to_dict(), memo_markdown=render_memo_markdown(memo))


class ExportCnEvidencePackTool(Tool):
    name = "export_cn_evidence_pack"
    description = "Export an A-share run's evidence pack ZIP and return its loss-tolerant audit replay timeline. Missing artifacts remain explicitly marked."
    parameters = {"type": "object", "properties": {"run_id": {"type": "string"}, "runs_root": {"type": "string"}, "output_dir": {"type": "string"}}, "required": ["run_id"]}

    async def execute(self, run_id: str, runs_root: str = "runs", output_dir: str = "") -> str:
        try:
            archive = export_evidence_pack(run_id, runs_root=runs_root, output_dir=output_dir or None)
            timeline = replay_timeline(Path(runs_root) / run_id)
        except (OSError, ValueError) as exc:
            return tool_error(str(exc), run_id=run_id)
        return tool_ok(run_id=run_id, archive=str(archive), timeline=timeline)


class TraceCnClaimTool(Tool):
    name = "trace_cn_claim"
    description = "Trace an A-share claim through calculations to document or snapshot evidence locations."
    parameters = {"type": "object", "properties": {"claim_id": {"type": "string"}}, "required": ["claim_id"]}

    def __init__(self, graph: ClaimGraph):
        self.graph = graph

    async def execute(self, claim_id: str) -> str:
        try:
            return tool_ok(claim_id=claim_id, trace_tree=self.graph.trace(claim_id).to_dict())
        except KeyError as exc:
            return tool_error(str(exc), claim_id=claim_id)


class DeactivateCnEvidenceTool(Tool):
    name = "deactivate_cn_evidence"
    description = "Mark evidence inactive for an audit run and propagate blocked/stale state without deleting the record."
    parameters = {"type": "object", "properties": {"run_id": {"type": "string"}, "evidence_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["run_id", "evidence_id", "reason"]}

    async def execute(self, run_id: str, evidence_id: str, reason: str) -> str:
        try:
            impacted = deactivate_evidence(run_id, evidence_id, reason)
        except (KeyError, ValueError) as exc:
            return tool_error(str(exc), run_id=run_id, evidence_id=evidence_id)
        return tool_ok(run_id=run_id, evidence_id=evidence_id, impacted_claims=impacted.split(",") if impacted else [], revalidation={"changed_evidence_ids": [evidence_id], "impacted_claim_ids": impacted.split(",") if impacted else []})


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
        return [ResolveCnSymbolTool(), RunCnRelativeValuationTool(), GenerateCnInvestmentMemoTool(), ExportCnEvidencePackTool()]
    snapshot = SnapshotProvider(path)
    return [
        ResolveCnSymbolTool(snapshot), GetCnPricesTool(snapshot), GetCnFinancialsTool(snapshot), NormalizeCnFinancialsTool(snapshot), AnalyzeCnFinancialsTool(snapshot),
        CreateCnResearchPlanTool(), GenerateCnResearchReportTool(snapshot), ValueWithPeersTool(), RunCnRelativeValuationTool(), GenerateCnInvestmentMemoTool(), ExportCnEvidencePackTool(),
    ]
