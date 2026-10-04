"""The only LLM boundary for CARD-05.

The client is injected by the caller.  This module validates and normalizes its
structured response; it never makes a provider call and never decides whether a
claim is true.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from .models import DraftClaim


def _client_result(client: Any, paragraphs: list[dict[str, Any]]) -> Any:
    if callable(client):
        return client(paragraphs)
    for name in ("extract_claims", "complete", "generate"):
        method = getattr(client, name, None)
        if callable(method):
            return method(paragraphs)
    raise TypeError("llm_client must be callable or expose extract_claims/complete/generate")


def _payload(result: Any) -> list[Any]:
    if isinstance(result, str):
        result = json.loads(result)
    if isinstance(result, dict):
        result = result.get("claims", result.get("data", []))
    if not isinstance(result, list):
        raise ValueError("claim extractor output must be a JSON array")
    return result


def _claim(raw: Any, paragraphs: list[dict[str, Any]], index: int) -> DraftClaim | None:
    if not isinstance(raw, dict):
        return None
    sentence = raw.get("sentence")
    if not isinstance(sentence, str) or not sentence.strip():
        return None
    # Preserve the source sentence exactly; reject hallucinated sentence text.
    source_sentences = {str(item.get("text", item.get("sentence", ""))) for item in paragraphs if isinstance(item, dict)}
    if source_sentences and sentence not in source_sentences and not any(sentence in source for source in source_sentences):
        return None
    value = raw.get("value")
    try:
        if isinstance(value, str) and value.strip() and value.strip().replace(".", "", 1).replace("-", "", 1).isdigit():
            value = float(value)
    except (TypeError, ValueError):
        pass
    evidence_ids = raw.get("evidence_ids") or ()
    if isinstance(evidence_ids, str):
        evidence_ids = (evidence_ids,)
    if not isinstance(evidence_ids, (tuple, list)):
        evidence_ids = ()
    return DraftClaim(
        claim_id=str(raw.get("claim_id") or f"draft_claim_{index + 1}"), sentence=sentence,
        page=int(raw["page"]) if raw.get("page") is not None and str(raw["page"]).isdigit() else None,
        metric=str(raw["metric"]) if raw.get("metric") is not None else None,
        period=str(raw["period"]) if raw.get("period") is not None else None,
        value=value, unit=str(raw["unit"]) if raw.get("unit") is not None else None,
        growth=float(raw["growth"]) if raw.get("growth") is not None else None,
        valuation_multiple=str(raw["valuation_multiple"]) if raw.get("valuation_multiple") is not None else None,
        source_reference=str(raw["source_reference"]) if raw.get("source_reference") is not None else None,
        claim_type=str(raw.get("claim_type") or "factual"), scope=raw.get("scope"),
        evidence_ids=tuple(str(item) for item in evidence_ids),
        temporal_status=str(raw.get("temporal_status") or "historical"),
    )


def extract_claims(draft_paragraphs: Iterable[dict[str, Any]], llm_client: Any) -> list[DraftClaim]:
    paragraphs = [dict(item) if isinstance(item, dict) else {"text": str(item)} for item in draft_paragraphs]
    result = _payload(_client_result(llm_client, paragraphs))
    return [claim for index, raw in enumerate(result) if (claim := _claim(raw, paragraphs, index)) is not None]
