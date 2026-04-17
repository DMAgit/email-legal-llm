"""Tests for M3 structured extraction behavior."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.model_registry import ModelConfig, ModelRegistry
from app.domain.models.document import ParsedDocument
from app.domain.models.extraction import ContractExtractionResult
from app.infra.llm.openai_client import OpenAIClient
from app.main import app
from app.services.extraction_service import ExtractionError, ExtractionService


class FakeLLMClient:
    """Test double that captures structured-output requests."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create_structured_output(
        self,
        *,
        model_config: ModelConfig,
        system_prompt: str,
        user_content: str,
        schema_model: type[ContractExtractionResult],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "model_config": model_config,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "schema_model": schema_model,
            }
        )
        return self.response


class FakeOpenAICompletions:
    """OpenAI SDK-shaped test double for chat completions."""

    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def create(self, **request: Any) -> Any:
        self.request = request
        message = SimpleNamespace(
            content=(
                '{"vendor_name":"Acme Corp","contract_type":null,'
                '"payment_terms":"Net 60","liability_clause":null,'
                '"termination_clause":null,"renewal_clause":null,'
                '"governing_law":null,"data_usage_clause":null,'
                '"key_missing_fields":[],"extraction_confidence":0.9}'
            )
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _parsed_document(raw_text: str = "Vendor: Acme Corp\nPayment Terms: Net 60") -> ParsedDocument:
    return ParsedDocument(
        document_id="doc-1",
        filename="contract.csv",
        file_type="csv",
        parser_name="unstructured_partition_chunk_parser",
        raw_text=raw_text,
        extracted_tables=[
            {
                "index": 0,
                "text": "vendor amount Acme Legal 1200",
                "html": "<table><tr><td>vendor</td><td>amount</td></tr><tr><td>Acme Legal</td><td>1200</td></tr></table>",
            }
        ],
        confidence_hint=0.9,
    )


def test_extraction_service_validates_structured_llm_output() -> None:
    fake_client = FakeLLMClient(
        {
            "vendor_name": "Acme Corp",
            "contract_type": None,
            "payment_terms": "Net 60",
            "liability_clause": None,
            "termination_clause": None,
            "renewal_clause": None,
            "governing_law": None,
            "data_usage_clause": None,
            "key_missing_fields": ["contract_type", "liability_clause"],
            "extraction_confidence": 0.86,
        }
    )
    service = ExtractionService(
        model_registry=ModelRegistry.from_directory(Path("config/models")),
        prompt_dir=Path("app/infra/llm/prompts"),
        llm_client=fake_client,
    )

    result = service.extract_document(_parsed_document())

    assert result.vendor_name == "Acme Corp"
    assert result.payment_terms == "Net 60"
    assert result.extraction_confidence == 0.86
    call = fake_client.calls[0]
    assert call["model_config"].model == "gpt-4o-mini"
    assert call["schema_model"] is ContractExtractionResult
    assert "Do not guess" in call["system_prompt"]
    assert "standalone prices" in call["system_prompt"]
    assert "Acme Corp" in call["user_content"]
    assert "<table>" in call["user_content"]


def test_openai_client_requests_strict_json_schema() -> None:
    completions = FakeOpenAICompletions()
    fake_sdk_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    model_config = ModelRegistry.from_directory(Path("config/models")).get("extraction")
    client = OpenAIClient(api_key=None, client=fake_sdk_client)

    payload = client.create_structured_output(
        model_config=model_config,
        system_prompt="Extract fields.",
        user_content="Vendor: Acme Corp",
        schema_model=ContractExtractionResult,
    )

    assert payload["vendor_name"] == "Acme Corp"
    assert completions.request is not None
    assert completions.request["model"] == "gpt-4o-mini"
    response_format = completions.request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "extraction_confidence" in schema["required"]


def test_extraction_service_reports_schema_validation_errors() -> None:
    service = ExtractionService(
        model_registry=ModelRegistry.from_directory(Path("config/models")),
        prompt_dir=Path("app/infra/llm/prompts"),
        llm_client=FakeLLMClient(
            {
                "vendor_name": "Acme Corp",
                "key_missing_fields": [],
                "extraction_confidence": 1.5,
            }
        ),
    )

    with pytest.raises(ExtractionError, match="schema validation"):
        service.extract_document(_parsed_document())


def test_extraction_endpoint_requires_configured_openai_key(tmp_path: Path) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path,
        openai_api_key=None,
    )

    try:
        response = TestClient(app).post(
            "/extractions/contract",
            json=_parsed_document().model_dump(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_webhook_extract_flag_reports_missing_openai_key(tmp_path: Path) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        upload_dir=tmp_path,
        openai_api_key=None,
    )

    try:
        response = TestClient(app).post(
            "/webhooks/mailgun/inbound?extract=true",
            data={
                "sender": "legal@example.com",
                "recipient": "contracts@example.com",
                "subject": "Contract review",
                "body-plain": "Please review.",
            },
            files={
                "attachment-1": (
                    "contract.csv",
                    b"vendor,payment_terms\nAcme Corp,Net 60\n",
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    payload = response.json()
    assert response.status_code == 200
    assert payload["errors"] == []
    assert payload["extractions"] == []
    assert payload["extraction_errors"][0]["filename"] == "contract.csv"
    assert "OPENAI_API_KEY" in payload["extraction_errors"][0]["error"]
