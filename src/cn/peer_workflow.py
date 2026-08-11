"""Deterministic peer selection, valuation ranges, and validation for A-shares."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Literal, Optional

from .valuation import MultipleName, PeerValuationInput, implied_price, summarize_peer_multiple


@dataclass(frozen=True)
class PeerCandidate:
    valuation: PeerValuationInput
    industry_code: str
    evidence_ids: Dict[str, str] = field(default_factory=dict)
    is_bank_or_insurer: bool = False


@dataclass(frozen=True)
class PeerDecision:
    symbol: str
    included: bool
    reason: str


@dataclass(frozen=True)
class PeerValuationResult:
    decisions: List[PeerDecision]
    multiples: Dict[str, Dict[str, object]]
    validation: Dict[str, object]


def select_peers(target: PeerCandidate, candidates: Iterable[PeerCandidate]) -> tuple[List[PeerCandidate], List[PeerDecision]]:
    """Keep only same-industry, same-period peers with the required evidence."""
    selected: List[PeerCandidate] = []
    decisions: List[PeerDecision] = []
    for candidate in candidates:
        if candidate.valuation.symbol == target.valuation.symbol:
            decisions.append(PeerDecision(candidate.valuation.symbol, False, "target_company"))
        elif candidate.industry_code != target.industry_code:
            decisions.append(PeerDecision(candidate.valuation.symbol, False, "industry_mismatch"))
        elif candidate.valuation.period_basis != target.valuation.period_basis:
            decisions.append(PeerDecision(candidate.valuation.symbol, False, "period_basis_mismatch"))
        elif candidate.valuation.raw_price <= 0 or candidate.valuation.total_shares <= 0:
            decisions.append(PeerDecision(candidate.valuation.symbol, False, "invalid_price_or_shares"))
        elif not candidate.evidence_ids:
            decisions.append(PeerDecision(candidate.valuation.symbol, False, "missing_evidence_ids"))
        else:
            selected.append(candidate)
            decisions.append(PeerDecision(candidate.valuation.symbol, True, "same_industry_same_period"))
    return selected, decisions


def _applicable_multiples(target: PeerCandidate) -> List[MultipleName]:
    # First-release suitability matrix: financial institutions are assessed using
    # PE/PB only; EV/EBITDA is intentionally absent from this P0 workflow.
    return ["PE", "PB"] if target.is_bank_or_insurer else ["PE", "PB", "PS"]


def value_with_peers(target: PeerCandidate, candidates: Iterable[PeerCandidate]) -> PeerValuationResult:
    selected, decisions = select_peers(target, candidates)
    multiples: Dict[str, Dict[str, object]] = {}
    denominator = {"PE": "net_profit", "PB": "book_equity", "PS": "revenue"}
    for name in _applicable_multiples(target):
        summary = summarize_peer_multiple([item.valuation for item in selected], name)
        multiples[name] = {
            "median": summary.median,
            "included_symbols": summary.included_symbols,
            "excluded": summary.excluded,
            "confidence": summary.confidence,
            "implied_price": implied_price(target.valuation, multiple=summary, denominator=denominator[name]),
        }
    validation = validate_peer_valuation(target, selected, multiples)
    return PeerValuationResult(decisions, multiples, validation)


def validate_peer_valuation(target: PeerCandidate, peers: Iterable[PeerCandidate], multiples: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    """Validate non-negotiable valuation inputs without fabricating a pass."""
    peers = list(peers)
    errors: List[str] = []
    warnings: List[str] = []
    recalculated: Dict[str, float] = {}
    if target.valuation.raw_price <= 0 or target.valuation.total_shares <= 0:
        errors.append("invalid_target_price_or_shares")
    if target.valuation.period_basis == "RAW":
        errors.append("invalid_period_basis")
    if len(peers) < 4:
        warnings.append("peer_count_below_4_low_confidence")
    for name, result in multiples.items():
        median = result.get("median")
        implied = result.get("implied_price")
        if median is None:
            warnings.append(f"unavailable_{name.lower()}")
            continue
        denominator = {"PE": target.valuation.net_profit, "PB": target.valuation.book_equity, "PS": target.valuation.revenue}[name]
        if denominator is None or denominator <= 0:
            errors.append(f"invalid_target_{name.lower()}_denominator")
            continue
        expected = float(median) * denominator / target.valuation.total_shares
        recalculated[f"implied_price_{name}"] = expected
        if implied is None or abs(float(implied) - expected) > 1e-9:
            errors.append(f"implied_price_mismatch_{name.lower()}")
    all_items = [target, *peers]
    evidence_total = sum(len(item.evidence_ids) for item in all_items)
    coverage = evidence_total / (len(all_items) * 5) if all_items else 0.0
    if coverage < 0.95:
        warnings.append("evidence_coverage_below_95_percent")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "recalculated_values": recalculated, "evidence_coverage": coverage}


def result_to_dict(result: PeerValuationResult) -> Dict[str, object]:
    return {"decisions": [asdict(item) for item in result.decisions], "multiples": result.multiples, "validation": result.validation}
