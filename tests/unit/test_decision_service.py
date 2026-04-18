"""Tests for deterministic M5 routing rules."""

from __future__ import annotations

from app.domain.enums import ProcessingStatus, RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.extraction import ContractExtractionResult
from app.services.decision_service import DecisionService


def _extraction() -> ContractExtractionResult:
    return ContractExtractionResult(
        vendor_name="Globex AI",
        contract_type="SaaS agreement",
        payment_terms="Net 60",
        liability_clause="Liability is uncapped.",
        termination_clause=None,
        renewal_clause=None,
        governing_law=None,
        data_usage_clause=None,
        key_missing_fields=[],
        extraction_confidence=0.9,
    )


def _classification(
    *,
    risk_level: RiskLevel,
    confidence: float,
    recommended_action: RoutingAction = RoutingAction.AUTO_STORE,
) -> ClassificationResult:
    return ClassificationResult(
        risk_level=risk_level,
        policy_conflicts=[],
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


def test_low_confidence_overrides_low_risk_classification() -> None:
    outcome = DecisionService(confidence_threshold=0.75).build_outcome(
        process_id="process-1",
        extraction=_extraction(),
        classification=_classification(risk_level=RiskLevel.LOW, confidence=0.4),
    )

    assert outcome.status == ProcessingStatus.FLAGGED
    assert outcome.final_action == RoutingAction.MANUAL_REVIEW
    assert "below" in (outcome.decision_reason or "")


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
