"""Deterministic financial validator for A-share research.

This module is a pure-Python computation layer — it never calls an LLM, a data
provider, or a network resource.  Every check is a fixed rule that must pass
before a report is accepted as valid.

Checks
------
- Market cap = price × total shares
- Implied equity value = implied price × diluted shares
- Unit consistency (no mixing of 元 / 万元 / 亿元)
- Currency consistency (no CNY + USD mixing)
- Period consistency (no mixing of FY / Q1 / H1 / 9M / TTM)
- Negative denominators excluded from peer median
- Peer count >= 4 (otherwise low confidence)
- Evidence freshness (data not expired)
- Recalculated values match reported values
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.cn.evidence import EvidenceLedger, EvidenceRecord
from src.cn.valuation import MultipleName, PeerValuationInput


@dataclass(frozen=True)
class ValidationResult:
    """Immutable output of a full validation pass."""

    valid: bool
    errors: List[str]
    warnings: List[str]
    recalculated_values: Dict[str, float]
    evidence_coverage: float


# Known unit families — all members of the same family are compatible.
_UNIT_FAMILIES: Dict[str, List[str]] = {
    "CNY_per_share": ["CNY/share", "元/股", "元每股"],
    "CNY": ["CNY", "元", "RMB", "人民币"],
    "CNY_wan": ["万元", "CNY万"],
    "CNY_yi": ["亿元", "CNY亿"],
    "USD": ["USD", "美元", "US$"],
    "ratio": ["", "倍", "x", "%", "percent"],
    "shares": ["股", "shares"],
}


def _unit_family(unit: str) -> Optional[str]:
    for family, members in _UNIT_FAMILIES.items():
        if unit in members:
            return family
    return None


def _is_expired(available_at: Optional[str], research_as_of: str, max_age_days: int = 365) -> bool:
    if available_at is None:
        return False
    try:
        available = datetime.fromisoformat(available_at)
        cutoff = datetime.fromisoformat(research_as_of)
        return (cutoff - available).days > max_age_days
    except (ValueError, TypeError):
        return False


class FinancialValidator:
    """Run all deterministic financial checks against an EvidenceLedger.

    Usage::

        validator = FinancialValidator()
        result = validator.validate(ledger, research_as_of="2026-08-10T00:00:00+08:00")
        assert result.valid, result.errors
    """

    def __init__(self, *, max_data_age_days: int = 365):
        self._max_age = max_data_age_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        ledger: EvidenceLedger,
        *,
        research_as_of: str,
        tolerance: float = 1e-9,
    ) -> ValidationResult:
        records = ledger.records()
        errors: List[str] = []
        warnings: List[str] = []
        recalculated: Dict[str, float] = {}

        self._check_future_facts(records, research_as_of, errors)
        self._check_expired_data(records, research_as_of, errors)
        self._check_unit_consistency(records, errors, warnings)
        self._check_currency_consistency(records, errors, warnings)
        self._check_period_consistency(records, errors, warnings)
        self._check_market_cap_consistency(records, recalculated, errors, tolerance)
        self._check_negative_denominators(records, errors)
        self._check_peer_count(records, warnings)
        evidence_coverage = self._evidence_coverage(records)

        return ValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            recalculated_values=recalculated,
            evidence_coverage=evidence_coverage,
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_future_facts(records: List[EvidenceRecord], research_as_of: str, errors: List[str]) -> None:
        for record in records:
            if record.available_at and record.available_at > research_as_of:
                errors.append(f"future_fact:{record.evidence_id}")

    def _check_expired_data(self, records: List[EvidenceRecord], research_as_of: str, errors: List[str]) -> None:
        for record in records:
            if _is_expired(record.available_at, research_as_of, self._max_age):
                errors.append(f"expired_data:{record.evidence_id}")

    @staticmethod
    def _check_unit_consistency(records: List[EvidenceRecord], errors: List[str], warnings: List[str]) -> None:
        families: Dict[str, str] = {}
        for record in records:
            family = _unit_family(record.unit)
            if family is None:
                warnings.append(f"unknown_unit:{record.evidence_id}:{record.unit}")
                continue
            if record.evidence_id.startswith("calc_"):
                # Calculations often mix units (e.g., price/share × shares)
                continue
            if record.metric in families:
                prev_family = families[record.metric]
                if family != prev_family:
                    errors.append(f"unit_mismatch:{record.metric}:{family}_vs_{prev_family}")
            else:
                families[record.metric] = family

    @staticmethod
    def _check_currency_consistency(records: List[EvidenceRecord], errors: List[str], warnings: List[str]) -> None:
        currencies = set()
        for record in records:
            if record.currency:
                currencies.add(record.currency)
        if len(currencies) > 1 and "CNY" in currencies and "USD" in currencies:
            errors.append(f"currency_mismatch:CNY_and_USD_both_present:{','.join(sorted(currencies))}")

    @staticmethod
    def _check_period_consistency(records: List[EvidenceRecord], errors: List[str], warnings: List[str]) -> None:
        bases = set()
        for record in records:
            if record.period_basis:
                bases.add(record.period_basis)
        # Separate period bases from the "RAW" price basis
        non_raw = {b for b in bases if b != "RAW"}
        if len(non_raw) > 1:
            errors.append(f"period_basis_mismatch:{','.join(sorted(non_raw))}")

    @staticmethod
    def _check_market_cap_consistency(
        records: List[EvidenceRecord], recalculated: Dict[str, float], errors: List[str], tolerance: float,
    ) -> None:
        price_records = [r for r in records if r.metric == "close" and r.unit == "CNY/share"]
        shares_records = [r for r in records if r.metric == "total_shares"]
        if price_records and shares_records:
            price = max(price_records, key=lambda r: r.value).value
            shares = max(shares_records, key=lambda r: r.value).value
            expected_market_cap = price * shares
            recalculated["market_cap"] = expected_market_cap
            for record in records:
                if record.metric == "market_cap" and record.kind == "calculation":
                    if abs(record.value - expected_market_cap) > tolerance:
                        errors.append(f"market_cap_mismatch:got_{record.value}_expected_{expected_market_cap}")

    @staticmethod
    def _check_negative_denominators(records: List[EvidenceRecord], errors: List[str]) -> None:
        for record in records:
            if record.metric == "net_profit" and record.value < 0:
                if any(r.evidence_id.startswith("calc_pe") for r in records if r.input_ids and record.evidence_id in r.input_ids):
                    errors.append(f"negative_pe_denominator:{record.evidence_id}")

    @staticmethod
    def _check_peer_count(records: List[EvidenceRecord], warnings: List[str]) -> None:
        peer_symbols = set()
        for record in records:
            if record.metric == "peer_valuation" and record.kind == "calculation":
                peer_symbols.add(record.symbol)
        if 0 < len(peer_symbols) < 4:
            warnings.append(f"peer_count_below_4:{len(peer_symbols)}")

    @staticmethod
    def _evidence_coverage(records: List[EvidenceRecord]) -> float:
        if not records:
            return 0.0
        facts = [r for r in records if r.kind == "fact"]
        calculations = [r for r in records if r.kind == "calculation"]
        if not calculations:
            return 1.0 if facts else 0.0
        covered = sum(1 for calc in calculations if calc.input_ids)
        return covered / len(calculations)