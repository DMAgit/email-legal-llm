"""Shared parser contracts and helpers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Protocol

from app.domain.models.document import ParsedDocument
from app.domain.models.email import AttachmentMetadata


class DocumentParser(Protocol):
    """Contract implemented by all attachment parsers."""

    file_type: str
    parser_name: str

    def parse(self, path: Path, metadata: AttachmentMetadata) -> ParsedDocument:
        """Extract text and structured hints from a stored attachment."""


def document_id_for_path(path: Path) -> str:
    """Create a stable short document id from file bytes."""
    return sha256(path.read_bytes()).hexdigest()[:16]
