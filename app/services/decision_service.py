"""Deterministic routing for extracted and classified contracts."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.enums import ProcessingStatus, RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.persistence import ProcessingOutcome

DEFAULT_CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.75


class DecisionService:
    """Apply application-owned routing rules on top of model outputs."""

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CLASSIFICATION_CONFIDENCE_THRESHOLD,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0.")
        self.confidence_threshold = confidence_threshold

    def build_outcome(
        self,
        *,
        process_id: str,
        extraction: ContractExtractionResult,
        classification: ClassificationResult | None,
        errors: Sequence[str] | None = None,
        failed: bool = False,
    ) -> ProcessingOutcome:
        """Return the final deterministic outcome for a processing run."""
        normalized_errors = [error for error in (errors or []) if error]

        if failed:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FAILED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason="Processing failed before deterministic routing could complete.",
                errors=normalized_errors,
            )

        if classification is None:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=None,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason="Classification was not available, so manual review is required.",
                errors=normalized_errors,
            )

        if classification.final_confidence < self.confidence_threshold:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason=(
                    f"Classification confidence {classification.final_confidence:.2f} is below "
                    f"the {self.confidence_threshold:.2f} routing threshold."
                ),
                errors=normalized_errors,
            )

        if classification.risk_level == RiskLevel.HIGH:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.LEGAL_REVIEW,
                decision_reason="High risk classification requires legal review.",
                errors=normalized_errors,
            )

        if classification.risk_level == RiskLevel.MEDIUM:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.PROCUREMENT_REVIEW,
                decision_reason="Medium risk classification requires procurement review.",
                errors=normalized_errors,
            )

        return ProcessingOutcome(
            process_id=process_id,
            status=ProcessingStatus.COMPLETED,
            extraction=extraction,
            classification=classification,
            review_required=False,
            final_action=RoutingAction.AUTO_STORE,
            decision_reason="Low risk classification met the routing confidence threshold.",
            errors=normalized_errors,
        )
