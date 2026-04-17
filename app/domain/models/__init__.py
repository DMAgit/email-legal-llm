"""Pydantic domain models for emails, documents, and pipeline outcomes."""

from app.domain.models.classification import ClassificationResult
from app.domain.models.document import ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.persistence import ProcessingOutcome
from app.domain.models.retrieval import RetrievedContextChunk

__all__ = [
    "AttachmentMetadata",
    "ClassificationResult",
    "ContractExtractionResult",
    "InboundEmail",
    "ParsedDocument",
    "ProcessingOutcome",
    "RetrievedContextChunk",
]

