"""Parsed document domain models."""

from typing import Any

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    """Chunked document text ready for retrieval indexing."""

    chunk_id: str
    index: int = Field(ge=0)
    text: str
    element_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Normalized text, tables, and chunks from a source attachment parser."""

    document_id: str
    filename: str
    file_type: str
    parser_name: str
    raw_text: str
    chunks: list[DocumentChunk] = Field(default_factory=list)
    extracted_tables: list[dict] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    confidence_hint: float | None = Field(default=None, ge=0.0, le=1.0)


class DocumentParseError(BaseModel):
    """Non-fatal parser error for a single attachment."""

    filename: str
    file_type: str | None = None
    parser_name: str | None = None
    error: str
