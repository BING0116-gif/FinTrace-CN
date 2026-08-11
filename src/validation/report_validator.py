"""Report validator — extracts numbers from rendered Markdown and cross-checks
them against the EvidenceLedger.

This module does NOT use an LLM judge for numeric checks.  It uses a simple
regex-based extraction to find numbers in the report text and match them against
known evidence records, flagging any unsupported number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.cn.evidence import EvidenceLedger


# Regex to find financial numbers in report text:
#   - CNY amounts: ¥1,234.56  or  1,234.56 元
#   - Percentages: 12.34%
#   - Multiples: 25.5x  or  25.5 倍
#   - Per-share: 123.45 元/股
_NUMBER_RE = re.compile(
    r"(?:¥|CNY\s*)?"
    r"(\d+(?:,\d{3})*(?:\.\d+)?)"
    r"(?:\s*(元|亿元|万元|美元|%/percent|倍|x|元/股|CNY/share))?"
)

# Match backtick-quoted evidence IDs so we can skip numbers inside them.
_EVIDENCE_ID_RE = re.compile(r"`(fact_\w+|calc_\w+)`")


@dataclass(frozen=True)
class ReportValidationResult:
    valid: bool
    errors: List[str]
    unsupported_numbers: List[Dict[str, object]]
    citation_coverage_rate: float


class ReportValidator:
    """Extract and cross-check numbers in a rendered Markdown report."""

    def __init__(self, ledger: EvidenceLedger):
        self._ledger = ledger

    def validate(self, report_markdown: str) -> ReportValidationResult:
        records = self._ledger.records()
        known_values = {r.value for r in records if r.value is not None}
        known_ids = {r.evidence_id for r in records}

        # Find all cited evidence IDs in the report
        cited_ids = set(re.findall(r"`(fact_\w+|calc_\w+)`", report_markdown))

        # Build a set of positions occupied by backtick-quoted evidence IDs
        # so we can skip numbers inside them.
        skip_positions = set()
        for match in _EVIDENCE_ID_RE.finditer(report_markdown):
            for i in range(match.start(), match.end()):
                skip_positions.add(i)

        # Find all numbers in the report, skipping those inside evidence IDs
        unsupported: List[Dict[str, object]] = []
        for match in _NUMBER_RE.finditer(report_markdown):
            if any(i in skip_positions for i in range(match.start(), match.end())):
                continue
            raw = match.group(1).replace(",", "")
            try:
                value = float(raw)
            except ValueError:
                continue
            # Check if this value is close to any known evidence value
            if not any(abs(value - known) / max(abs(known), 1.0) < 0.001 for known in known_values):
                unsupported.append({
                    "value": value,
                    "unit": match.group(2) or "",
                    "context": report_markdown[max(0, match.start() - 30):match.end() + 30],
                })

        errors: List[str] = []
        # Check that all cited evidence IDs actually exist
        missing_citations = cited_ids - known_ids
        if missing_citations:
            errors.append(f"missing_evidence_ids:{','.join(sorted(missing_citations))}")

        # Check that key numbers have citations
        total_citations = len(cited_ids)
        coverage = total_citations / len(known_ids) if known_ids else 1.0

        return ReportValidationResult(
            valid=not errors and len(unsupported) == 0,
            errors=errors,
            unsupported_numbers=unsupported,
            citation_coverage_rate=min(coverage, 1.0),
        )