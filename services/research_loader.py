"""Cached adapters between Streamlit pages and the existing service contract."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from src.cn import workbench_service as service


@st.cache_data(ttl=300, max_entries=64)
def catalog() -> list[dict[str, Any]]:
    return service.list_research()


@st.cache_data(ttl=300, max_entries=64)
def snapshot(snapshot_id: str) -> dict[str, Any]:
    return service.load_snapshot(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def summary(snapshot_id: str) -> dict[str, Any]:
    return service.research_summary(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def validation(snapshot_id: str) -> dict[str, Any]:
    return service.research_validation(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def readiness(snapshot_id: str) -> dict[str, Any]:
    return service.research_readiness(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def overview_insights(snapshot_id: str) -> dict[str, Any]:
    return service.research_overview_insights(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def market(snapshot_id: str, adjustment: str = "RAW") -> dict[str, Any]:
    return service.research_market(snapshot_id, adjustment)


@st.cache_data(ttl=300, max_entries=64)
def financials(snapshot_id: str) -> dict[str, Any]:
    return service.research_financials(snapshot_id)


@st.cache_data(ttl=128, max_entries=64)
def trends(snapshot_id: str, period_basis: str = "FY") -> dict[str, Any]:
    return service.research_financial_trends(snapshot_id, period_basis)


@st.cache_data(ttl=300, max_entries=64)
def evidence(snapshot_id: str) -> dict[str, Any]:
    return service.research_evidence(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def valuation(snapshot_id: str) -> dict[str, Any]:
    return service.research_valuation(snapshot_id)


@st.cache_data(ttl=300, max_entries=64)
def trace(snapshot_id: str) -> dict[str, Any]:
    return service.research_trace(snapshot_id)


@st.cache_data(ttl=300, max_entries=32)
def report(snapshot_id: str) -> dict[str, Any]:
    return service.research_report(snapshot_id)


@st.cache_data(ttl=300, max_entries=32)
def artifacts(snapshot_id: str) -> dict[str, Any]:
    return service.research_artifacts(snapshot_id)


def current(catalog_rows: list[dict[str, Any]], snapshot_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not snapshot_id:
        return None, None
    try:
        item = next(row for row in catalog_rows if row.get("id") == snapshot_id)
        return item, summary(snapshot_id)
    except (StopIteration, KeyError, ValueError):
        return None, None


def safe_call(fn: Callable[..., dict[str, Any]], *args: Any, fallback: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    """Return an explicit unavailable state instead of crashing a page."""
    try:
        result = fn(*args, **kwargs)
        return result if isinstance(result, dict) else {"data": result}
    except Exception as exc:  # UI boundary: preserve diagnosis, never invent values.
        return {"available": False, "status": "unavailable", "reason": f"{type(exc).__name__}: {exc}", **(fallback or {})}


def clear_caches() -> None:
    for fn in (catalog, snapshot, summary, validation, readiness, overview_insights, market, financials, trends, evidence, valuation, trace, report, artifacts):
        fn.clear()
