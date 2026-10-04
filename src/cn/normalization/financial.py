"""Deterministic normalization of A-share financial statement values.

This layer converts units and validates dimensions before the existing period
engine derives single quarters or TTM. It never creates missing financial
values and it preserves source statement metadata on every normalized fact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable, Optional

from ..domain import FinancialStatement
from ..periods import FinancialPeriodEngine, PeriodEngineError, supports_period_engine


NORMALIZATION_SCHEMA_VERSION = "cn-normalized-fact-1.1.0"
_PERIOD_RE = re.compile(r"^(?P<year>\d{4})(?P<kind>Q1|H1|9M|FY)$")


class NormalizationError(ValueError):
    """A statement cannot safely enter deterministic financial calculations."""


_UNIT_SCALE = {
    "CNY": ("money", 1.0),
    "RMB": ("money", 1.0),
    "元": ("money", 1.0),
    "人民币": ("money", 1.0),
    "万元": ("money", 10_000.0),
    "百万元": ("money", 1_000_000.0),
    "百万元人民币": ("money", 1_000_000.0),
    "亿元": ("money", 100_000_000.0),
    "亿元人民币": ("money", 100_000_000.0),
    "股": ("shares", 1.0),
    "share": ("shares", 1.0),
    "shares": ("shares", 1.0),
    "%": ("ratio_percent", 1.0),
    "percent": ("ratio_percent", 1.0),
}


@dataclass(frozen=True)
class NormalizedFact:
    fact_id: str
    symbol: str
    metric: str
    value: float
    currency: str
    unit: str
    fiscal_period: str
    period_basis: str
    statement_type: str
    flow_stock: str
    scope: Optional[str]
    source_periods: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    provider: str
    published_at: Optional[str]
    available_at: Optional[str]
    validation_status: str
    version: str = "AS_REPORTED"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = NORMALIZATION_SCHEMA_VERSION
        payload["source_periods"] = list(self.source_periods)
        payload["source_evidence_ids"] = list(self.source_evidence_ids)
        payload["warnings"] = list(self.warnings)
        return payload


def _canonical_period(fiscal_period: str) -> tuple[str, str]:
    match = _PERIOD_RE.fullmatch(str(fiscal_period or ""))
    if not match:
        raise NormalizationError(f"Unsupported fiscal period '{fiscal_period}'.")
    return fiscal_period, match.group("kind")


def _canonical_basis(statement: FinancialStatement, period_kind: str) -> str:
    raw = str(statement.period_basis or "").strip()
    if raw.endswith("_CUMULATIVE"):
        raw = period_kind
    if statement.statement_type == "balance":
        if raw not in {"FY", "Q1", "H1", "9M", "END", "POINT_IN_TIME"}:
            raise NormalizationError(f"Balance-sheet period basis is unsupported: '{statement.period_basis}'.")
        return "POINT_IN_TIME"
    if raw not in {"FY", "Q1", "H1", "9M", "TTM", "SINGLE_QUARTER"}:
        raise NormalizationError(f"Flow statement period basis is unsupported: '{statement.period_basis}'.")
    return raw


def _unit_dimension(unit: str) -> tuple[str, float]:
    key = str(unit or "").strip()
    if key not in _UNIT_SCALE:
        raise NormalizationError(f"Unsupported financial unit '{unit}'.")
    return _UNIT_SCALE[key]


def normalize_unit_value(value: float, unit: str, *, target_unit: str = "CNY") -> float:
    """Convert a known unit without guessing currency or dimensional meaning."""
    source_dimension, source_scale = _unit_dimension(unit)
    target_dimension, target_scale = _unit_dimension(target_unit)
    if source_dimension != target_dimension:
        raise NormalizationError(
            f"Cannot convert incompatible units '{unit}' and '{target_unit}'."
        )
    return float(value) * source_scale / target_scale


def _status_and_warnings(scope: Optional[str], version: str) -> tuple[str, tuple[str, ...]]:
    if scope is None:
        return "ambiguous", ("scope_unknown",)
    if scope not in {"consolidated", "parent"}:
        raise NormalizationError(f"Unsupported accounting scope '{scope}'.")
    if version not in {"AS_REPORTED", "CORRECTED", "RESTATED"}:
        raise NormalizationError(f"Unsupported financial fact version '{version}'.")
    return "normalized", ()


def normalize_statements(
    statements: Iterable[FinancialStatement],
    *,
    symbol: str,
    provider: str,
    scope: Optional[str] = None,
    target_unit: str = "CNY",
    source_evidence_prefix: Optional[str] = None,
) -> list[NormalizedFact]:
    """Normalize statements while preserving period and provenance metadata."""
    rows = list(statements)
    if not rows:
        raise NormalizationError("No financial statements were supplied.")
    target_dimension, _ = _unit_dimension(target_unit)
    if target_dimension != "money":
        raise NormalizationError("Statement normalization target_unit must be a money unit.")
    currencies = {str(row.currency or "").upper() for row in rows}
    if not currencies or "" in currencies:
        raise NormalizationError("Every statement must declare a currency.")
    if len(currencies) != 1:
        raise NormalizationError("Mixed statement currencies require an explicit FX evidence layer.")
    currency = next(iter(currencies))
    if currency not in {"CNY", "RMB"}:
        raise NormalizationError(f"Unsupported statement currency '{currency}'.")

    facts: list[NormalizedFact] = []
    for row in rows:
        fiscal_period, period_kind = _canonical_period(row.fiscal_period)
        if not supports_period_engine(fiscal_period):
            raise NormalizationError(f"Period engine does not support '{fiscal_period}'.")
        basis = _canonical_basis(row, period_kind)
        if row.statement_type not in {"income", "cashflow", "balance"}:
            raise NormalizationError(f"Unsupported statement type '{row.statement_type}'.")
        flow_stock = "stock" if row.statement_type == "balance" else "flow"
        if flow_stock == "stock" and basis != "POINT_IN_TIME":
            raise NormalizationError("Stock statements must use POINT_IN_TIME semantics.")
        fact_scope = scope if scope is not None else row.scope
        version = "RESTATED" if row.is_restated and row.version == "AS_REPORTED" else row.version
        status, warnings = _status_and_warnings(fact_scope, version)
        for metric, raw_value in sorted(row.values.items()):
            if raw_value is None:
                continue
            normalized_value = normalize_unit_value(float(raw_value), row.unit, target_unit=target_unit)
            evidence_id = f"{source_evidence_prefix or provider}_{symbol.replace('.', '_')}_{metric}_{fiscal_period}"
            facts.append(NormalizedFact(
                fact_id=f"norm_{evidence_id}", symbol=symbol, metric=metric,
                value=normalized_value, currency="CNY", unit=target_unit,
                fiscal_period=fiscal_period, period_basis=basis,
                statement_type=row.statement_type, flow_stock=flow_stock,
                scope=fact_scope, version=version, source_periods=(fiscal_period,),
                source_evidence_ids=(evidence_id,), provider=provider,
                published_at=row.published_at, available_at=row.available_at,
                validation_status=status, warnings=warnings,
            ))
    return facts


def derive_normalized_periods(
    statements: Iterable[FinancialStatement],
    *,
    symbol: str,
    provider: str,
    statement_type: str,
    scope: Optional[str] = None,
) -> list[NormalizedFact]:
    """Derive single-quarter and TTM facts through the existing period engine."""
    rows = [row for row in statements if row.statement_type == statement_type]
    if statement_type == "balance":
        raise NormalizationError("Balance-sheet stock values cannot be differenced or converted to TTM.")
    if not rows:
        return []
    base_facts = normalize_statements(rows, symbol=symbol, provider=provider, scope=scope)
    by_period: dict[str, list[NormalizedFact]] = {}
    for fact in base_facts:
        by_period.setdefault(fact.fiscal_period, []).append(fact)
    normalized_rows: list[FinancialStatement] = []
    for period, period_facts in sorted(by_period.items()):
        normalized_rows.append(FinancialStatement(
            statement_type=statement_type, fiscal_period=period,
            period_basis=period_facts[0].period_basis, published_at=period_facts[0].published_at,
            available_at=period_facts[0].available_at, currency="CNY", unit="CNY",
            values={fact.metric: fact.value for fact in period_facts},
            scope=period_facts[0].scope, version=period_facts[0].version,
        ))
    try:
        derived = [
            *FinancialPeriodEngine.derive_single_quarters(normalized_rows, statement_type),
            *FinancialPeriodEngine.derive_ttm(normalized_rows, statement_type),
        ]
    except PeriodEngineError as exc:
        raise NormalizationError(str(exc)) from exc
    output: list[NormalizedFact] = []
    for item in derived:
        input_ids = tuple(
            fact.source_evidence_ids[0]
            for source_period in item.source_periods
            for fact in by_period.get(source_period, [])
        )
        for metric, value in sorted(item.values.items()):
            if value is None:
                continue
            output.append(NormalizedFact(
                fact_id=f"norm_derived_{symbol.replace('.', '_')}_{metric}_{item.fiscal_period}_{item.period_basis}",
                symbol=symbol, metric=metric, value=float(value), currency="CNY", unit="CNY",
                fiscal_period=item.fiscal_period, period_basis=item.period_basis,
                statement_type=item.statement_type, flow_stock="flow", scope=scope or None, version=next(iter({fact.version for source_period in item.source_periods for fact in by_period.get(source_period, [])}), "AS_REPORTED"),
                source_periods=item.source_periods, source_evidence_ids=input_ids,
                provider="fintrace_period_engine", published_at=None, available_at=None,
                validation_status="ambiguous" if scope is None else "normalized",
                warnings=("scope_unknown",) if scope is None else (),
            ))
    return output
