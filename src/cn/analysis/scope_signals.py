"""Deterministic accounting-scope and restatement signal detection.

This module intentionally works only from extracted document text and facts.
It is not an LLM classifier: an unrecognised but suspicious disclosure remains
``unknown`` and conservatively blocks YoY rather than being guessed away.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, Sequence

from ..documents.schema import DocumentRecord, ExtractedFact, SourceFragment


SCOPE_SIGNAL_SCHEMA_VERSION = "cn-accounting-scope-signal-1.0.0"


class ScopeSignalType(str, Enum):
    RESTATED = "restated"
    ACCOUNTING_POLICY_CHANGE = "accounting_policy_change"
    PRIOR_PERIOD_ERROR_CORRECTION = "prior_period_error_correction"
    CONSOLIDATION_SCOPE_CHANGE = "consolidation_scope_change"
    COMPARABLE_PERIOD_ADJUSTED = "comparable_period_adjusted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AccountingScopeSignal:
    signal_type: ScopeSignalType
    company: str
    periods_affected: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    detected_at: str
    detector_rule: str
    severity: str = "materiality_unknown"
    comparison_data_available: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["schema_version"] = SCOPE_SIGNAL_SCHEMA_VERSION
        payload["signal_type"] = self.signal_type.value
        payload["periods_affected"] = list(self.periods_affected)
        payload["evidence_ids"] = list(self.evidence_ids)
        return payload


# Order is deliberate: the most specific correction disclosure wins over a
# generic word such as "调整" in the same paragraph.
_RULES: tuple[tuple[ScopeSignalType, tuple[str, ...], str], ...] = (
    (ScopeSignalType.PRIOR_PERIOD_ERROR_CORRECTION, ("前期差错更正", "会计差错更正"), "prior_period_error_correction_keywords"),
    (ScopeSignalType.ACCOUNTING_POLICY_CHANGE, ("会计政策变更", "会计政策和会计估计变更", "会计政策、会计估计变更"), "accounting_policy_change_keywords"),
    (ScopeSignalType.CONSOLIDATION_SCOPE_CHANGE, ("合并范围变化", "合并范围发生变化", "合并报表范围", "纳入合并范围", "不再纳入合并范围"), "consolidation_scope_change_keywords"),
    (ScopeSignalType.RESTATED, ("重述", "重列", "追溯调整", "restated", "restatement"), "restatement_keywords"),
    (ScopeSignalType.COMPARABLE_PERIOD_ADJUSTED, ("调整后", "更正后", "比较期间已调整", "comparative period adjusted"), "adjusted_comparative_keywords"),
)
_SUSPICIOUS = ("更正公告", "调整", "更正", "重大影响", "restatement", "recast")


def _document_parts(item: object) -> tuple[DocumentRecord | None, tuple[SourceFragment, ...], tuple[ExtractedFact, ...]]:
    if isinstance(item, SourceFragment):
        return None, (item,), ()
    document = getattr(item, "document", item if isinstance(item, DocumentRecord) else None)
    fragments = tuple(getattr(item, "fragments", ()))
    facts = tuple(getattr(item, "facts", ()))
    return document if isinstance(document, DocumentRecord) else None, fragments, facts


def detect_scope_signals(
    facts: Iterable[ExtractedFact] = (), documents: Iterable[object] = (),
) -> list[AccountingScopeSignal]:
    """Detect disclosed accounting changes, binding every result to a fragment.

    ``facts`` may be supplied separately for callers that retain an extraction
    ledger; document-local facts are also considered when deciding whether a
    corrected/restated comparison value is available.
    """
    supplied_facts = tuple(facts)
    output: list[AccountingScopeSignal] = []
    for item in documents:
        document, fragments, local_facts = _document_parts(item)
        company = (document.symbol if document and document.symbol else "unknown")
        document_period = document.fiscal_period if document else None
        all_facts = supplied_facts + local_facts
        for fragment in fragments:
            text = fragment.text
            matched = next(((kind, rule) for kind, words, rule in _RULES if any(word in text for word in words)), None)
            if matched is None:
                if not any(word in text for word in _SUSPICIOUS):
                    continue
                kind, rule = ScopeSignalType.UNKNOWN, "suspicious_unclassified_disclosure"
            else:
                kind, rule = matched
            periods = tuple(sorted({fact.period for fact in all_facts if fact.source_fragment_id == fragment.fragment_id and fact.period} | ({document_period} if document_period else set())))
            adjusted_available = any(
                fact.source_fragment_id == fragment.fragment_id
                and fact.version in {"CORRECTED", "RESTATED"}
                for fact in all_facts
            )
            severity = "material" if "重大" in text else "materiality_unknown"
            output.append(AccountingScopeSignal(
                signal_type=kind, company=company, periods_affected=periods,
                evidence_ids=(fragment.fragment_id,), detected_at=document.published_at if document and document.published_at else "unknown",
                detector_rule=rule, severity=severity, comparison_data_available=adjusted_available,
            ))
    return output


def comparability_decision(signal: AccountingScopeSignal) -> str:
    """Return the only allowed action for a disclosure signal."""
    if signal.signal_type in {ScopeSignalType.PRIOR_PERIOD_ERROR_CORRECTION, ScopeSignalType.RESTATED}:
        return "use_adjusted" if signal.comparison_data_available else "block_yoy"
    if signal.signal_type is ScopeSignalType.COMPARABLE_PERIOD_ADJUSTED:
        return "use_adjusted" if signal.comparison_data_available else "block_yoy"
    if signal.signal_type is ScopeSignalType.CONSOLIDATION_SCOPE_CHANGE:
        return "warning"
    if signal.signal_type is ScopeSignalType.UNKNOWN and signal.severity == "material":
        return "block_yoy"
    return "warning"


def detection_coverage() -> dict[str, object]:
    return {"schema_version": SCOPE_SIGNAL_SCHEMA_VERSION, "rules": [rule for _, _, rule in _RULES], "unknown_rule": "suspicious_unclassified_disclosure"}
