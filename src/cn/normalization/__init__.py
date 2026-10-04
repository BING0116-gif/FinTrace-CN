"""Provider-neutral financial normalization for A-share research."""

from .financial import (
    NormalizationError,
    NormalizedFact,
    derive_normalized_periods,
    normalize_statements,
    normalize_unit_value,
)

__all__ = [
    "NormalizationError", "NormalizedFact", "derive_normalized_periods",
    "normalize_statements", "normalize_unit_value",
]
