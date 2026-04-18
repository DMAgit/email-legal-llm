"""Processing outcome models for persistence and review routing."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import ProcessingStatus, ReviewQueueStatus, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.document import ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult, DocumentExtraction
from app.domain.models.retrieval import RetrievedContextChunk


class ProcessingOutcome(BaseModel):
    """Final state for a processing run after extraction and classification."""

    process_id: str
    status: ProcessingStatus
    extraction: ContractExtractionResult
    classification: ClassificationResult | None = None
    review_required: bool
    final_action: RoutingAction | None = None
    decision_reason: str | None = None
    errors: list[str] = Field(default_factory=list)


class DocumentEvaluation(BaseModel):
    """Per-document classification and deterministic routing result."""

    process_id: str
    document_id: str
    filename: str
    extraction: ContractExtractionResult
    retrieved_contexts: list[RetrievedContextChunk] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    status: ProcessingStatus
    review_required: bool
    final_action: RoutingAction | None = None
    decision_reason: str | None = None
    errors: list[str] = Field(default_factory=list)


class ReviewQueueItem(BaseModel):
    """Persisted manual review queue item."""

    id: int
    process_id: str
    review_type: RoutingAction
    reason: str
    status: ReviewQueueStatus = ReviewQueueStatus.OPEN
    created_at: datetime
    updated_at: datetime


class ProcessRecord(BaseModel):
    """Auditable processing status and persisted artifacts for one process."""

    process_id: str
    status: str
    current_stage: str
    created_at: datetime
    updated_at: datetime
    error_type: str | None = None
    error_message: str | None = None
    final_action: RoutingAction | None = None
    review_required: bool = False
    decision_reason: str | None = None
    email: InboundEmail | None = None
    attachments: list[AttachmentMetadata] = Field(default_factory=list)
    documents: list[ParsedDocument] = Field(default_factory=list)
    extractions: list[DocumentExtraction] = Field(default_factory=list)
    retrieved_contexts: list[RetrievedContextChunk] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    document_evaluations: list[DocumentEvaluation] = Field(default_factory=list)
    review_queue: list[ReviewQueueItem] = Field(default_factory=list)
