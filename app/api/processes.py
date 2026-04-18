"""Process status and review queue endpoints."""

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import PersistenceRepositoryDep
from app.core.exceptions import PersistenceError
from app.domain.enums import ReviewQueueStatus
from app.domain.models.persistence import ProcessRecord, ReviewQueueItem

router = APIRouter(tags=["processes"])


@router.get("/processes/{process_id}", response_model=ProcessRecord)
def get_process(
    process_id: str,
    repository: PersistenceRepositoryDep,
) -> ProcessRecord:
    """Return persisted status and traceability artifacts for one process."""
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
    return record


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
