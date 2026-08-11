"""Deterministic peer-multiple calculations for A-share research."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Dict, Iterable, List, Literal, Optional


MultipleName = Literal["PE", "PB", "PS"]


@dataclass(frozen=True)
class PeerValuationInput:
    symbol: str
    raw_price: float
    total_shares: float
    net_profit: Optional[float]
    book_equity: Optional[float]
    revenue: Optional[float]
    period_basis: str

    @property
    def market_cap(self) -> float:
        return self.raw_price * self.total_shares


@dataclass(frozen=True)
class PeerMultiple:
    symbol: str
    name: MultipleName
    value: Optional[float]
    exclusion_reason: Optional[str] = None


@dataclass(frozen=True)
class MultipleSummary:
    name: MultipleName
    median: Optional[float]
    included_symbols: List[str]
    excluded: Dict[str, str]
    confidence: Literal["high", "medium", "low", "unavailable"]


def calculate_multiple(peer: PeerValuationInput, name: MultipleName) -> PeerMultiple:
    if peer.raw_price <= 0 or peer.total_shares <= 0:
        return PeerMultiple(peer.symbol, name, None, "invalid_raw_price_or_shares")
    denominator = {
        "PE": peer.net_profit,
        "PB": peer.book_equity,
        "PS": peer.revenue,
    }[name]
    if denominator is None or denominator <= 0:
        return PeerMultiple(peer.symbol, name, None, f"non_positive_{name}_denominator")
    return PeerMultiple(peer.symbol, name, peer.market_cap / denominator)


def _iqr_bounds(values: List[float]) -> tuple[float, float]:
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    lower_half = sorted_values[:midpoint]
    upper_half = sorted_values[midpoint + (len(sorted_values) % 2):]
    q1, q3 = median(lower_half), median(upper_half)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def summarize_peer_multiple(peers: Iterable[PeerValuationInput], name: MultipleName) -> MultipleSummary:
    """Filter invalid values and IQR outliers before calculating a peer median."""
    computed = [calculate_multiple(peer, name) for peer in peers]
    excluded = {item.symbol: item.exclusion_reason for item in computed if item.exclusion_reason}
    valid = [item for item in computed if item.value is not None]
    if not valid:
        return MultipleSummary(name, None, [], excluded, "unavailable")

    # IQR becomes meaningful only with four or more valid peers.  Smaller samples
    # remain visible but explicitly have low confidence rather than fabricated
    # outlier decisions.
    included = valid
    if len(valid) >= 4:
        lower, upper = _iqr_bounds([item.value for item in valid if item.value is not None])
        included = []
        for item in valid:
            if item.value is not None and not lower <= item.value <= upper:
                excluded[item.symbol] = "iqr_outlier"
            else:
                included.append(item)
    confidence: Literal["high", "medium", "low", "unavailable"]
    confidence = "high" if len(included) >= 6 else "medium" if len(included) >= 4 else "low"
    return MultipleSummary(
        name=name,
        median=median([item.value for item in included if item.value is not None]) if included else None,
        included_symbols=[item.symbol for item in included],
        excluded=excluded,
        confidence=confidence if included else "unavailable",
    )


def implied_price(
    target: PeerValuationInput, *, multiple: MultipleSummary, denominator: Literal["net_profit", "book_equity", "revenue"]
) -> Optional[float]:
    """Return a per-share value only when the target and peer basis are valid."""
    if multiple.median is None or target.total_shares <= 0:
        return None
    value = getattr(target, denominator)
    if value is None or value <= 0:
        return None
    return multiple.median * value / target.total_shares
