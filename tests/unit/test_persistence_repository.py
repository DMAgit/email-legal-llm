"""Tests for M5 SQLite persistence behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.domain.enums import ProcessingStage, ProcessingStatus, RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.document import DocumentParseError, ParsedDocument
from app.domain.models.email import AttachmentMetadata, InboundEmail
from app.domain.models.extraction import ContractExtractionResult, DocumentExtraction
from app.domain.models.persistence import DocumentEvaluation
from app.domain.models.retrieval import RetrievedContextChunk
from app.infra.db.repository import PersistenceRepository
from app.main import app
from app.services.decision_service import DecisionService
from app.services.persistence_service import PersistenceService


def _db_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _email() -> InboundEmail:
    return InboundEmail(
        message_id="message-1",
        sender="legal@example.com",
        recipient="contracts@example.com",
        subject="Review contract",
        plain_text_body="Please review.",
        attachment_count=1,
        received_at=datetime.now(UTC),
    )


def _attachment(tmp_path: Path) -> AttachmentMetadata:
    contract_path = tmp_path / "contract.csv"
    contract_path.write_text("vendor,payment_terms\nAcme Corp,Net 30\n", encoding="utf-8")
    return AttachmentMetadata(
        filename="contract.csv",
        content_type="text/csv",
        size_bytes=contract_path.stat().st_size,
        storage_path=str(contract_path),
    )


def _document() -> ParsedDocument:
    return ParsedDocument(
        document_id="doc-1",
        filename="contract.csv",
        file_type="csv",
        parser_name="unstructured_partition_parser",
        raw_text="Vendor: Acme Corp\nPayment terms: Net 30",
        extracted_tables=[],
        parse_warnings=[],
        confidence_hint=0.95,
    )


def _extraction() -> ContractExtractionResult:
    return ContractExtractionResult(
        vendor_name="Acme Corp",
        contract_type="MSA",
        payment_terms="Net 30",
        liability_clause="Liability is capped at fees paid.",
        termination_clause=None,
        renewal_clause=None,
        governing_law="New York",
        data_usage_clause=None,
        key_missing_fields=[],
        extraction_confidence=0.92,
    )


def _classification(
    risk_level: RiskLevel = RiskLevel.LOW,
    recommended_action: RoutingAction = RoutingAction.AUTO_STORE,
    confidence: float = 0.93,
) -> ClassificationResult:
    return ClassificationResult(
        risk_level=risk_level,
        policy_conflicts=[],
        recommended_action=recommended_action,
        rationale=["Payment terms: Net 30 aligns with policy."],
        clause_evaluations={
            "payment_terms": {
                "risk": "low",
                "reason": "Net 30 aligns with the payment policy.",
            }
        },
        final_confidence=confidence,
    )


def _context() -> RetrievedContextChunk:
    return RetrievedContextChunk(
        chunk_id="liability-policy",
        source="contract_review_policy.md",
        doc_type="policy",
        clause_type="liability",
        content="Liability capped at fees paid can be auto-stored for approved vendors.",
        score=3.4,
    )


def test_repository_saves_and_fetches_completed_run(tmp_path: Path) -> None:
    repository = PersistenceRepository(_db_url(tmp_path / "app.db"))
    service = PersistenceService(repository)
    document = _document()
    extraction = _extraction()
    classification = _classification()
    outcome = DecisionService().build_outcome(
        process_id="process-1",
        extraction=extraction,
        classification=classification,
    )

    try:
        service.save_processing_result(
            process_id="process-1",
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
            retrieved_contexts=[_context()],
            classification=classification,
            outcome=outcome,
            document_evaluations=[
                DocumentEvaluation(
                    process_id="process-1",
                    document_id=document.document_id,
                    filename=document.filename,
                    extraction=extraction,
                    retrieved_contexts=[_context()],
                    classification=classification,
                    status=outcome.status,
                    review_required=outcome.review_required,
                    final_action=outcome.final_action,
                    decision_reason=outcome.decision_reason,
                    errors=outcome.errors,
                )
            ],
        )

        record = repository.get_process("process-1")
    finally:
        repository.close()

    assert record is not None
    assert record.status == ProcessingStatus.COMPLETED.value
    assert record.email is not None
    assert record.email.sender == "legal@example.com"
    assert record.attachments[0].filename == "contract.csv"
    assert record.documents[0].raw_text.startswith("Vendor: Acme")
    assert record.extractions[0].extraction.vendor_name == "Acme Corp"
    assert record.retrieved_contexts[0].chunk_id == "liability-policy"
    assert record.classification is not None
    assert record.classification.risk_level == RiskLevel.LOW
    assert record.classification.rationale == ["Payment terms: Net 30 aligns with policy."]
    assert record.classification.clause_evaluations["payment_terms"].risk == RiskLevel.LOW
    assert record.document_evaluations[0].document_id == "doc-1"
    assert record.document_evaluations[0].filename == "contract.csv"
    assert record.document_evaluations[0].final_action == RoutingAction.AUTO_STORE
    assert record.document_evaluations[0].retrieved_contexts[0].chunk_id == "liability-policy"
    assert record.review_queue == []


def test_flagged_run_creates_review_queue_entry(tmp_path: Path) -> None:
    repository = PersistenceRepository(_db_url(tmp_path / "app.db"))
    service = PersistenceService(repository)
    document = _document()
    extraction = _extraction()
    classification = _classification(
        risk_level=RiskLevel.MEDIUM,
        recommended_action=RoutingAction.AUTO_STORE,
        confidence=0.9,
    )
    outcome = DecisionService().build_outcome(
        process_id="process-2",
        extraction=extraction,
        classification=classification,
    )

    try:
        service.save_processing_result(
            process_id="process-2",
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
        record = repository.get_process("process-2")
        review_items = repository.list_review_queue()
    finally:
        repository.close()

    assert record is not None
    assert record.status == ProcessingStatus.FLAGGED.value
    assert record.final_action == RoutingAction.PROCUREMENT_REVIEW
    assert record.review_required is True
    assert record.review_queue[0].review_type == RoutingAction.PROCUREMENT_REVIEW
    assert review_items[0].process_id == "process-2"


def test_failed_run_preserves_error_stage_and_message(tmp_path: Path) -> None:
    repository = PersistenceRepository(_db_url(tmp_path / "app.db"))
    service = PersistenceService(repository)

    try:
        repository.create_processing_run("process-3")
        service.save_failed_run(
            process_id="process-3",
            current_stage=ProcessingStage.RETRIEVING.value,
            error_type="RetrievalError",
            error_message="Search index unavailable.",
        )
        record = repository.get_process("process-3")
    finally:
        repository.close()

    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert record.current_stage == ProcessingStage.RETRIEVING.value
    assert record.error_type == "RetrievalError"
    assert record.error_message == "Search index unavailable."
    assert record.review_queue[0].review_type == RoutingAction.MANUAL_REVIEW


def test_parse_only_failure_creates_review_queue_entry(tmp_path: Path) -> None:
    repository = PersistenceRepository(_db_url(tmp_path / "app.db"))
    service = PersistenceService(repository)

    try:
        repository.create_processing_run("process-parse-error")
        service.save_parsing_result(
            process_id="process-parse-error",
            documents=[],
            errors=[
                DocumentParseError(
                    filename="notes.txt",
                    file_type=None,
                    parser_name=None,
                    error="Unsupported attachment type.",
                )
            ],
        )
        record = repository.get_process("process-parse-error")
        review_items = repository.list_review_queue()
    finally:
        repository.close()

    assert record is not None
    assert record.status == ProcessingStatus.FAILED.value
    assert record.review_required is True
    assert record.review_queue[0].reason == "Unsupported attachment type."
    assert review_items[0].process_id == "process-parse-error"


def test_failed_outcome_keeps_specific_review_reason(tmp_path: Path) -> None:
    repository = PersistenceRepository(_db_url(tmp_path / "app.db"))
    service = PersistenceService(repository)
    error_message = "Azure AI Search index not found: contract-kb."
    outcome = DecisionService().build_outcome(
        process_id="process-specific-error",
        extraction=_extraction(),
        classification=None,
        errors=[error_message],
        failed=True,
    )

    try:
        service.save_failed_run(
            process_id="process-specific-error",
            current_stage=ProcessingStage.RETRIEVING.value,
            error_type="SearchIndexNotFoundError",
            error_message=error_message,
        )
        service.save_outcome("process-specific-error", outcome)
        record = repository.get_process("process-specific-error")
    finally:
        repository.close()

    assert record is not None
    assert record.review_queue[0].reason == error_message


def test_process_status_endpoint_returns_persisted_record(tmp_path: Path) -> None:
    database_url = _db_url(tmp_path / "app.db")
    repository = PersistenceRepository(database_url)
    try:
        repository.create_processing_run("process-api")
        repository.update_processing_run(
            "process-api",
            status=ProcessingStatus.COMPLETED.value,
            current_stage=ProcessingStage.PARSING.value,
        )
    finally:
        repository.close()

    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path / "uploads",
        database_url=database_url,
    )
    try:
        response = TestClient(app).get("/processes/process-api")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["process_id"] == "process-api"
    assert payload["status"] == ProcessingStatus.COMPLETED.value
