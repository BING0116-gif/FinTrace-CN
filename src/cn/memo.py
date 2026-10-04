"""Deterministic, traceable buy-side investment memo assembly."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Mapping

MEMO_SECTION_IDS = ("executive_summary", "company_overview", "financial_performance", "investment_thesis", "valuation", "catalysts", "risks", "counter_thesis", "falsification", "tracking_kpis", "evidence_appendix")
_TITLES = {"executive_summary":"执行摘要", "company_overview":"公司概览", "financial_performance":"财务表现", "investment_thesis":"投资逻辑", "valuation":"估值", "catalysts":"催化剂", "risks":"风险", "counter_thesis":"反向论证", "falsification":"证伪条件", "tracking_kpis":"跟踪指标", "evidence_appendix":"证据附录"}
_NUMERIC = re.compile(r"(?<![A-Za-z])[+-]?(?:\d+(?:\.\d+)?%?|\d+\.\d+)")

class MemoValidationError(ValueError):
    pass

@dataclass
class MemoSection:
    section_id: str
    tier_marking: list[dict[str, Any]] = field(default_factory=list)
    body_markdown: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "supported"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class InvestmentMemo:
    memo_id: str
    run_id: str
    symbol: str
    sections: list[MemoSection]
    validation: dict[str, Any]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    disclaimer: str = "本材料仅用于研究讨论，不构成投资建议；数据适用边界以证据与验证状态为准。"

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": "cn-investment-memo-1.0.0", "memo_id": self.memo_id, "run_id": self.run_id, "symbol": self.symbol, "generated_at": self.generated_at, "disclaimer": self.disclaimer, "sections": [s.to_dict() for s in self.sections], "validation": self.validation}

def _obj(value: Any) -> dict[str, Any]:
    if value is None: return {}
    if hasattr(value, "to_dict"): return value.to_dict()
    return dict(value) if isinstance(value, Mapping) else {}

def _graph_claims(graph: Any) -> dict[str, Any]:
    return getattr(graph, "claims", {}) if graph is not None else {}

def _claim(graph: Any, *, claim_type: str | None = None, calculation_id: str | None = None) -> Any:
    for c in _graph_claims(graph).values():
        if claim_type and getattr(c, "claim_type", None) != claim_type: continue
        if calculation_id and calculation_id not in getattr(c, "calculation_ids", []): continue
        return c
    return None

def _mark(sentence: str, claim: Any = None, *, calculation_ids: list[str] | None = None, evidence_ids: list[str] | None = None, claim_type: str | None = None) -> dict[str, Any]:
    return {"sentence_span": sentence, "claim_id": getattr(claim, "claim_id", None), "claim_type": claim_type or getattr(claim, "claim_type", "opinion"), "calculation_ids": calculation_ids or [], "evidence_ids": evidence_ids or list(getattr(claim, "evidence_ids", []) if claim else [])}

def _analysis_rows(analysis: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = _obj(analysis)
    return data.get("metrics", []) or [], data.get("signals", []) or []

def _section(section_id: str, sentences: list[dict[str, Any]], *, evidence_ids: list[str] = None, status: str = "supported") -> MemoSection:
    return MemoSection(section_id, sentences, "\n".join(x["sentence_span"] for x in sentences), evidence_ids or [], status)

def build_memo(analysis: Any = None, valuation: Any = None, findings: Any = None, hits: Any = None, graph: Any = None, *, symbol: str = "", run_id: str = "") -> InvestmentMemo:
    metrics, signals = _analysis_rows(analysis)
    claims = _graph_claims(graph)
    sections: list[MemoSection] = []
    sections.append(_section("executive_summary", [_mark("本备忘录汇总已验证的事实、推论与待验证事项，结论强度受证据覆盖度约束。", _claim(graph, claim_type="inference"))]))
    if hits:
        text = getattr(hits[0], "chunk", hits[0]); text = getattr(text, "text", None) or (_obj(hits[0]).get("text", ""))
        sections.append(_section("company_overview", [_mark(text or "公司概览证据文本为空，无法形成可验证描述。", _claim(graph, claim_type="fact"))]))
    else: sections.append(_section("company_overview", [_mark("data_unavailable：未提供公司概览证据。")], status="data_unavailable"))
    if metrics and graph:
        marks = []
        for row in metrics:
            sentence = f"{row.get('metric', '指标')}（{row.get('period_key', '期间')}）为 {row.get('value')} {row.get('unit', '')}。"
            c = _claim(graph, calculation_id=row.get("calculation_id"))
            marks.append(_mark(sentence, c, calculation_ids=[row.get("calculation_id")] if row.get("calculation_id") else [], evidence_ids=list(getattr(c, "evidence_ids", []) if c else []), claim_type="fact"))
        sections.append(_section("financial_performance", marks))
    else: sections.append(_section("financial_performance", [_mark("data_unavailable：未提供经验证的财务指标。")], status="data_unavailable"))
    if signals and graph:
        sections.append(_section("investment_thesis", [_mark(str(x.get("detail", "")), _claim(graph, claim_type="inference"), calculation_ids=list(x.get("metric_calculation_ids", [])), claim_type="inference") for x in signals]))
    else: sections.append(_section("investment_thesis", [_mark("data_unavailable：未发现可引用的投资逻辑信号。")], status="data_unavailable"))
    v = _obj(valuation)
    if v and graph:
        rows = v.get("scenarios") or v.get("scenario_values") or []
        if isinstance(rows, Mapping): rows = [{"name": k, **(_obj(val))} for k, val in rows.items()]
        marks = [_mark(f"估值情景 {r.get('name', r.get('scenario', 'unknown'))}：{r.get('implied_price', r.get('value', '待计算'))}。", _claim(graph, calculation_id=r.get("calculation_id")), calculation_ids=[r.get("calculation_id")] if r.get("calculation_id") else [], claim_type="fact") for r in rows]
        sections.append(_section("valuation", marks or [_mark("估值结果未包含可渲染情景。")], status="supported" if marks else "data_unavailable"))
    else: sections.append(_section("valuation", [_mark("data_unavailable：未提供估值结果。")], status="data_unavailable"))
    sections.append(_section("catalysts", [_mark("催化剂需以新增、可核验的证据确认；当前未自动推断未提供的事件。")]))
    risk_marks = [_mark(str(x.get("detail", "")), _claim(graph, claim_type="inference"), calculation_ids=list(x.get("metric_calculation_ids", [])), claim_type="inference") for x in signals if "risk" in str(x.get("signal_id", "")) or "warning" in str(x.get("signal_id", ""))]
    sections.append(_section("risks", risk_marks or [_mark("当前未提供已验证的风险信号。")]))
    sections.append(_section("counter_thesis", [_mark("未发现显著反向证据；这不等同于反向风险不存在，需继续检索。", _claim(graph, claim_type="opinion"))]))
    sections.append(_section("falsification", [_mark("若下一期净利润同比低于 0%，则应重新评估当前投资逻辑。", _claim(graph, claim_type="opinion"))]))
    kpi_marks = [_mark(f"跟踪 {m.get('metric', '指标')}（{m.get('period_key', '期间')}）及其后续变化。", _claim(graph, calculation_id=m.get("calculation_id")), calculation_ids=[m.get("calculation_id")] if m.get("calculation_id") else [], claim_type="fact") for m in metrics]
    sections.append(_section("tracking_kpis", kpi_marks or [_mark("data_unavailable：未提供可计算的跟踪指标。")], status="supported" if kpi_marks else "data_unavailable"))
    evidence_ids = sorted({eid for c in claims.values() for eid in getattr(c, "evidence_ids", [])})
    sections.append(_section("evidence_appendix", [_mark("证据清单：" + (", ".join(evidence_ids) if evidence_ids else "data_unavailable") )], evidence_ids=evidence_ids, status="supported" if evidence_ids else "data_unavailable"))
    blocked = [c.claim_id for c in claims.values() if getattr(c, "validation_status", "") in {"blocked", "stale", "conflicted"}]
    if blocked:
        sections[0].body_markdown += f"\n数据链路被阻断（blocked/stale）：{', '.join(blocked)}；相关结论不得视为已验证。"
        sections[0].tier_marking.append(_mark(f"数据链路被阻断（blocked/stale）：{', '.join(blocked)}；相关结论不得视为已验证。"))
        # Fail closed: blocked/conflicted Claims cannot remain in conclusion
        # paragraphs. Stale claims are retained only as an explicit refresh
        # marker, never as a supported conclusion.
        for section in sections:
            if section.section_id == "evidence_appendix":
                continue
            impacted = [mark.get("claim_id") for mark in section.tier_marking if mark.get("claim_id") in blocked]
            if not impacted:
                continue
            hard_block = [cid for cid in impacted if getattr(claims.get(cid), "validation_status", "") in {"blocked", "conflicted"}]
            section.status = "blocked" if hard_block else "stale"
            label = "BLOCKED" if hard_block else "STALE"
            section.tier_marking = [{"sentence_span": f"{label}：上游 Claim {', '.join(impacted)} 已失效，需完成时间重验证后刷新本段。", "claim_id": None, "claim_type": "opinion", "calculation_ids": [], "evidence_ids": []}]
            section.body_markdown = section.tier_marking[0]["sentence_span"]
    memo = InvestmentMemo(f"memo-{run_id or 'draft'}", run_id, symbol, sections, {})
    memo.validation = validate_memo(memo, graph)
    return memo

def validate_memo(memo: InvestmentMemo, graph: Any = None) -> dict[str, Any]:
    errors: list[str] = []; warnings: list[str] = []
    present = {s.section_id for s in memo.sections}
    errors.extend(f"missing_section:{x}" for x in MEMO_SECTION_IDS if x not in present)
    claims = _graph_claims(graph)
    for section in memo.sections:
        for mark in section.tier_marking:
            sentence = str(mark.get("sentence_span", "")).strip()
            if not sentence: errors.append(f"empty_sentence:{section.section_id}"); continue
            cid = mark.get("claim_id"); typ = mark.get("claim_type")
            if cid and cid not in claims: errors.append(f"unknown_claim:{cid}")
            if typ == "fact" and not cid: errors.append(f"fact_without_claim:{section.section_id}")
            if typ == "fact" and cid and not getattr(claims.get(cid), "evidence_ids", []): errors.append(f"fact_without_evidence:{cid}")
            if _NUMERIC.search(sentence) and not (mark.get("calculation_ids") or mark.get("evidence_ids")) and section.section_id not in {"falsification"}: errors.append(f"numeric_without_trace:{section.section_id}")
    falsification = next((s for s in memo.sections if s.section_id == "falsification"), None)
    if not falsification or not re.search(r"%|<|>|低于|高于|达到|超过", falsification.body_markdown): errors.append("falsification_threshold_missing")
    if "不构成投资建议" not in memo.disclaimer: errors.append("disclaimer_missing")
    blocked = [c.claim_id for c in claims.values() if getattr(c, "validation_status", "") in {"blocked", "stale", "conflicted"}]
    if blocked: warnings.append("blocked_upstream:" + ",".join(blocked))
    for section in memo.sections:
        for mark in section.tier_marking:
            cid = mark.get("claim_id")
            if cid and cid in claims and getattr(claims[cid], "validation_status", "") in {"blocked", "conflicted"} and section.section_id != "evidence_appendix":
                errors.append(f"blocked_claim_in_conclusion:{cid}:{section.section_id}")
    return {"valid": not errors, "errors": errors, "warnings": warnings}

def render_memo_markdown(memo: InvestmentMemo) -> str:
    lines = [f"# {memo.symbol or 'A股'} 投资备忘录", "", f"> {memo.disclaimer}", ""]
    for section in memo.sections:
        lines += [f"## {_TITLES.get(section.section_id, section.section_id)}", f"状态：{section.status}", section.body_markdown]
        lines += ["", "<!-- tier_marking: " + json.dumps(section.tier_marking, ensure_ascii=False) + " -->", ""]
    return "\n".join(lines)

def render_memo_json(memo: InvestmentMemo) -> dict[str, Any]: return memo.to_dict()

def _build_memo_prompt(section_name: str, analysis_dict: Mapping[str, Any], valuation_dict: Mapping[str, Any], existing_claim_ids: set[str]) -> str:
    return f"生成 {section_name} 段落。只能引用 claim_id 白名单 {sorted(existing_claim_ids)}；不得编造事实、数字或证据。结构化输入：analysis={json.dumps(dict(analysis_dict), ensure_ascii=False, default=str)} valuation={json.dumps(dict(valuation_dict), ensure_ascii=False, default=str)}。逐句返回 sentence_span、claim_id、claim_type；数值句必须带 calculation_ids。"

def _validate_memo_segment_output(llm_json: Any, existing_claim_ids: set[str]) -> None:
    rows = llm_json.get("sentences", llm_json) if isinstance(llm_json, Mapping) else llm_json
    if not isinstance(rows, list): raise MemoValidationError("sentences must be a list")
    for row in rows:
        if not isinstance(row, Mapping) or not str(row.get("sentence_span", "")).strip(): raise MemoValidationError("sentence_span must be non-empty")
        cid = row.get("claim_id"); typ = row.get("claim_type")
        if cid is not None and cid not in existing_claim_ids: raise MemoValidationError("claim_id is not in whitelist")
        if typ not in {"fact", "inference", "opinion"}: raise MemoValidationError("invalid claim_type")
        if typ == "fact" and not cid: raise MemoValidationError("fact sentence requires claim_id")
        if typ == "inference" and not row.get("derived_from"): raise MemoValidationError("inference sentence requires derived_from")
        if _NUMERIC.search(str(row["sentence_span"])) and not (row.get("calculation_id") or row.get("calculation_ids")): raise MemoValidationError("numeric sentence requires calculation_id")

