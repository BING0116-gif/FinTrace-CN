"""Local document registration with deterministic content identity."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import DocumentRecord


SUPPORTED_DOCUMENT_TYPES = {
    ".pdf": "annual_report",
    ".txt": "research_draft",
    ".md": "research_draft",
}
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


class DocumentRegistrationError(ValueError):
    """The document cannot safely enter the extraction pipeline."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DocumentRegistry:
    """Register local files without copying or mutating the source document."""

    def register(
        self,
        path: str | Path,
        *,
        document_type: Optional[str] = None,
        symbol: Optional[str] = None,
        fiscal_period: Optional[str] = None,
        published_at: Optional[str] = None,
        source: str = "user_upload",
    ) -> DocumentRecord:
        source_path = Path(path)
        if not source_path.is_file():
            raise DocumentRegistrationError("Document does not exist or is not a file.")
        suffix = source_path.suffix.lower()
        if suffix not in SUPPORTED_DOCUMENT_TYPES:
            raise DocumentRegistrationError("Unsupported document type; use PDF, TXT, or Markdown.")
        size = source_path.stat().st_size
        if size > MAX_DOCUMENT_BYTES:
            raise DocumentRegistrationError("Document exceeds the 50 MiB safety limit.")
        digest = sha256_file(source_path)
        resolved_type = document_type or SUPPORTED_DOCUMENT_TYPES[suffix]
        if not resolved_type.strip():
            raise DocumentRegistrationError("document_type must not be empty.")
        return DocumentRecord(
            document_id=f"doc_{digest[:20]}", file_name=source_path.name,
            document_type=resolved_type, sha256=digest, ingested_at=_now(),
            source=source, symbol=symbol, fiscal_period=fiscal_period,
            published_at=published_at,
        )
