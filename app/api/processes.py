"""Process status and review queue endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import PersistenceRepositoryDep
from app.core.exceptions import PersistenceError
from app.domain.enums import ReviewQueueStatus
from app.domain.models.document import ParsedDocument
from app.domain.models.persistence import (
    ProcessAttachmentSummary,
    ProcessDocumentSummary,
    ProcessErrorSummary,
    ProcessRecord,
    ProcessStatusResponse,
    ReviewQueueItem,
)

router = APIRouter(tags=["processes"])
DOCUMENT_EXCERPT_CHARS = 320


@router.get("/processes/{process_id}", response_model=ProcessStatusResponse)
def get_process(
    process_id: str,
    repository: PersistenceRepositoryDep,
) -> ProcessStatusResponse:
    """Return persisted status and bounded traceability artifacts for one process."""
    try:
        record = repository.get_process(process_id)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process not found: {process_id}.",
        )
    return _process_status_response(record)


@router.get("/reviews", response_model=list[ReviewQueueItem])
def list_reviews(
    repository: PersistenceRepositoryDep,
    review_status: ReviewQueueStatus | None = Query(default=ReviewQueueStatus.OPEN),
) -> list[ReviewQueueItem]:
    """Return review queue items for demo visibility."""
    try:
        return repository.list_review_queue(status=review_status)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


def _process_status_response(record: ProcessRecord) -> ProcessStatusResponse:
    errors = []
    if record.error_message:
        errors.append(
            ProcessErrorSummary(
                error_type=record.error_type,
                message=record.error_message,
                stage=record.current_stage,
            )
        )

    return ProcessStatusResponse(
        process_id=record.process_id,
        status=record.status,
        current_stage=record.current_stage,
        created_at=record.created_at,
        updated_at=record.updated_at,
        final_action=record.final_action,
        review_required=record.review_required,
        decision_reason=record.decision_reason,
        errors=errors,
        email=record.email,
        attachments=[
            ProcessAttachmentSummary(
                filename=attachment.filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
            )
            for attachment in record.attachments
        ],
        documents=[_document_summary(document) for document in record.documents],
        extractions=record.extractions,
        extraction_summary=record.extractions,
        retrieved_contexts=record.retrieved_contexts,
        classification=record.classification,
        classification_summary=record.classification,
        document_evaluations=record.document_evaluations,
        review_queue=record.review_queue,
    )


def _document_summary(document: ParsedDocument) -> ProcessDocumentSummary:
    raw_text = document.raw_text.strip()
    return ProcessDocumentSummary(
        document_id=document.document_id,
        filename=document.filename,
        file_type=document.file_type,
        parser_name=document.parser_name,
        raw_text_excerpt=_truncate(raw_text, DOCUMENT_EXCERPT_CHARS),
        raw_text_length=len(document.raw_text),
        extracted_tables_count=len(document.extracted_tables),
        parse_warnings=document.parse_warnings,
        confidence_hint=document.confidence_hint,
    )


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."
