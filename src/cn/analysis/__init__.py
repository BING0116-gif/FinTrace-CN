"""Deterministic financial diagnostics over normalized A-share facts."""

from .financial import AnalysisResult, DiagnosticSignal, MetricResult, analyze_financials, compute_qoq, compute_single_quarter_qoq, compute_yoy, run_diagnostics
from .scope_signals import AccountingScopeSignal, ScopeSignalType, comparability_decision, detect_scope_signals, detection_coverage

__all__ = ["AccountingScopeSignal", "AnalysisResult", "DiagnosticSignal", "MetricResult", "ScopeSignalType", "analyze_financials", "comparability_decision", "compute_qoq", "compute_single_quarter_qoq", "compute_yoy", "detect_scope_signals", "detection_coverage", "run_diagnostics"]
