"""Tests for deterministic M5 routing rules."""

from __future__ import annotations

from app.domain.enums import ProcessingStatus, RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.extraction import ContractExtractionResult
from app.services.decision_service import DecisionService


def _extraction(
    *,
    extraction_confidence: float = 0.9,
    key_missing_fields: list[str] | None = None,
) -> ContractExtractionResult:
    return ContractExtractionResult(
        vendor_name="Globex AI",
        contract_type="SaaS agreement",
        payment_terms="Net 60",
        liability_clause="Liability is uncapped.",
        termination_clause=None,
        renewal_clause=None,
        governing_law=None,
        data_usage_clause=None,
        key_missing_fields=key_missing_fields or [],
        extraction_confidence=extraction_confidence,
    )


def _classification(
    *,
    risk_level: RiskLevel,
    confidence: float,
    recommended_action: RoutingAction = RoutingAction.AUTO_STORE,
    policy_conflicts: list[str] | None = None,
) -> ClassificationResult:
    return ClassificationResult(
        risk_level=risk_level,
        policy_conflicts=policy_conflicts or [],
        recommended_action=recommended_action,
        rationale="Model rationale.",
        final_confidence=confidence,
    )


def test_high_risk_routes_to_legal_review_even_if_model_recommends_auto_store() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.HIGH, confidence=0.95),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.review_required is True
    assert outcome.final_action == RoutingAction.LEGAL_REVIEW


def test_medium_risk_routes_to_procurement_review() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.MEDIUM, confidence=0.9),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.PROCUREMENT_REVIEW


def test_high_risk_above_manual_threshold_routes_to_legal_review() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.HIGH, confidence=0.7),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.LEGAL_REVIEW


def test_low_confidence_overrides_low_risk_classification() -> None:
    outcome = DecisionService(confidence_threshold=0.75).build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.4),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "below" in (outcome.decision_reason or "")


def test_low_risk_requires_auto_store_confidence_threshold() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.79),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "auto-store threshold" in (outcome.decision_reason or "")


def test_low_risk_requires_sufficient_extraction_confidence() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(extraction_confidence=0.79),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.91),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "Extraction confidence" in (outcome.decision_reason or "")


def test_low_risk_requires_all_key_fields() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(key_missing_fields=["data_usage_clause"]),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.91),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "data_usage_clause" in (outcome.decision_reason or "")


def test_low_risk_requires_no_policy_conflicts() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(
            risk_level=RiskLevel.LOW,
            confidence=0.91,
            policy_conflicts=["Missing DPA."],
        ),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "Policy conflicts" in (outcome.decision_reason or "")


def test_low_risk_requires_retrieved_policy_context() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.91),
        retrieved_context_available=False,
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "No retrieved policy context" in (outcome.decision_reason or "")


def test_low_risk_high_confidence_routes_to_auto_store() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.91),
    )

    assert outcome.status == ProcessingStatus.COMPLETED
    assert outcome.review_required is False
    assert outcome.final_action == RoutingAction.AUTO_STORE


def test_missing_classification_routes_to_manual_review() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=None,
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.review_required is True
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW


def test_hard_failure_produces_failed_outcome() -> None:
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=None,
        errors=["retrieval timeout"],
        failed=True,
    )

    assert outcome.status == ProcessingStatus.FAILED
    assert outcome.review_required is True
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert outcome.errors == ["retrieval timeout"]
