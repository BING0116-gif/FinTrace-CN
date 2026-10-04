"""ACME: deterministic accounting-constrained multimodal evidence checks."""

from .models import (
    ConstraintViolation,
    CrossModalInconsistency,
    IntegrityReport,
    TolerancePolicy,
)
from .validator import (
    check_accounting_identities,
    check_cross_modal,
    check_cross_period_continuity,
    check_cross_source,
    check_period_relations,
    check_table_structural,
    validate_multimodal_evidence,
)

__all__ = [
    "ConstraintViolation", "CrossModalInconsistency", "IntegrityReport",
    "TolerancePolicy", "check_accounting_identities", "check_cross_modal",
    "check_cross_period_continuity", "check_cross_source", "check_period_relations",
    "check_table_structural", "validate_multimodal_evidence",
]
