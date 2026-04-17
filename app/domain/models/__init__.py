"""Pydantic domain models for emails, documents, and pipeline outcomes."""

from app.domain.models.classification import ClassificationResult
from app.domain.models.document import DocumentChunk, DocumentParseError, ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.ingestion import AttachmentProcessingSummary, InboundEmailProcessingResult
from app.domain.models.persistence import ProcessingOutcome
from app.domain.models.retrieval import RetrievedContextChunk

__all__ = [
    "AttachmentProcessingSummary",
    "AttachmentMetadata",
    "ClassificationResult",
    "ContractExtractionResult",
    "DocumentChunk",
    "DocumentParseError",
    "InboundEmail",
    "InboundEmailProcessingResult",
    "ParsedDocument",
    "ProcessingOutcome",
    "RetrievedContextChunk",
]
