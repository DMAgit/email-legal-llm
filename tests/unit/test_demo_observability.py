"""Tests for M6 demo observability behavior."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.domain.enums import ProcessingStage, RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.document import ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult, DocumentExtraction
from app.infra.db.repository import PersistenceRepository
from app.main import app
from app.services.decision_service import DecisionService
from app.services.persistence_service import PersistenceService


def _db_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _email() -> InboundEmail:
    return InboundEmail(
        message_id="demo-message",
        sender="legal@example.com",
        recipient="contracts@example.com",
        subject="Demo contract",
        plain_text_body="Please review the attached contract.",
        attachment_count=1,
        received_at=datetime.now(UTC),
    )


def _attachment(tmp_path: Path) -> AttachmentMetadata:
    path = tmp_path / "demo.csv"
    path.write_text("field,value\nvendor_name,Acme Corp\n", encoding="utf-8")
    return AttachmentMetadata(
        filename="demo.csv",
        content_type="text/csv",
        size_bytes=path.stat().st_size,
        storage_path=str(path),
    )


def _document(raw_text: str) -> ParsedDocument:
    return ParsedDocument(
        document_id="demo-doc",
        filename="demo.csv",
        file_type="csv",
        parser_name="unstructured_partition_parser",
        raw_text=raw_text,
        extracted_tables=[{"index": 0, "text": "vendor_name,Acme Corp"}],
        parse_warnings=[],
        confidence_hint=0.95,
    )


def _extraction() -> ContractExtractionResult:
    return ContractExtractionResult(
        vendor_name="Acme Corp",
        contract_type="SaaS agreement",
        payment_terms="Net 30",
        liability_clause="Liability is capped at fees paid.",
        termination_clause="Either party may terminate for breach.",
        renewal_clause="No automatic renewal.",
        governing_law="New York",
        data_usage_clause="Data may be used only to provide the service.",
        key_missing_fields=[],
        extraction_confidence=0.94,
    )


def _classification(
    risk_level: RiskLevel = RiskLevel.LOW,
    action: RoutingAction = RoutingAction.AUTO_STORE,
) -> ClassificationResult:
    return ClassificationResult(
        risk_level=risk_level,
        policy_conflicts=[],
        recommended_action=action,
        rationale="Terms align with policy.",
        final_confidence=0.92,
    )


def test_process_status_endpoint_returns_bounded_document_summary(tmp_path: Path) -> None:
    database_url = _db_url(tmp_path / "app.db")
    repository = PersistenceRepository(database_url)
    service = PersistenceService(repository)
    raw_text = "Vendor: Acme Corp\n" + ("standard terms " * 80)
    document = _document(raw_text)
    extraction = _extraction()
    classification = _classification()
    outcome = DecisionService().build_outcome(
        process_id="demo-process",
        extraction=extraction,
        classification=classification,
    )

    try:
        service.save_processing_result(
            process_id="demo-process",
            email=_email(),
            attachments=[_attachment(tmp_path)],
            documents=[document],
            extractions=[
                DocumentExtraction(
                    document_id=document.document_id,
                    filename=document.filename,
                    extraction=extraction,
                )
            ],
            classification=classification,
            outcome=outcome,
        )
    finally:
        repository.close()

    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path / "uploads",
        database_url=database_url,
        mailgun_webhook_secret="",
    )
    try:
        response = TestClient(app).get("/processes/demo-process")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    document_summary = payload["documents"][0]
    assert payload["classification_summary"]["risk_level"] == RiskLevel.LOW.value
    assert payload["current_stage"] == ProcessingStage.PERSISTENCE_COMPLETED.value
    assert "raw_text" not in document_summary
    assert document_summary["raw_text_length"] == len(raw_text)
    assert len(document_summary["raw_text_excerpt"]) <= 320
    assert document_summary["extracted_tables_count"] == 1


def test_reviews_endpoint_includes_risk_level_when_known(tmp_path: Path) -> None:
    database_url = _db_url(tmp_path / "app.db")
    repository = PersistenceRepository(database_url)
    service = PersistenceService(repository)
    document = _document("Vendor: Acme Corp\nPayment terms: Net 60")
    extraction = _extraction()
    classification = _classification(
        risk_level=RiskLevel.MEDIUM,
        action=RoutingAction.PROCUREMENT_REVIEW,
    )
    outcome = DecisionService().build_outcome(
        process_id="review-process",
        extraction=extraction,
        classification=classification,
    )

    try:
        service.save_processing_result(
            process_id="review-process",
            email=_email(),
            documents=[document],
            extractions=[
                DocumentExtraction(
                    document_id=document.document_id,
                    filename=document.filename,
                    extraction=extraction,
                )
            ],
            classification=classification,
            outcome=outcome,
        )
    finally:
        repository.close()

    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path / "uploads",
        database_url=database_url,
        mailgun_webhook_secret="",
    )
    try:
        response = TestClient(app).get("/reviews")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["process_id"] == "review-process"
    assert payload[0]["review_type"] == RoutingAction.PROCUREMENT_REVIEW.value
    assert payload[0]["risk_level"] == RiskLevel.MEDIUM.value


def test_webhook_logs_observable_stages(caplog, tmp_path: Path) -> None:
    database_url = _db_url(tmp_path / "app.db")
    caplog.set_level(logging.INFO)
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path / "uploads",
        database_url=database_url,
        mailgun_webhook_secret="",
    )

    try:
        response = TestClient(app).post(
            "/webhooks/mailgun/inbound",
            data={
                "sender": "legal@example.com",
                "recipient": "contracts@example.com",
                "subject": "Contract review",
                "body-plain": "Please review.",
            },
            files={
                "attachment-1": (
                    "contract.csv",
                    b"field,value\nvendor_name,Acme Corp\n",
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    process_id = response.json()["process_id"]
    stages = {
        getattr(record, "stage", None)
        for record in caplog.records
        if getattr(record, "process_id", None) == process_id
    }
    assert ProcessingStage.EMAIL_RECEIVED.value in stages
    assert ProcessingStage.ATTACHMENT_SAVED.value in stages
    assert ProcessingStage.PARSE_STARTED.value in stages
    assert ProcessingStage.PARSE_COMPLETED.value in stages
    assert ProcessingStage.PERSISTENCE_COMPLETED.value in stages
