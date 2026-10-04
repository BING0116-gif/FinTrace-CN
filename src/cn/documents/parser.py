"""Deterministic page extraction for PDF and plain-text research inputs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .schema import DocumentRecord, ExtractedFact, ParseResult, SourceFragment


_METRIC_PATTERNS = (
    ("revenue", re.compile(r"(?:营业收入|营业总收入)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("net_profit", re.compile(r"(?:归母净利润|归属于母公司股东的净利润)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("net_profit_deducted", re.compile(r"(?:扣非净利润|扣除非经常性损益后的净利润)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("minority_interest_profit", re.compile(r"(?:少数股东损益|少数股东损益影响)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("equity_parent", re.compile(r"(?:归属于母公司股东权益|母公司股东权益)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("net_assets_parent", re.compile(r"(?:母公司净资产)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("net_assets_consolidated", re.compile(r"(?:合并净资产|所有者权益合计)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
    ("net_profit", re.compile(r"(?<!归母)(?<!扣非)(?<!少数股东)(?:净利润)\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*(亿元|万元|百万元|元)")),
)


def _scope_from_text(text: str) -> str | None:
    """Infer scope only when the disclosure explicitly establishes it.

    This helper is intentionally conservative for generic metrics such as
    revenue: a page can contain both parent and consolidated rows, so callers
    should prefer the metric-local text below whenever possible.
    """
    if any(token in text for token in ("母公司", "归母", "归属于母公司")) and "合并" not in text:
        return "parent"
    if "合并" in text:
        return "consolidated"
    return None


def _fact_scope(metric: str, matched_text: str, fragment_text: str) -> str | None:
    """Resolve scope for one candidate without borrowing a neighbouring row."""
    if metric in {"net_profit_parent", "net_assets_parent", "equity_parent"}:
        return "parent"
    if metric in {"net_assets_consolidated", "minority_interest_profit"}:
        return "consolidated"
    local = _scope_from_text(matched_text)
    return local if local is not None else _scope_from_text(fragment_text)


def _version_from_text(text: str) -> str:
    if any(token in text for token in ("重述", "重列")):
        return "RESTATED"
    if any(token in text for token in ("更正后", "调整后", "更正公告")):
        return "CORRECTED"
    return "AS_REPORTED"


class DocumentParseError(ValueError):
    """The registered document cannot be parsed safely."""


def _fragment_id(document_id: str, page_number: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"frag_{document_id}_{page_number}_{digest}"


class DocumentParser:
    name = "pymupdf_or_text"
    version = "1.0.0"

    def parse(self, record: DocumentRecord, path: str | Path) -> ParseResult:
        source_path = Path(path)
        if not source_path.is_file():
            raise DocumentParseError("Registered document is no longer available.")
        if source_path.suffix.lower() in {".txt", ".md"}:
            pages = [(page_number, text, None, "text_layer", "exact")
                     for page_number, text in enumerate(source_path.read_text(encoding="utf-8").split("\f"), 1)]
        elif source_path.suffix.lower() == ".pdf":
            pages = self._parse_pdf(source_path)
        else:
            raise DocumentParseError("Unsupported document type.")

        fragments: list[SourceFragment] = []
        warnings: list[str] = []
        for page_number, text, bbox, method, confidence in pages:
            clean = text.strip()
            if not clean:
                warnings.append(f"page_{page_number}:empty_text_layer")
                method, confidence = "ocr_required", "unavailable"
            fragments.append(SourceFragment(
                fragment_id=_fragment_id(record.document_id, page_number, clean),
                document_id=record.document_id, page_number=page_number,
                text=clean, text_sha256=hashlib.sha256(clean.encode("utf-8")).hexdigest(),
                extraction_method=method, confidence=confidence, bbox=bbox,
            ))
        facts = tuple(self._extract_candidate_facts(record, fragments))
        status = "complete" if not warnings else "partial"
        parsed_record = DocumentRecord(
            document_id=record.document_id, file_name=record.file_name,
            document_type=record.document_type, sha256=record.sha256,
            ingested_at=record.ingested_at, source=record.source, status=status,
            symbol=record.symbol, fiscal_period=record.fiscal_period,
            published_at=record.published_at, parser_name=self.name,
            parser_version=self.version, page_count=len(fragments),
            warnings=tuple(warnings),
        )
        return ParseResult(parsed_record, tuple(fragments), facts, tuple(warnings))

    def _parse_pdf(self, path: Path) -> list[tuple[int, str, tuple[float, float, float, float] | None, str, str]]:
        try:
            try:
                import pymupdf as fitz  # type: ignore
            except ImportError:
                import fitz  # type: ignore
        except ImportError as exc:
            raise DocumentParseError("PDF parsing requires the optional PyMuPDF dependency.") from exc
        try:
            pdf = fitz.open(path)
        except Exception as exc:  # noqa: BLE001 - convert parser internals to a safe error
            raise DocumentParseError("PDF could not be opened.") from exc
        pages = []
        try:
            for index, page in enumerate(pdf, 1):
                blocks = page.get_text("blocks")
                text = "\n".join(str(block[4]) for block in blocks if len(block) >= 5)
                bbox = None
                if blocks:
                    xs = [float(block[0]) for block in blocks] + [float(block[2]) for block in blocks]
                    ys = [float(block[1]) for block in blocks] + [float(block[3]) for block in blocks]
                    bbox = (min(xs), min(ys), max(xs), max(ys))
                pages.append((index, text, bbox, "text_layer", "exact"))
        finally:
            pdf.close()
        return pages

    @staticmethod
    def _extract_candidate_facts(record: DocumentRecord, fragments: Iterable[SourceFragment]) -> list[ExtractedFact]:
        facts: list[ExtractedFact] = []
        for fragment in fragments:
            version = _version_from_text(fragment.text)
            for metric, pattern in _METRIC_PATTERNS:
                for match in pattern.finditer(fragment.text):
                    value = float(match.group(1))
                    unit = match.group(2)
                    matched_text = match.group(0)
                    accounting_metric = (
                        "net_profit_parent"
                        if metric == "net_profit" and ("归母" in matched_text or "归属于母公司" in matched_text)
                        else metric
                    )
                    fact_id = f"fact_{record.document_id}_{metric}_{fragment.page_number}_{len(facts) + 1}"
                    facts.append(ExtractedFact(
                        fact_id=fact_id, metric=metric, raw_value=value,
                        raw_unit=unit, raw_currency="CNY", period=record.fiscal_period,
                        scope=_fact_scope(accounting_metric, matched_text, fragment.text),
                        version=version, source_fragment_id=fragment.fragment_id,
                        accounting_metric=accounting_metric,
                    ))
        return facts
