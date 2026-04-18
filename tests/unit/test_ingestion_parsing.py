"""Tests for M2 ingestion and parsing behavior."""

from __future__ import annotations

import asyncio
import hmac
import io
import time
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.datastructures import FormData, Headers, UploadFile

from app.core.config import Settings, get_settings
from app.domain.enums import RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.email import AttachmentMetadata
from app.domain.models.extraction import ContractExtractionResult, DocumentExtraction
from app.domain.models.retrieval import RetrievedContextChunk, RetrievalResult
from app.infra.db.repository import PersistenceRepository
from app.infra.parsers.exceptions import UnsupportedFileTypeError
from app.infra.parsers.parser_factory import ParserFactory
from app.infra.parsers.unstructured_parser import UnstructuredParser
from app.main import app
from app.services.ingestion_service import IngestionError, IngestionService
from app.services.parsing_service import ParsingService


def _mailgun_signature(secret: str, timestamp: str, token: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}{token}".encode("utf-8"),
        "sha256",
    ).hexdigest()


def test_parser_factory_selects_supported_types(tmp_path: Path) -> None:
    factory = ParserFactory.default()
    pdf_path = tmp_path / "contract.bin"
    csv_path = tmp_path / "contract.data"
    image_path = tmp_path / "contract.upload"
    unknown_path = tmp_path / "contract.unknown"

    pdf_path.write_bytes(b"%PDF-1.7\n")
    csv_path.write_text("vendor,value\nAcme,100\n", encoding="utf-8")
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    unknown_path.write_bytes(b"\x01\x02\x03")

    assert factory.detect_file_type(pdf_path) == "pdf"
    assert factory.detect_file_type(csv_path) == "csv"
    assert factory.detect_file_type(image_path) == "image"
    assert factory.detect_file_type(unknown_path, "application/pdf") == "pdf"

    try:
        factory.detect_file_type(unknown_path)
    except UnsupportedFileTypeError as exc:
        assert "Unsupported attachment type" in str(exc)
    else:
        raise AssertionError("Unsupported files should not get a parser.")


def test_unstructured_parser_returns_text_and_table_metadata(tmp_path: Path) -> None:
    csv_path = tmp_path / "contract.csv"
    csv_path.write_text("vendor,amount\nAcme Legal,1200\n", encoding="utf-8")
    metadata = AttachmentMetadata(
        filename="contract.csv",
        content_type="text/csv",
        size_bytes=csv_path.stat().st_size,
        storage_path=str(csv_path),
    )

    parsed = UnstructuredParser(file_type="csv").parse(csv_path, metadata)

    assert parsed.file_type == "csv"
    assert parsed.parser_name == "unstructured_partition_parser"
    assert "Acme Legal" in parsed.raw_text
    assert "<table>" in parsed.extracted_tables[0]["html"]


def test_unstructured_parser_uses_detected_type_for_generic_upload_mime(tmp_path: Path) -> None:
    csv_path = tmp_path / "contract.csv"
    csv_path.write_text("vendor,amount\nAcme Legal,1200\n", encoding="utf-8")
    metadata = AttachmentMetadata(
        filename="contract.csv",
        content_type="application/octet-stream",
        size_bytes=csv_path.stat().st_size,
        storage_path=str(csv_path),
    )

    parsed = UnstructuredParser(file_type="csv").parse(csv_path, metadata)

    assert parsed.file_type == "csv"
    assert "Acme Legal" in parsed.raw_text
    assert parsed.parse_warnings == []


def test_ingestion_service_persists_uploads(tmp_path: Path) -> None:
    form = FormData(
        [
            ("sender", "legal@example.com"),
            ("recipient", "contracts@example.com"),
            ("subject", "Contract review"),
            ("body-plain", "Please review."),
            ("attachment-count", "1"),
            (
                "attachment-1",
                UploadFile(
                    file=io.BytesIO(b"vendor,amount\nAcme,100\n"),
                    filename="../contract.csv",
                    headers=Headers({"content-type": "text/csv"}),
                ),
            ),
        ]
    )

    result = asyncio.run(IngestionService(tmp_path).ingest_mailgun_form(form))

    assert result.email.sender == "legal@example.com"
    assert result.email.attachment_count == 1
    assert result.attachments[0].filename == "contract.csv"
    assert Path(result.attachments[0].storage_path).read_text(encoding="utf-8") == "vendor,amount\nAcme,100\n"


def test_ingestion_service_validates_email_fields_before_writing_uploads(tmp_path: Path) -> None:
    form = FormData(
        [
            ("sender", "legal@example.com"),
            (
                "attachment-1",
                UploadFile(
                    file=io.BytesIO(b"vendor,amount\nAcme,100\n"),
                    filename="contract.csv",
                    headers=Headers({"content-type": "text/csv"}),
                ),
            ),
        ]
    )

    try:
        asyncio.run(IngestionService(tmp_path).ingest_mailgun_form(form))
    except IngestionError as exc:
        assert "recipient" in str(exc)
    else:
        raise AssertionError("Invalid Mailgun payloads should fail before upload persistence.")

    assert list(tmp_path.iterdir()) == []


def test_parsing_service_reports_unsupported_attachment(tmp_path: Path) -> None:
    text_path = tmp_path / "notes.txt"
    text_path.write_text("plain text only", encoding="utf-8")
    metadata = AttachmentMetadata(
        filename="notes.txt",
        content_type="text/plain",
        size_bytes=text_path.stat().st_size,
        storage_path=str(text_path),
    )

    documents, errors = ParsingService().parse_attachments([metadata])

    assert documents == []
    assert errors[0].filename == "notes.txt"
    assert "Unsupported attachment type" in errors[0].error
    assert "storage_path" not in errors[0].model_dump()


def test_mailgun_webhook_stores_and_parses_csv(tmp_path: Path) -> None:
    secret = "mailgun-test-secret"
    timestamp = str(int(time.time()))
    token = "test-token"
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path,
        mailgun_webhook_secret=secret,
    )

    try:
        response = TestClient(app).post(
            "/webhooks/mailgun/inbound",
            data={
                "sender": "legal@example.com",
                "recipient": "contracts@example.com",
                "subject": "Contract review",
                "body-plain": "Please review.",
                "timestamp": timestamp,
                "token": token,
                "signature": _mailgun_signature(secret, timestamp, token),
            },
            files={
                "attachment-1": (
                    "contract.csv",
                    b"vendor,amount\nAcme,100\n",
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["email"]["sender"] == "legal@example.com"
    assert payload["attachments"][0]["filename"] == "contract.csv"
    assert "storage_path" not in payload["attachments"][0]
    assert payload["documents"][0]["file_type"] == "csv"
    assert payload["documents"][0]["parser_name"] == "unstructured_partition_parser"
    assert "Acme" in payload["documents"][0]["raw_text"]
    assert "chunks" not in payload["documents"][0]
    assert payload["errors"] == []


def test_mailgun_webhook_rejects_invalid_signature_before_storage(tmp_path: Path) -> None:
    secret = "mailgun-test-secret"
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path,
        mailgun_webhook_secret=secret,
    )

    try:
        response = TestClient(app).post(
            "/webhooks/mailgun/inbound",
            data={
                "sender": "legal@example.com",
                "recipient": "contracts@example.com",
                "subject": "Contract review",
                "body-plain": "Please review.",
                "timestamp": str(int(time.time())),
                "token": "test-token",
                "signature": "not-a-valid-signature",
            },
            files={
                "attachment-1": (
                    "contract.csv",
                    b"vendor,amount\nAcme,100\n",
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert list(tmp_path.iterdir()) == []


def test_mailgun_webhook_error_response_omits_storage_path(tmp_path: Path) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path,
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
                    "notes.txt",
                    b"plain text only",
                    "text/plain",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert "storage_path" not in payload["attachments"][0]
    assert payload["errors"][0]["filename"] == "notes.txt"
    assert "storage_path" not in payload["errors"][0]


def test_mailgun_webhook_classifies_all_extracted_documents(monkeypatch, tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"

    class FakeOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeOpenAIEmbeddingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeAzureSearchClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

    class FakeExtractionService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def extract_documents(self, documents):
            extractions = []
            for index, document in enumerate(documents):
                vendor_name = "Safe Co" if index == 0 else "Risky Co"
                extractions.append(
                    DocumentExtraction(
                        document_id=document.document_id,
                        filename=document.filename,
                        extraction=ContractExtractionResult(
                            vendor_name=vendor_name,
                            contract_type="SaaS agreement",
                            payment_terms="Net 30",
                            liability_clause=(
                                "Liability is capped."
                                if vendor_name == "Safe Co"
                                else "Liability is uncapped."
                            ),
                            key_missing_fields=[],
                            extraction_confidence=0.95,
                        ),
                    )
                )
            return extractions, []

    class FakeRetrievalService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def retrieve_for_extraction(self, extraction):
            return RetrievalResult(
                chunks=[
                    RetrievedContextChunk(
                        chunk_id=f"{extraction.vendor_name}-policy",
                        source="policy.md",
                        doc_type="policy",
                        clause_type="liability",
                        content=f"Policy context for {extraction.vendor_name}.",
                        score=3.0,
                    )
                ]
            )

    class FakeClassificationService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def classify_retrieval_result(self, extraction, retrieval_result):
            if extraction.vendor_name == "Risky Co":
                return ClassificationResult(
                    risk_level=RiskLevel.HIGH,
                    policy_conflicts=["Uncapped liability."],
                    recommended_action=RoutingAction.LEGAL_REVIEW,
                    rationale="Uncapped liability requires legal review.",
                    final_confidence=0.95,
                )
            return ClassificationResult(
                risk_level=RiskLevel.LOW,
                policy_conflicts=[],
                recommended_action=RoutingAction.AUTO_STORE,
                rationale="Terms align with policy.",
                final_confidence=0.95,
            )

    monkeypatch.setattr("app.api.webhook.OpenAIClient", FakeOpenAIClient)
    monkeypatch.setattr("app.api.webhook.OpenAIEmbeddingClient", FakeOpenAIEmbeddingClient)
    monkeypatch.setattr("app.api.webhook.AzureSearchClient", FakeAzureSearchClient)
    monkeypatch.setattr("app.api.webhook.ExtractionService", FakeExtractionService)
    monkeypatch.setattr("app.api.webhook.RetrievalService", FakeRetrievalService)
    monkeypatch.setattr("app.api.webhook.ClassificationService", FakeClassificationService)

    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path / "uploads",
        database_url=database_url,
        mailgun_webhook_secret="",
    )
    try:
        response = TestClient(app).post(
            "/webhooks/mailgun/inbound?classify=true",
            data={
                "sender": "legal@example.com",
                "recipient": "contracts@example.com",
                "subject": "Contract review",
                "body-plain": "Please review.",
            },
            files=[
                (
                    "attachment-1",
                    (
                        "safe.csv",
                        b"vendor,liability\nSafe Co,capped\n",
                        "text/csv",
                    ),
                ),
                (
                    "attachment-2",
                    (
                        "risky.csv",
                        b"vendor,liability\nRisky Co,uncapped\n",
                        "text/csv",
                    ),
                ),
            ],
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"]["risk_level"] == RiskLevel.HIGH.value
    assert payload["outcome"]["final_action"] == RoutingAction.LEGAL_REVIEW.value
    assert len(payload["retrieved_contexts"]) == 2
    assert [item["filename"] for item in payload["document_evaluations"]] == [
        "safe.csv",
        "risky.csv",
    ]
    assert payload["document_evaluations"][0]["final_action"] == RoutingAction.AUTO_STORE.value
    assert payload["document_evaluations"][1]["final_action"] == RoutingAction.LEGAL_REVIEW.value
    assert payload["document_evaluations"][1]["classification"]["risk_level"] == RiskLevel.HIGH.value

    repository = PersistenceRepository(database_url)
    try:
        record = repository.get_process(payload["process_id"])
    finally:
        repository.close()

    assert record is not None
    assert len(record.retrieved_contexts) == 2
    assert len(record.document_evaluations) == 2
    assert record.document_evaluations[0].filename == "safe.csv"
    assert record.document_evaluations[1].final_action == RoutingAction.LEGAL_REVIEW
    assert record.review_queue[0].review_type == RoutingAction.LEGAL_REVIEW
