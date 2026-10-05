"""Single source of truth for per-session workbench state."""

from __future__ import annotations

from typing import Any

import streamlit as st


DEFAULTS: dict[str, Any] = {
    "selected_snapshot_id": None,
    "selected_evidence_id": None,
    "selected_claim_id": None,
    "selected_document_id": None,
    "selected_run_id": None,
    "research_page": "overview",
    "task_step": 1,
    "task_uploaded_documents": [],
    "task_last_message": None,
    "report_draft": "",
}


def initialize(catalog: list[dict[str, Any]] | None = None) -> None:
    """Initialize user state once and reconcile a removed snapshot safely."""
    for key, value in DEFAULTS.items():
        st.session_state.setdefault(key, value.copy() if isinstance(value, list) else value)
    if catalog:
        ids = {item.get("id") for item in catalog}
        if st.session_state.selected_snapshot_id not in ids:
            st.session_state.selected_snapshot_id = catalog[0]["id"]


def selected_snapshot_id() -> str | None:
    return st.session_state.get("selected_snapshot_id")


def set_snapshot(snapshot_id: str) -> None:
    st.session_state.selected_snapshot_id = snapshot_id
    st.session_state.selected_evidence_id = None
    st.session_state.selected_claim_id = None


def go_to_evidence(evidence_id: str | None = None) -> None:
    if evidence_id:
        st.session_state.selected_evidence_id = evidence_id
    st.session_state.research_page = "documents"


def go_to_claim(claim_id: str) -> None:
    st.session_state.selected_claim_id = claim_id
    st.session_state.research_page = "report_checker"
