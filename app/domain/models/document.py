"""Parsed document domain models."""

from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    """Normalized text and tables from a source attachment parser."""

    document_id: str
    filename: str
    file_type: str
    parser_name: str
    raw_text: str
    extracted_tables: list[dict] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    confidence_hint: float | None = Field(default=None, ge=0.0, le=1.0)


class DocumentParseError(BaseModel):
    """Non-fatal parser error for a single attachment."""

    filename: str
    file_type: str | None = None
    parser_name: str | None = None
    error: str
