"""Deterministic routing for extracted and classified contracts."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.enums import ProcessingStatus, RiskLevel, RoutingAction
from app.domain.models.classification import ClauseEvaluation, ClassificationResult, PolicyConflict
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.persistence import ProcessingOutcome

DEFAULT_CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.65
DEFAULT_AUTO_STORE_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_EXTRACTION_CONFIDENCE_THRESHOLD = 0.80


class DecisionService:
    """Apply application-owned routing rules on top of model outputs."""

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CLASSIFICATION_CONFIDENCE_THRESHOLD,
        auto_store_confidence_threshold: float = DEFAULT_AUTO_STORE_CONFIDENCE_THRESHOLD,
        extraction_confidence_threshold: float = DEFAULT_EXTRACTION_CONFIDENCE_THRESHOLD,
    ) -> None:
        if not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0.0 and 1.0.")
        if not 0.0 <= auto_store_confidence_threshold <= 1.0:
            raise ValueError("auto_store_confidence_threshold must be between 0.0 and 1.0.")
        if not 0.0 <= extraction_confidence_threshold <= 1.0:
            raise ValueError("extraction_confidence_threshold must be between 0.0 and 1.0.")
        self.confidence_threshold = confidence_threshold
        self.auto_store_confidence_threshold = auto_store_confidence_threshold
        self.extraction_confidence_threshold = extraction_confidence_threshold

    def build_outcome(
        self,
        *,
        process_id: str,
        extraction: ContractExtractionResult,
        classification: ClassificationResult | None,
        retrieved_context_available: bool = True,
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
                    f"the {self.confidence_threshold:.2f} manual review threshold."
                ),
                errors=normalized_errors,
            )

        highest_clause = _highest_clause_evaluation(classification)
        if highest_clause is not None and highest_clause[1].risk == RiskLevel.HIGH:
            clause_type, clause_evaluation = highest_clause
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.LEGAL_REVIEW,
                decision_reason=(
                    "High risk clause evaluation requires legal review: "
                    f"{_format_clause_evaluation(clause_type, clause_evaluation)}."
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

        if highest_clause is not None and highest_clause[1].risk == RiskLevel.MEDIUM:
            clause_type, clause_evaluation = highest_clause
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.PROCUREMENT_REVIEW,
                decision_reason=(
                    "Medium risk clause evaluation requires procurement review: "
                    f"{_format_clause_evaluation(clause_type, clause_evaluation)}."
                ),
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

        if not retrieved_context_available:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason="No retrieved policy context was available, so manual review is required.",
                errors=normalized_errors,
            )

        if extraction.extraction_confidence < self.extraction_confidence_threshold:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason=(
                    f"Extraction confidence {extraction.extraction_confidence:.2f} is below "
                    f"the {self.extraction_confidence_threshold:.2f} auto-store threshold."
                ),
                errors=normalized_errors,
            )

        if extraction.key_missing_fields:
            missing_fields = ", ".join(extraction.key_missing_fields)
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason=f"Required extracted fields are missing: {missing_fields}.",
                errors=normalized_errors,
            )

        if classification.policy_conflicts:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason=(
                    "Policy conflicts prevent auto-store: "
                    f"{_format_policy_conflicts(classification.policy_conflicts)}."
                ),
                errors=normalized_errors,
            )

        if normalized_errors:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason="Processing completed with warnings that require manual review.",
                errors=normalized_errors,
            )

        if classification.final_confidence < self.auto_store_confidence_threshold:
            return ProcessingOutcome(
                process_id=process_id,
                status=ProcessingStatus.FLAGGED,
                extraction=extraction,
                classification=classification,
                review_required=True,
                final_action=RoutingAction.MANUAL_REVIEW,
                decision_reason=(
                    f"Classification confidence {classification.final_confidence:.2f} is below "
                    f"the {self.auto_store_confidence_threshold:.2f} auto-store threshold."
                ),
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


def _highest_clause_evaluation(
    classification: ClassificationResult,
) -> tuple[str, ClauseEvaluation] | None:
    if not classification.clause_evaluations:
        return None

    risk_priority = {
        RiskLevel.LOW: 1,
        RiskLevel.MEDIUM: 2,
        RiskLevel.HIGH: 3,
    }
    return max(
        classification.clause_evaluations.items(),
        key=lambda item: risk_priority[item[1].risk],
    )


def _format_clause_evaluation(clause_type: str, evaluation: ClauseEvaluation) -> str:
    return f"{clause_type}: {evaluation.reason}"


def _format_policy_conflicts(conflicts: Sequence[PolicyConflict]) -> str:
    return "; ".join(f"{conflict.clause_type}: {conflict.issue}" for conflict in conflicts)
