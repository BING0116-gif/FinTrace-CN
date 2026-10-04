"""Explicit source-conflict and version-supersession resolution (CARD-13)."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable, Mapping

from .normalization import NormalizedFact

RESOLVER_VERSION = "cn-conflict-resolver-1.0.0"
DATA_CONFLICT = "DATA_CONFLICT"
VERSION_SUPERSESSION = "VERSION_SUPERSESSION"
NEW_INFORMATION = "NEW_INFORMATION"
_VERSION_RANK = {"AS_REPORTED": 0, "RESTATED": 1, "CORRECTED": 2}

@dataclass(frozen=True)
class ConflictRecord:
    conflict_id: str
    change_kind: str
    source_a: str
    source_b: str
    selected_source: str
    reason: str
    resolver: str = RESOLVER_VERSION
    timestamp: str = ""
    metric: str = ""
    period: str = ""
    unresolved: bool = False

    def to_dict(self) -> dict[str, Any]: return asdict(self)

def _source_id(fact: NormalizedFact) -> str: return str(fact.fact_id or (fact.source_evidence_ids[0] if fact.source_evidence_ids else fact.provider))
def _priority(fact: NormalizedFact) -> int:
    provider = str(fact.provider or "").lower()
    if any(token in provider for token in ("exchange", "cninfo", "csrc", "regulator", "regulatory", "official_filing")): return 3
    if any(token in provider for token in ("company", "issuer", "announcement", "annual_report")): return 2
    return 1
def _same_key(fact: NormalizedFact) -> tuple[Any, ...]: return (fact.symbol, fact.metric, fact.fiscal_period, fact.period_basis, fact.currency, fact.unit, fact.scope, fact.version)
def _same_basis(a: NormalizedFact, b: NormalizedFact) -> bool: return (a.symbol, a.metric, a.fiscal_period, a.period_basis, a.currency, a.unit, a.scope) == (b.symbol, b.metric, b.fiscal_period, b.period_basis, b.currency, b.unit, b.scope)
def _close(a: float, b: float, tolerance: float) -> bool: return abs(float(a) - float(b)) <= tolerance * max(1.0, abs(float(a)), abs(float(b)))
def _record_id(a: NormalizedFact, b: NormalizedFact, kind: str) -> str: return "conflict_" + hashlib.sha256(f"{_source_id(a)}|{_source_id(b)}|{kind}".encode()).hexdigest()[:16]
def _record(a: NormalizedFact, b: NormalizedFact, kind: str, selected: str, reason: str, *, unresolved: bool = False) -> ConflictRecord:
    return ConflictRecord(_record_id(a, b, kind), kind, _source_id(a), _source_id(b), selected, reason, timestamp=datetime.now(timezone.utc).isoformat(), metric=a.metric, period=a.fiscal_period, unresolved=unresolved)

def resolve_conflicts(facts: list[NormalizedFact], *, tolerance: float = 1e-9) -> tuple[list[NormalizedFact], list[ConflictRecord]]:
    """Resolve same-basis candidates without silently overwriting any source.

    Scope, unit, period, or version differences are not treated as numeric
    conflicts.  Unresolved same-priority disagreements are omitted from the
    selected facts so downstream validators can fail closed.
    """
    selected: list[NormalizedFact] = []; records: list[ConflictRecord] = []
    candidates = list(facts)
    groups: dict[tuple[Any, ...], list[NormalizedFact]] = {}
    for fact in candidates: groups.setdefault((fact.symbol, fact.metric, fact.fiscal_period, fact.period_basis, fact.currency, fact.unit, fact.scope), []).append(fact)
    for _, group in groups.items():
        if len(group) == 1: selected.extend(group); continue
        ordered = sorted(group, key=lambda f: (str(f.published_at or ""), _VERSION_RANK.get(str(f.version), 0), _priority(f)), reverse=True)
        if all(_close(group[0].value, item.value, tolerance) for item in group[1:]):
            selected.append(ordered[0]); continue
        corrected = [item for item in group if str(item.version) in {"CORRECTED", "RESTATED"}]
        original = [item for item in group if str(item.version) == "AS_REPORTED"]
        if corrected and original:
            winner = max(corrected, key=lambda f: (str(f.published_at or ""), _VERSION_RANK.get(str(f.version), 0)))
            loser = max(original, key=lambda f: str(f.published_at or ""))
            selected.append(winner)
            records.append(_record(loser, winner, VERSION_SUPERSESSION, _source_id(winner), "VERSION_SUPERSESSION: later explicit corrected/restated disclosure supersedes AS_REPORTED"))
            continue
        ranked = sorted(group, key=lambda f: (_priority(f), str(f.published_at or "")), reverse=True)
        if len(ranked) > 1 and _priority(ranked[0]) > _priority(ranked[1]):
            winner, loser = ranked[0], ranked[1]
            selected.append(winner)
            records.append(_record(loser, winner, DATA_CONFLICT, _source_id(winner), "SOURCE_PRIORITY: regulatory disclosure > company official announcement > third-party source"))
        else:
            records.append(_record(ranked[0], ranked[1], DATA_CONFLICT, "", "UNRESOLVED: same-priority sources disagree; downstream fact is blocked", unresolved=True))
    # Different periods are additive information, not replacements.
    by_metric: dict[tuple[Any, ...], set[str]] = {}
    for fact in candidates: by_metric.setdefault((fact.symbol, fact.metric, fact.period_basis, fact.scope), set()).add(fact.fiscal_period)
    for key, periods in by_metric.items():
        if len(periods) > 1:
            rows = [f for f in candidates if (f.symbol, f.metric, f.period_basis, f.scope) == key]
            if rows:
                newest = max(rows, key=lambda f: str(f.fiscal_period)); oldest = min(rows, key=lambda f: str(f.fiscal_period))
                records.append(_record(oldest, newest, NEW_INFORMATION, _source_id(newest), "NEW_INFORMATION: new fiscal period adds information and does not replace history"))
    return selected, records

def unresolved_report(conflicts: Iterable[ConflictRecord]) -> list[dict[str, Any]]:
    return [item.to_dict() if isinstance(item, ConflictRecord) else dict(item) for item in conflicts if bool(item.unresolved if isinstance(item, ConflictRecord) else item.get("unresolved"))]
