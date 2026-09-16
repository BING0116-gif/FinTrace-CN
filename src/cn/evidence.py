"""Evidence ledger for traceable A-share facts and deterministic calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Literal, Optional, Tuple

from .domain import FinancialStatement, MarketBar


EvidenceKind = Literal["fact", "calculation"]
Operation = Literal["add", "subtract", "multiply", "divide"]


class EvidenceError(ValueError):
    """An evidence entry is incomplete, duplicated, or internally inconsistent."""


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: EvidenceKind
    symbol: str
    metric: str
    value: float
    currency: str
    unit: str
    fiscal_period: Optional[str]
    period_basis: Optional[str]
    published_at: Optional[str]
    available_at: Optional[str]
    provider: str
    field_path: Optional[str]
    source_url: Optional[str] = None
    input_ids: Tuple[str, ...] = ()
    operation: Optional[Operation] = None


@dataclass(frozen=True)
class LedgerValidation:
    valid: bool
    errors: List[str] = field(default_factory=list)


class EvidenceLedger:
    """Stores every reportable financial fact and the calculation paths between them."""

    def __init__(self, *, snapshot_id: str):
        self.snapshot_id = snapshot_id
        self._records: Dict[str, EvidenceRecord] = {}

    def add_fact(
        self,
        *,
        evidence_id: str,
        symbol: str,
        metric: str,
        value: float,
        currency: str,
        unit: str,
        fiscal_period: Optional[str],
        period_basis: Optional[str],
        published_at: Optional[str],
        available_at: Optional[str],
        provider: str,
        field_path: str,
        source_url: Optional[str] = None,
    ) -> EvidenceRecord:
        return self._add(
            EvidenceRecord(
                evidence_id=evidence_id, kind="fact", symbol=symbol, metric=metric,
                value=float(value), currency=currency, unit=unit, fiscal_period=fiscal_period,
                period_basis=period_basis, published_at=published_at, available_at=available_at,
                provider=provider, field_path=field_path, source_url=source_url,
            )
        )

    def add_calculation(
        self,
        *,
        evidence_id: str,
        symbol: str,
        metric: str,
        value: float,
        currency: str,
        unit: str,
        operation: Operation,
        input_ids: Iterable[str],
        fiscal_period: Optional[str] = None,
        period_basis: Optional[str] = None,
    ) -> EvidenceRecord:
        inputs = tuple(input_ids)
        if len(inputs) < 2:
            raise EvidenceError("A calculation requires at least two evidence inputs.")
        for input_id in inputs:
            if input_id not in self._records:
                raise EvidenceError(f"Calculation input does not exist: {input_id}")
        return self._add(
            EvidenceRecord(
                evidence_id=evidence_id, kind="calculation", symbol=symbol, metric=metric,
                value=float(value), currency=currency, unit=unit, fiscal_period=fiscal_period,
                period_basis=period_basis, published_at=None, available_at=None,
                provider="fintrace_calculator", field_path=None, input_ids=inputs, operation=operation,
            )
        )

    def _add(self, record: EvidenceRecord) -> EvidenceRecord:
        if record.evidence_id in self._records:
            raise EvidenceError(f"Duplicate evidence ID: {record.evidence_id}")
        self._records[record.evidence_id] = record
        return record

    def get(self, evidence_id: str) -> EvidenceRecord:
        return self._records[evidence_id]

    def records(self) -> List[EvidenceRecord]:
        return list(self._records.values())

    def add_statement_facts(self, *, symbol: str, statement: FinancialStatement, provider: str) -> List[EvidenceRecord]:
        # Skip statements whose fiscal_period is not a supported engine tag.
        # Such rows have unparseable ``YYYYUNKNOWN`` placeholders that would
        # produce colliding evidence IDs and break deduplication.
        if not __import__("src.cn.periods", fromlist=["supports_period_engine"]).supports_period_engine(
            getattr(statement, "fiscal_period", None)
        ):
            return []
        created = []
        for metric, value in statement.values.items():
            if value is None:
                continue
            evidence_id = f"fact_{symbol.replace('.', '_')}_{metric}_{statement.fiscal_period}"
            created.append(self.add_fact(
                evidence_id=evidence_id, symbol=symbol, metric=metric, value=value,
                currency=statement.currency, unit=statement.unit, fiscal_period=statement.fiscal_period,
                period_basis=statement.period_basis, published_at=statement.published_at,
                available_at=statement.available_at, provider=provider,
                field_path=f"statements.{statement.statement_type}.{statement.fiscal_period}.{metric}",
                source_url=statement.source_url,
            ))
        return created

    def add_market_bar_facts(self, *, symbol: str, bar: MarketBar, provider: str) -> List[EvidenceRecord]:
        if bar.adjustment != "RAW":
            raise EvidenceError("Only RAW prices may enter valuation evidence.")
        return [self.add_fact(
            evidence_id=f"fact_{symbol.replace('.', '_')}_close_{bar.trade_date}_RAW",
            symbol=symbol, metric="close", value=bar.close, currency="CNY", unit="CNY/share",
            fiscal_period=None, period_basis="RAW", published_at=bar.trade_date + "T15:00:00+08:00",
            available_at=bar.trade_date + "T15:00:00+08:00", provider=provider,
            field_path=f"bars.{bar.trade_date}.close",
        )]

    def validate(self, *, research_as_of: str, tolerance: float = 1e-9) -> LedgerValidation:
        errors: List[str] = []
        for record in self._records.values():
            if record.kind == "fact" and record.available_at and record.available_at > research_as_of:
                errors.append(f"future_fact:{record.evidence_id}")
            if record.kind == "calculation":
                try:
                    expected = self._recalculate(record)
                except EvidenceError as exc:
                    errors.append(f"invalid_calculation:{record.evidence_id}:{exc}")
                    continue
                # Financial values can be on the order of trillions.  Use a
                # relative tolerance so harmless IEEE-754 rounding does not
                # turn an otherwise identical multiplication into a false
                # validation failure.
                if abs(expected - record.value) > tolerance * max(1.0, abs(expected)):
                    errors.append(f"calculation_mismatch:{record.evidence_id}")
        return LedgerValidation(valid=not errors, errors=errors)

    def _recalculate(self, record: EvidenceRecord) -> float:
        values = [self._records[input_id].value for input_id in record.input_ids]
        if record.operation == "add":
            return sum(values)
        if record.operation == "subtract":
            return values[0] - sum(values[1:])
        if record.operation == "multiply":
            result = 1.0
            for value in values:
                result *= value
            return result
        if record.operation == "divide":
            result = values[0]
            for value in values[1:]:
                if value == 0:
                    raise EvidenceError("division_by_zero")
                result /= value
            return result
        raise EvidenceError("missing_or_unknown_operation")

    def to_dict(self) -> Dict[str, object]:
        return {"snapshot_id": self.snapshot_id, "records": [asdict(record) for record in self.records()]}
