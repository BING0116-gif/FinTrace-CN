"""Document registration and page-level source fragments for FinTrace-CN.

The MVP deliberately stops at provenance-preserving extraction.  It does not
decide whether a candidate number is a financial fact; normalization and
validation own that decision in later stages.
"""

from .parser import DocumentParser, ParseResult
from .registry import DocumentRegistry
from .schema import DocumentRecord, ExtractedFact, SourceFragment
from .service import DocumentService

__all__ = [
    "DocumentParser", "DocumentRecord", "DocumentRegistry", "DocumentService",
    "ExtractedFact", "ParseResult", "SourceFragment",
]
