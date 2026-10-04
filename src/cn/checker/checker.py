"""Fail-closed, provider-neutral report claim checker (no LLM imports)."""

from __future__ import annotations

import math
import re
from datetime import datetime
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from ..analysis.financial import compute_yoy
from ..analysis.scope_signals import AccountingScopeSignal, ScopeSignalType, comparability_decision
from .models import DraftClaim, Finding


UNIT_SCALE = {"元": 1.0, "CNY": 1.0, "万元": 10_000.0, "亿元": 100_000_000.0, "百万元": 1_000_000.0}
METRIC_ALIASES = {"net_profit": "net_profit", "net_profit_parent": "net_profit_parent", "归母净利润": "net_profit_parent", "营业收入": "revenue", "营收": "revenue", "收入": "revenue", "扣非净利润": "net_profit_deducted", "少数股东损益": "minority_interest_profit", "母公司净资产": "net_assets_parent", "合并净资产": "net_assets_consolidated"}
CAUSAL_WORDS = ("因为", "由于", "导致", "驱动", "得益于", "归因于")


def _get(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, Mapping) else getattr(item, key, default)


def _metric(claim: DraftClaim) -> str | None:
    return METRIC_ALIASES.get(str(claim.metric or "").strip(), str(claim.metric or "").strip() or None)


def _period(value: Any) -> str | None:
    raw = str(value or "")
    if re.fullmatch(r"\d{4}(FY|Q[1-4]|H1|9M|TTM|SINGLE_QUARTER)", raw):
        return raw
    match = re.search(r"(20\d{2}).{0,3}(年|FY|年度)", raw)
    return f"{match.group(1)}FY" if match else None


def _close(left: float, right: float, digits: int | None = None) -> bool:
    tolerance = max(1e-9, abs(right) * 0.0005)
    if digits is not None:
        tolerance = max(tolerance, 0.5 * 10 ** (-digits))
    return math.isclose(left, right, rel_tol=0.0005, abs_tol=tolerance)


def _finding(claim: DraftClaim, check_type: str, severity: str, original: Any, expected: Any, evidence: Iterable[str], suggestion: str, confidence: float) -> Finding:
    return Finding(claim.claim_id, check_type, severity, str(original), str(expected), tuple(evidence), suggestion, confidence)


def _facts_for(facts: list[Any], metric: str | None, period: str | None) -> list[Any]:
    return [fact for fact in facts if _get(fact, "metric") == metric and (period is None or _get(fact, "fiscal_period", _get(fact, "period")) == period)]


def _signal_decision(signal: Any) -> str:
    if isinstance(signal, Mapping):
        kind = signal.get("signal_type")
        decision = signal.get("comparability_decision")
        if decision:
            return str(decision)
        return "block_yoy" if str(kind) in {"unknown", "restated", "prior_period_error_correction"} else "warning"
    return comparability_decision(signal)


def check_report(
    claims: Iterable[DraftClaim], normalized_facts: Iterable[Any],
    scope_signals: Iterable[AccountingScopeSignal] = (), *, research_as_of: str | None = None,
) -> list[Finding]:
    facts = list(normalized_facts)
    signals = list(scope_signals)
    findings: list[Finding] = []
    evidence_index: dict[str, Any] = {}
    for fact in facts:
        primary = str(_get(fact, "fact_id", _get(fact, "evidence_id", "")))
        if primary:
            evidence_index[primary] = fact
        for source_id in (_get(fact, "source_evidence_ids", ()) or ()):
            evidence_index[str(source_id)] = fact
    for claim in claims:
        metric, period = _metric(claim), _period(claim.period)
        if claim.temporal_status == "forward_looking" or claim.claim_type == "forward_looking":
            continue
        matching = _facts_for(facts, metric, period)
        all_metric = _facts_for(facts, metric, None)
        refs = tuple(claim.evidence_ids) or ((claim.source_reference,) if claim.source_reference else ())
        if not refs:
            findings.append(_finding(claim, "missing_citation", "warning", claim.sentence, "Evidence ID or source page", (), "补充可解析的 Evidence ID 或原始文档页码。", 1.0))
        unsupported = [ref for ref in refs if ref and ref not in evidence_index and not str(ref).lower().startswith(("page:", "p."))]
        if unsupported:
            findings.append(_finding(claim, "unsupported_citation", "error", ",".join(unsupported), "可解析的 Evidence ID", (), "更换为事实库中存在的 Evidence ID。", 1.0))
        if refs and not matching and all_metric:
            findings.append(_finding(claim, "period_error", "error", claim.period, ", ".join(str(_get(item, "fiscal_period")) for item in all_metric), tuple(str(_get(item, "fact_id", "")) for item in all_metric), "改用事实对应期间，或标记为无法核验。", 1.0))
        if not matching:
            if claim.claim_type == "causal" or any(word in claim.sentence for word in CAUSAL_WORDS):
                if len(refs) < 2:
                    findings.append(_finding(claim, "unsupported_causal_claim", "warning", claim.sentence, "因果两侧各有独立证据", (), "将因果表述改为相关性，或补充原因与结果两侧的独立证据。", 1.0))
            if refs and all_metric:
                referenced = [evidence_index[ref] for ref in refs if ref in evidence_index]
                if referenced and not any(_get(item, "metric") == metric and _get(item, "fiscal_period", _get(item, "period")) == period for item in referenced):
                    findings.append(_finding(claim, "wrong_citation", "error", ",".join(refs), f"{metric} 对应 Evidence", tuple(str(_get(item, "fact_id", "")) for item in referenced), "改为引用与指标和期间对应的 Evidence。", 1.0))
            if claim.valuation_multiple and metric in {"pe", "pb", "ps"}:
                findings.append(_finding(claim, "valuation_multiple_error", "warning", claim.valuation_multiple, "无可比事实，视为分析师假设", (), "明确标注目标倍数为假设，不要表述为已披露事实。", 1.0))
            continue
        fact = matching[0]
        fact_id = str(_get(fact, "fact_id", _get(fact, "evidence_id", "")))
        evidence = (fact_id,) if fact_id else ()
        cited_facts = [evidence_index[ref] for ref in refs if ref in evidence_index]
        if cited_facts and not any(str(_get(item, "fact_id", _get(item, "evidence_id", ""))) == fact_id for item in cited_facts):
            findings.append(_finding(claim, "wrong_citation", "error", ",".join(refs), fact_id, evidence, "改为引用与该指标和期间对应的 Evidence。", 1.0))
        fact_scope = _get(fact, "scope")
        if claim.scope and fact_scope and claim.scope != fact_scope:
            findings.append(_finding(claim, "scope_error", "error", claim.scope, fact_scope, evidence, "改为与来源一致的合并/母公司口径，并重新计算相关指标。", 1.0))
        if claim.page is not None:
            fact_page = _get(fact, "page", _get(fact, "page_number"))
            if fact_page is not None and int(claim.page) != int(fact_page):
                findings.append(_finding(claim, "wrong_page", "error", claim.page, fact_page, evidence, "改为事实来源所在页码。", 1.0))
        available_at = _get(fact, "available_at")
        if research_as_of and available_at:
            try:
                age_days = (datetime.fromisoformat(research_as_of) - datetime.fromisoformat(str(available_at))).days
            except ValueError:
                age_days = 0
            if age_days > 365:
                findings.append(_finding(claim, "stale_citation", "error", available_at, f"不早于 {research_as_of} 前 365 天", evidence, "改用研究截止日前仍在有效期内的事实版本。", 1.0))
        if any(_signal_decision(signal) == "block_yoy" for signal in signals) and claim.growth is not None:
            findings.append(_finding(claim, "scope_error", "error", claim.growth, "同比已阻断", evidence, "删除同比结论，或使用更正/重述后的可比期间数据。", 1.0))
        if claim.value is not None and isinstance(claim.value, (int, float)):
            declared_unit = claim.unit or "CNY"
            scale = UNIT_SCALE.get(declared_unit)
            expected_value = float(_get(fact, "value"))
            converted = float(claim.value) * scale if scale is not None else None
            if converted is None:
                findings.append(_finding(claim, "unit_error", "error", declared_unit, _get(fact, "unit", "CNY"), evidence, "改用事实单位并明确换算关系。", 1.0))
            elif not _close(converted, expected_value, 1 if declared_unit in {"亿元", "万元"} else None):
                raw_equal = _close(float(claim.value), expected_value)
                check_type = "unit_error" if raw_equal and declared_unit != _get(fact, "unit") else "numeric_error"
                findings.append(_finding(claim, check_type, "error", f"{claim.value} {declared_unit}", f"{expected_value} {_get(fact, 'unit', 'CNY')}", evidence, "按证据中的数值、单位和期间修正原句。", 0.9 if check_type == "unit_error" else 1.0))
        if claim.growth is not None:
            previous_period = f"{int(period[:4]) - 1}{period[4:]}" if period and period[:4].isdigit() else None
            previous = next((item for item in facts if _get(item, "metric") == metric and _get(item, "fiscal_period") == previous_period), None)
            if previous is not None:
                expected_growth = compute_yoy(float(_get(fact, "value")), float(_get(previous, "value")), metric=metric or "metric", period_key=period or "unknown").delta_pct
                if expected_growth is not None and not _close(float(claim.growth) / 100.0, expected_growth):
                    findings.append(_finding(claim, "calculation_error", "error", f"{claim.growth}%", f"{expected_growth * 100:.2f}%", (fact_id, str(_get(previous, "fact_id", ""))), "按同口径前期事实重新计算同比。", 1.0))
        if claim.valuation_multiple and metric in {"pe", "pb", "ps"}:
            match = re.search(r"[-+]?\d+(?:\.\d+)?", claim.valuation_multiple)
            expected_multiple = float(_get(fact, "value"))
            if match and not _close(float(match.group(0)), expected_multiple):
                findings.append(_finding(claim, "valuation_multiple_error", "error", claim.valuation_multiple, f"{expected_multiple:.2f}x", evidence, "改为事实中的可比倍数，或明确标注为分析师目标假设。", 1.0))
        if claim.claim_type in {"causal", "inference"} or any(word in claim.sentence for word in CAUSAL_WORDS):
            if len(refs) < 2:
                findings.append(_finding(claim, "unsupported_causal_claim", "warning", claim.sentence, "因果两侧各有独立证据", evidence, "将因果表述改为相关性，或补充原因与结果两侧的独立证据。", 1.0))
        version = _get(fact, "version", "AS_REPORTED")
        if version == "AS_REPORTED" and any(_get(item, "metric") == metric and _get(item, "fiscal_period") == period and _get(item, "version") in {"CORRECTED", "RESTATED"} for item in facts):
            findings.append(_finding(claim, "revision_superseded", "error", fact_id, "使用 CORRECTED/RESTATED 事实", evidence, "改为引用最新更正/重述版本。", 1.0))
    return findings


def summarize(findings: Iterable[Finding]) -> dict[str, Any]:
    rows = list(findings)
    counts = Counter(item.check_type for item in rows)
    return {"total": len(rows), "errors": sum(item.severity == "error" for item in rows), "warnings": sum(item.severity == "warning" for item in rows), "by_check_type": dict(sorted(counts.items())), "schema_version": "cn-report-checker-1.0.0"}


def check_raw_report(
    draft_paragraphs: Iterable[dict[str, Any]], llm_client: Any,
    normalized_facts: Iterable[Any], scope_signals: Iterable[AccountingScopeSignal] = (),
    *, research_as_of: str | None = None,
) -> dict[str, Any]:
    """Run the raw-paragraph boundary end to end.

    Claim extraction remains the sole injected transport boundary; every finding
    is produced by :func:`check_report`. Invalid extractor rows are reported as
    ``unextracted`` rather than silently treated as a clean report.
    """
    from .claim_extractor import extract_claims
    paragraphs = [dict(item) if isinstance(item, Mapping) else {"text": str(item)} for item in draft_paragraphs]
    claims = extract_claims(paragraphs, llm_client)
    extracted_sentences = {claim.sentence for claim in claims}
    unextracted = sum(1 for paragraph in paragraphs if str(paragraph.get("text", "")).strip() and str(paragraph.get("text", "")) not in extracted_sentences)
    findings = check_report(claims, normalized_facts, scope_signals, research_as_of=research_as_of)
    summary = summarize(findings)
    summary["extracted_claims"] = len(claims)
    summary["unextracted_sentences"] = unextracted
    return {"claims": claims, "findings": findings, "summary": summary}
