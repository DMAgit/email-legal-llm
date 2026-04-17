"""Processing outcome models for persistence and review routing."""

from pydantic import BaseModel, Field

from app.domain.enums import ProcessingStatus
from app.domain.models.classification import ClassificationResult
from app.domain.models.extraction import ContractExtractionResult


class ProcessingOutcome(BaseModel):
    """Final state for a processing run after extraction and classification."""

    process_id: str
    status: ProcessingStatus
    extraction: ContractExtractionResult
    classification: ClassificationResult | None = None
    review_required: bool
    errors: list[str] = Field(default_factory=list)

