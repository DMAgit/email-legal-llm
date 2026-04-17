"""Webhook ingestion response models."""

from pydantic import BaseModel, Field

from app.domain.models.document import DocumentParseError, ParsedDocument
from app.domain.models.email import InboundEmail
from app.domain.models.extraction import DocumentExtraction, DocumentExtractionError


class AttachmentProcessingSummary(BaseModel):
    """Public attachment metadata returned from webhook processing."""

    filename: str
    content_type: str | None = None
    size_bytes: int = Field(ge=0)


class InboundEmailProcessingResult(BaseModel):
    """Result returned after storing and parsing inbound email attachments."""

    process_id: str
    email: InboundEmail
    attachments: list[AttachmentProcessingSummary] = Field(default_factory=list)
    documents: list[ParsedDocument] = Field(default_factory=list)
    extractions: list[DocumentExtraction] = Field(default_factory=list)
    extraction_errors: list[DocumentExtractionError] = Field(default_factory=list)
    errors: list[DocumentParseError] = Field(default_factory=list)
