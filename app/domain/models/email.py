"""Inbound email and attachment metadata models."""

from datetime import datetime

from pydantic import BaseModel, Field


class InboundEmail(BaseModel):
    """Normalized metadata for an inbound contract-related email."""

    message_id: str | None = None
    sender: str
    recipient: str
    subject: str
    plain_text_body: str | None = None
    attachment_count: int = Field(default=0, ge=0)
    received_at: datetime


class AttachmentMetadata(BaseModel):
    """Storage and source metadata for an inbound attachment."""

    filename: str
    content_type: str | None = None
    size_bytes: int = Field(ge=0)
    storage_path: str

