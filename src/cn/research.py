"""Structured, auditable planning state for offline A-share research."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ResearchPlan:
    intent: str
    symbol: str
    research_as_of: str
    tasks: List[str]
    required_evidence: List[str]


@dataclass(frozen=True)
class ToolTrace:
    tool_name: str
    arguments: Dict[str, object]
    started_at: str
    ended_at: str
    result_status: str
    provider: Optional[str] = None
    retry_count: int = 0
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class ResearchState:
    trace_id: str
    query: str
    research_as_of: str
    symbol: str
    plan: ResearchPlan
    facts: List[str] = field(default_factory=list)
    calculations: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    validation_result: Optional[Dict[str, object]] = None
    tool_trace: List[ToolTrace] = field(default_factory=list)
    cost_trace: List[Dict[str, object]] = field(default_factory=list)
    report: Optional[str] = None
    recovery_attempts: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def create(cls, *, query: str, symbol: str, research_as_of: str, intent: str = "valuation_research") -> "ResearchState":
        plan = ResearchPlan(intent, symbol, research_as_of,
                            ["company_profile", "latest_price", "financials", "peer_selection", "peer_valuation", "validation", "report"],
                            ["price", "shares", "net_profit_ttm", "peer_multiples"])
        return cls(uuid4().hex, query, research_as_of, symbol, plan)

    def record_tool(self, *, tool_name: str, arguments: Dict[str, object], started_at: str, result_status: str,
                    provider: Optional[str] = None, retry_count: int = 0, evidence_ids: Optional[List[str]] = None,
                    ended_at: Optional[str] = None) -> None:
        self.tool_trace.append(ToolTrace(tool_name, arguments, started_at, ended_at or _now(), result_status, provider, retry_count, evidence_ids or []))

    def register_evidence(self, evidence_ids: List[str]) -> None:
        for evidence_id in evidence_ids:
            destination = self.calculations if evidence_id.startswith("calc_") else self.facts
            if evidence_id not in destination:
                destination.append(evidence_id)

    def request_recovery(self, reason: str, *, max_attempts: int = 2) -> bool:
        attempts = self.recovery_attempts.get(reason, 0)
        if attempts >= max_attempts:
            self.conflicts.append(f"recovery_limit_reached:{reason}")
            return False
        self.recovery_attempts[reason] = attempts + 1
        return True

    def finalize_validation(self, result: Dict[str, object]) -> None:
        self.validation_result = result
        for item in result.get("missing_evidence", []):
            if item not in self.missing_evidence:
                self.missing_evidence.append(str(item))

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
