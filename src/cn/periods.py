"""Deterministic A-share financial-period conversion.

Income-statement and cash-flow values in H1/9M/FY reports are usually
year-to-date cumulative amounts.  This module derives single quarters and TTM
only when every required input period is present; it never invents a number.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Literal, Optional, Tuple

from .domain import FinancialStatement


_PERIOD = re.compile(r"^(?P<year>\d{4})(?P<kind>Q1|H1|9M|FY)$")
_FLOW_TYPES = {"income", "cashflow"}


class PeriodEngineError(ValueError):
    """Input periods are unsuitable for a deterministic conversion."""


@dataclass(frozen=True)
class DerivedPeriod:
    statement_type: Literal["income", "cashflow"]
    fiscal_period: str
    period_basis: str
    values: Dict[str, Optional[float]]
    source_periods: Tuple[str, ...]


def _parse_period(fiscal_period: str) -> Tuple[int, str]:
    match = _PERIOD.fullmatch(fiscal_period)
    if not match:
        raise PeriodEngineError(f"Unsupported fiscal period '{fiscal_period}'.")
    return int(match.group("year")), match.group("kind")


def _subtract(left: Dict[str, Optional[float]], right: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    return {
        key: (None if left.get(key) is None or right.get(key) is None else left[key] - right[key])
        for key in sorted(set(left) | set(right))
    }


def _add_subtract(
    current: Dict[str, Optional[float]],
    previous_fy: Dict[str, Optional[float]],
    previous_same_period: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    return {
        key: (
            None
            if current.get(key) is None or previous_fy.get(key) is None or previous_same_period.get(key) is None
            else current[key] + previous_fy[key] - previous_same_period[key]
        )
        for key in sorted(set(current) | set(previous_fy) | set(previous_same_period))
    }


class FinancialPeriodEngine:
    """Converts cumulative A-share flow statements into comparable periods."""

    @staticmethod
    def _index(records: Iterable[FinancialStatement], statement_type: str) -> Dict[Tuple[int, str], FinancialStatement]:
        indexed: Dict[Tuple[int, str], FinancialStatement] = {}
        for record in records:
            if record.statement_type != statement_type:
                continue
            year, kind = _parse_period(record.fiscal_period)
            if (year, kind) in indexed:
                raise PeriodEngineError(f"Duplicate {statement_type} record for {record.fiscal_period}.")
            indexed[(year, kind)] = record
        return indexed

    @classmethod
    def derive_single_quarters(
        cls, records: Iterable[FinancialStatement], statement_type: Literal["income", "cashflow"]
    ) -> List[DerivedPeriod]:
        if statement_type not in _FLOW_TYPES:
            raise PeriodEngineError("Balance-sheet records are stock values and cannot be differenced.")
        indexed = cls._index(records, statement_type)
        results: List[DerivedPeriod] = []
        for year in sorted({year for year, _ in indexed}):
            q1 = indexed.get((year, "Q1"))
            h1 = indexed.get((year, "H1"))
            nine_month = indexed.get((year, "9M"))
            fy = indexed.get((year, "FY"))
            if q1:
                results.append(DerivedPeriod(statement_type, f"{year}Q1", "SINGLE_QUARTER", q1.values, (q1.fiscal_period,)))
            if h1 and q1:
                results.append(DerivedPeriod(statement_type, f"{year}Q2", "SINGLE_QUARTER", _subtract(h1.values, q1.values), (h1.fiscal_period, q1.fiscal_period)))
            if nine_month and h1:
                results.append(DerivedPeriod(statement_type, f"{year}Q3", "SINGLE_QUARTER", _subtract(nine_month.values, h1.values), (nine_month.fiscal_period, h1.fiscal_period)))
            if fy and nine_month:
                results.append(DerivedPeriod(statement_type, f"{year}Q4", "SINGLE_QUARTER", _subtract(fy.values, nine_month.values), (fy.fiscal_period, nine_month.fiscal_period)))
        return results

    @classmethod
    def derive_ttm(
        cls, records: Iterable[FinancialStatement], statement_type: Literal["income", "cashflow"]
    ) -> List[DerivedPeriod]:
        if statement_type not in _FLOW_TYPES:
            raise PeriodEngineError("Balance-sheet records have no TTM conversion.")
        indexed = cls._index(records, statement_type)
        results: List[DerivedPeriod] = []
        for (year, kind), current in sorted(indexed.items()):
            if kind == "FY":
                results.append(DerivedPeriod(statement_type, f"{year}FY", "TTM", current.values, (current.fiscal_period,)))
                continue
            previous_fy = indexed.get((year - 1, "FY"))
            previous_same = indexed.get((year - 1, kind))
            if previous_fy and previous_same:
                results.append(
                    DerivedPeriod(
                        statement_type,
                        f"{year}{kind}",
                        "TTM",
                        _add_subtract(current.values, previous_fy.values, previous_same.values),
                        (current.fiscal_period, previous_fy.fiscal_period, previous_same.fiscal_period),
                    )
                )
        return results
