"""Pydantic domain models for emails, documents, and pipeline outcomes."""

from app.domain.models.classification import ClassificationResult
from app.domain.models.document import DocumentParseError, ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult, DocumentExtraction, DocumentExtractionError
from app.domain.models.ingestion import AttachmentProcessingSummary, InboundEmailProcessingResult
from app.domain.models.persistence import DocumentEvaluation, ProcessRecord, ProcessingOutcome, ReviewQueueItem
from app.domain.models.retrieval import RetrievedContextChunk, RetrievalResult

__all__ = [
    "AttachmentProcessingSummary",
    "AttachmentMetadata",
    "ClassificationResult",
    "ContractExtractionResult",
    "DocumentExtraction",
    "DocumentExtractionError",
    "DocumentEvaluation",
    "DocumentParseError",
    "InboundEmail",
    "InboundEmailProcessingResult",
    "ParsedDocument",
    "ProcessRecord",
    "ProcessingOutcome",
    "RetrievedContextChunk",
    "RetrievalResult",
    "ReviewQueueItem",
]
