"""Fail-closed, deterministic checks for parsed A-share financial evidence.

The validator only reports anomalies. It never selects or mutates an OCR value.
Inputs intentionally accept the existing ``NormalizedFact``/``FinancialStatement``
objects and small mapping fixtures, making the offline contract easy to replay.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib
from typing import Any, Iterable, Mapping, Sequence

from ..domain import FinancialStatement
from ..periods import FinancialPeriodEngine, PeriodEngineError
from .models import ConstraintViolation, CrossModalInconsistency, IntegrityReport, TolerancePolicy

FAMILIES = ("accounting_identity", "table_structural", "period", "cross_period", "cross_source", "cross_modal")

def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping): return item.get(key, default)
    return getattr(item, key, default)

def _num(item: Any) -> float | None:
    value = _get(item, "value", _get(item, "raw_value"))
    try: return None if value is None else float(value)
    except (TypeError, ValueError): return None

def _ref(item: Any) -> dict[str, Any]:
    return {k: _get(item, k) for k in ("fact_id", "source_fragment_id", "document_id", "page", "locator", "source_url", "snapshot_id") if _get(item, k) is not None}

def _id(family: str, cid: str, inputs: Sequence[Any]) -> str:
    raw = family + "|" + cid + "|" + "|".join(str(_get(x, "fact_id", _get(x, "evidence_id", _get(x, "source_fragment_id", repr(x))))) for x in inputs)
    return "acme_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def _violation(family: str, cid: str, inputs: Sequence[Any], expected: float | None, actual: float | None,
               policy: TolerancePolicy, *, source_refs: Sequence[dict[str, Any]] = (), reason: str | None = None,
               status: str | None = None) -> ConstraintViolation:
    residual = None if expected is None or actual is None else float(actual) - float(expected)
    values = [v for v in (expected, actual) if v is not None]
    state = status or ("not_comparable" if residual is None else policy.classify(residual, *values))
    return ConstraintViolation(_id(family, cid, inputs), family, cid, [_ref(x) | ({"value": _num(x)} if _num(x) is not None else {}) for x in inputs], expected, actual, residual, policy.limit(*values), state, list(source_refs) or [_ref(x) for x in inputs], "error" if state == "violated" else "warning", reason=reason)

def _group_facts(facts: Iterable[Any], names: set[str]) -> dict[tuple[Any, ...], dict[str, Any]]:
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for fact in facts:
        metric = str(_get(fact, "metric", "")).lower()
        if metric not in names: continue
        key = (_get(fact, "symbol"), _get(fact, "fiscal_period", _get(fact, "period")), _get(fact, "scope"), _get(fact, "currency"), _get(fact, "unit"))
        groups.setdefault(key, {})[metric] = fact
    return groups

def check_accounting_identities(facts: Iterable[Any], *, tolerance_policy: TolerancePolicy | None = None) -> list[ConstraintViolation]:
    policy = tolerance_policy or TolerancePolicy(); out: list[ConstraintViolation] = []
    groups = _group_facts(facts, {"assets", "liabilities", "equity", "total_assets", "total_liabilities", "total_equity", "net_profit", "profit_before_tax", "income_tax", "opening_cash", "closing_cash", "net_change_in_cash"})
    for row in groups.values():
        for cid, left, right in (("balance_sheet_equation", "assets", ("liabilities", "equity")), ("balance_sheet_equation", "total_assets", ("total_liabilities", "total_equity")), ("profit_after_tax", "net_profit", ("profit_before_tax", "income_tax")), ("cash_roll_forward", "closing_cash", ("opening_cash", "net_change_in_cash"))):
            if left not in row or any(key not in row for key in right): continue
            if cid == "profit_after_tax":
                expected = (_num(row["profit_before_tax"]) or 0.0) - (_num(row["income_tax"]) or 0.0)
            else:
                expected = sum(_num(row[key]) or 0.0 for key in right)
            actual = _num(row[left])
            if actual is not None: out.append(_violation("accounting_identity", cid, [row[left], *[row[key] for key in right]], expected, actual, policy))
    return out

def check_table_structural(tables: Iterable[Any], *, tolerance_policy: TolerancePolicy | None = None) -> list[ConstraintViolation]:
    policy = tolerance_policy or TolerancePolicy(); out = []
    for table in tables:
        rows = _get(table, "rows", table if isinstance(table, list) else None)
        if not rows: continue
        for row in rows:
            children = _get(row, "children", _get(row, "items"))
            total = _get(row, "subtotal", _get(row, "total"))
            if children is None or total is None: continue
            child_values = [float(_num(x) if _num(x) is not None else x) for x in children]
            expected = sum(child_values); actual = float(_num(total) if _num(total) is not None else total)
            out.append(_violation("table_structural", "subtotal_reconciliation", [*children, total], expected, actual, policy))
    return out

def _statements_from_facts(facts: Iterable[Any], statement_type: str) -> list[FinancialStatement]:
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for fact in facts:
        if _get(fact, "statement_type") != statement_type: continue
        key = (_get(fact, "fiscal_period"), _get(fact, "scope"), _get(fact, "currency", "CNY"), _get(fact, "unit", "CNY"))
        rows.setdefault(key, {})[str(_get(fact, "metric"))] = _num(fact)
    return [FinancialStatement(statement_type=statement_type, fiscal_period=key[0], period_basis=_get(next(iter([f for f in facts if _get(f, 'fiscal_period') == key[0]]), {}), 'period_basis', key[0][-2:]), published_at=None, available_at=None, currency=key[2], unit=key[3], values=values, scope=key[1]) for key, values in rows.items()]

def check_period_relations(facts: Iterable[Any], *, tolerance_policy: TolerancePolicy | None = None) -> list[ConstraintViolation]:
    policy = tolerance_policy or TolerancePolicy(); facts = list(facts); out = []
    for statement_type in ("income", "cashflow"):
        rows = _statements_from_facts(facts, statement_type)
        if not rows: continue
        try: derived = FinancialPeriodEngine.derive_single_quarters(rows, statement_type)  # single source of period logic
        except (PeriodEngineError, ValueError): continue
        lookup = {(d.fiscal_period, metric): value for d in derived for metric, value in d.values.items() if value is not None}
        actuals = {(str(_get(f, "fiscal_period")), str(_get(f, "metric"))): f for f in facts if _get(f, "statement_type") == statement_type}
        for (period, metric), expected in lookup.items():
            fact = actuals.get((period, metric))
            if fact is not None: out.append(_violation("period", "ytd_single_quarter_relation", [fact], expected, _num(fact), policy))
    return out

def check_cross_period_continuity(facts: Iterable[Any], *, restatement_signals: Iterable[Any] = (), tolerance_policy: TolerancePolicy | None = None) -> list[ConstraintViolation]:
    policy = tolerance_policy or TolerancePolicy(); rows = sorted(list(facts), key=lambda x: str(_get(x, "fiscal_period", ""))); out = []
    signals = list(restatement_signals)
    for previous, current in zip(rows, rows[1:]):
        if _get(previous, "metric") != _get(current, "metric") or _get(previous, "scope") != _get(current, "scope"): continue
        if str(_get(previous, "fiscal_period", ""))[-2:] != "FY" or str(_get(current, "fiscal_period", ""))[-2:] not in {"Q1", "H1", "9M", "FY"}: continue
        status = "warning" if any(_get(s, "signal_type", "") in {"restated", "prior_period_error_correction", "consolidation_scope_change"} for s in signals) else None
        out.append(_violation("cross_period", "opening_closing_continuity", [previous, current], _num(previous), _num(current), policy, status=status, reason="restatement_context" if status else None))
    return out

def check_cross_source(facts: Iterable[Any], *, tolerance_policy: TolerancePolicy | None = None) -> list[ConstraintViolation]:
    policy = tolerance_policy or TolerancePolicy(); groups: dict[tuple[Any, ...], list[Any]] = {}; out = []
    for fact in facts: groups.setdefault((_get(fact, "symbol"), _get(fact, "metric"), _get(fact, "fiscal_period"), _get(fact, "period_basis"), _get(fact, "currency"), _get(fact, "unit"), _get(fact, "scope")), []).append(fact)
    for group in groups.values():
        providers = {str(_get(f, "provider")) for f in group}; values = [_num(f) for f in group]
        if len(group) < 2: continue
        if len({_get(f, "currency") for f in group} | {_get(f, "unit") for f in group}) > 1:
            out.append(_violation("cross_source", "NOT_COMPARABLE", group, None, None, policy, status="not_comparable", reason="period/scope/currency/unit not aligned")); continue
        residual = max(values) - min(values) if all(v is not None for v in values) else None
        classification = "MATCH" if residual == 0 else ("ROUNDING_MATCH" if residual is not None and residual <= policy.limit(*values) else "CONFLICT")
        out.append(_violation("cross_source", classification, group, min(values) if values else None, max(values) if values else None, policy, status="passed" if classification in {"MATCH", "ROUNDING_MATCH"} else "violated", reason="detection_only; CARD-13 decides conflict"))
    return out

def check_cross_modal(annotations: Iterable[Any], *, tolerance_policy: TolerancePolicy | None = None) -> list[CrossModalInconsistency]:
    policy = tolerance_policy or TolerancePolicy(); out = []
    for item in annotations:
        metric = str(_get(item, "metric", "")); values = dict(_get(item, "values", {})); computed = _get(item, "computed_value")
        nums = [float(v) for v in values.values() if v is not None]
        if computed is not None: nums.append(float(computed))
        if len(nums) < 2 or max(nums) - min(nums) == 0: continue
        conflict_type = "unit_mismatch" if _get(item, "unit_mismatch", False) else ("period_mismatch" if _get(item, "period_mismatch", False) else "value_mismatch")
        ref = _get(item, "source_refs", [])
        digest = hashlib.sha256((metric + repr(sorted(values.items()))).encode()).hexdigest()[:16]
        out.append(CrossModalInconsistency("acme_modal_" + digest, metric, values, None if computed is None else float(computed), conflict_type, "unresolved", list(ref)))
    return out

def validate_multimodal_evidence(facts: Iterable[Any], statements: Iterable[Any] = (), snapshots: Iterable[Any] | None = None, chart_annotations: Iterable[Any] | None = None, *, document_id: str = "unknown", tolerance_policy: TolerancePolicy | None = None, restatement_signals: Iterable[Any] = ()) -> IntegrityReport:
    policy = tolerance_policy or TolerancePolicy(); facts = list(facts); statements = list(statements)
    violations = [*check_accounting_identities(facts, tolerance_policy=policy), *check_table_structural(statements, tolerance_policy=policy), *check_period_relations(facts, tolerance_policy=policy), *check_cross_period_continuity(facts, restatement_signals=restatement_signals, tolerance_policy=policy), *check_cross_source([*facts, *list(snapshots or ())], tolerance_policy=policy)]
    modal = check_cross_modal(chart_annotations or (), tolerance_policy=policy)
    totals = {key: sum(1 for item in violations if item.status == key) for key in ("checked", "passed", "warning", "violated", "not_comparable")}; totals["checked"] = len(violations) + len(modal)
    review = [v.violation_id for v in violations if v.status in {"warning", "violated", "not_comparable"}] + [m.inconsistency_id for m in modal]
    return IntegrityReport(document_id, list(FAMILIES), totals, violations, modal, review)
