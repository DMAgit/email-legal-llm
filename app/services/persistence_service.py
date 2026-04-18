"""Persistence coordination for processing workflow artifacts."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.enums import ProcessingStage, ProcessingStatus, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.document import DocumentParseError, ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import DocumentExtraction, DocumentExtractionError
from app.domain.models.persistence import ProcessingOutcome, ReviewQueueItem
from app.domain.models.retrieval import RetrievedContextChunk, RetrievalResult
from app.infra.db.repository import PersistenceRepository


class PersistenceService:
    """Coordinate repository writes for one processing run."""

    def __init__(self, repository: PersistenceRepository) -> None:
        self.repository = repository

    def save_received(
        self,
        *,
        process_id: str,
        email: InboundEmail,
        attachments: Sequence[AttachmentMetadata],
    ) -> None:
        """Persist the earliest known process state and inbound metadata."""
        self.repository.create_processing_run(process_id)
        self.repository.save_email(process_id, email)
        self.repository.save_attachments(process_id, attachments)

    def save_parsing_result(
        self,
        *,
        process_id: str,
        documents: Sequence[ParsedDocument],
        errors: Sequence[DocumentParseError] = (),
    ) -> None:
        """Persist parsed document artifacts and parser warning state."""
        self.repository.save_parsed_documents(process_id, documents)
        if errors and not documents:
            self.repository.record_failure(
                process_id,
                current_stage=ProcessingStage.PARSING.value,
                error_type="DocumentParseError",
                error_message=_join_errors(error.error for error in errors),
            )
        elif errors:
            self.repository.update_processing_run(
                process_id,
                status=ProcessingStage.PARSING.value,
                current_stage=ProcessingStage.PARSING.value,
                error_type="DocumentParseWarning",
                error_message=_join_errors(error.error for error in errors),
            )
        else:
            self.repository.update_processing_run(
                process_id,
                status=ProcessingStage.PARSING.value,
                current_stage=ProcessingStage.PARSING.value,
            )

    def save_extraction_result(
        self,
        *,
        process_id: str,
        extractions: Sequence[DocumentExtraction],
        errors: Sequence[DocumentExtractionError] = (),
    ) -> None:
        """Persist extraction artifacts and extraction failure state."""
        self.repository.save_extractions(process_id, extractions)
        if errors and not extractions:
            self.repository.record_failure(
                process_id,
                current_stage=ProcessingStage.EXTRACTING.value,
                error_type="DocumentExtractionError",
                error_message=_join_errors(error.error for error in errors),
            )
        elif errors:
            self.repository.update_processing_run(
                process_id,
                status=ProcessingStage.EXTRACTING.value,
                current_stage=ProcessingStage.EXTRACTING.value,
                error_type="DocumentExtractionWarning",
                error_message=_join_errors(error.error for error in errors),
            )
        else:
            self.repository.update_processing_run(
                process_id,
                status=ProcessingStage.EXTRACTING.value,
                current_stage=ProcessingStage.EXTRACTING.value,
            )

    def save_processing_result(
        self,
        *,
        process_id: str,
        email: InboundEmail | None = None,
        attachments: Sequence[AttachmentMetadata] = (),
        documents: Sequence[ParsedDocument] = (),
        extractions: Sequence[DocumentExtraction] = (),
        retrieved_contexts: Sequence[RetrievedContextChunk] | RetrievalResult = (),
        classification: ClassificationResult | None = None,
        outcome: ProcessingOutcome,
        document_id: str | None = None,
    ) -> ReviewQueueItem | None:
        """Persist all important artifacts and the final deterministic outcome."""
        self.repository.create_processing_run(process_id)
        if email is not None:
            self.repository.save_email(process_id, email)
        if attachments:
            self.repository.save_attachments(process_id, attachments)
        if documents:
            self.repository.save_parsed_documents(process_id, documents)
        if extractions:
            self.repository.save_extractions(process_id, extractions)

        resolved_document_id = document_id or _first_document_id(documents, extractions)
        contexts = _contexts(retrieved_contexts)
        if contexts and resolved_document_id:
            self.repository.save_retrieved_contexts(process_id, resolved_document_id, contexts)
        if classification is not None:
            self.repository.save_classification(process_id, classification)

        return self.save_outcome(process_id=process_id, outcome=outcome)

    def save_outcome(
        self,
        process_id: str,
        outcome: ProcessingOutcome,
    ) -> ReviewQueueItem | None:
        """Persist final outcome and create review queue entries when required."""
        self.repository.save_outcome(outcome)
        if not outcome.review_required:
            return None

        review_type = outcome.final_action or RoutingAction.MANUAL_REVIEW
        reason = outcome.decision_reason or _join_errors(outcome.errors) or "Manual review required."
        return self.repository.create_review_queue_item(
            process_id,
            review_type=review_type,
            reason=reason,
        )

    def save_failed_run(
        self,
        *,
        process_id: str,
        current_stage: str,
        error_type: str,
        error_message: str,
        create_review_item: bool = True,
    ) -> ReviewQueueItem | None:
        """Persist a failed run and optionally queue manual review."""
        self.repository.record_failure(
            process_id,
            current_stage=current_stage,
            error_type=error_type,
            error_message=error_message,
        )
        if not create_review_item:
            return None
        return self.repository.create_review_queue_item(
            process_id,
            review_type=RoutingAction.MANUAL_REVIEW,
            reason=error_message,
        )

    def mark_completed_without_decision(self, process_id: str, current_stage: str) -> None:
        """Mark partial workflows, such as parse-only demos, as completed."""
        self.repository.update_processing_run(
            process_id,
            status=ProcessingStatus.COMPLETED.value,
            current_stage=current_stage,
            review_required=False,
        )


def _contexts(
    retrieved_contexts: Sequence[RetrievedContextChunk] | RetrievalResult,
) -> Sequence[RetrievedContextChunk]:
    if isinstance(retrieved_contexts, RetrievalResult):
        return retrieved_contexts.chunks
    return retrieved_contexts


def _first_document_id(
    documents: Sequence[ParsedDocument],
    extractions: Sequence[DocumentExtraction],
) -> str | None:
    if extractions:
        return extractions[0].document_id
    if documents:
        return documents[0].document_id
    return None


def _join_errors(errors: Sequence[str] | object) -> str:
    return "; ".join(str(error) for error in errors if str(error))
