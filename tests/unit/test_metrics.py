"""Tests for in-process API and OpenAI metrics."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.core.metrics import MetricsCollector
from app.core.model_registry import ModelRegistry
from app.domain.models.extraction import ContractExtractionResult
from app.infra.llm.embedding_client import OpenAIEmbeddingClient
from app.infra.llm.openai_client import OpenAIClient
from app.main import create_app


class FakeOpenAICompletions:
    """OpenAI SDK-shaped test double for chat completions."""

    def __init__(self) -> None:
        self.content = (
            '{"vendor_name":"Acme Corp","contract_type":null,'
            '"payment_terms":"Net 60","liability_clause":null,'
            '"termination_clause":null,"renewal_clause":null,'
            '"governing_law":null,"data_usage_clause":null,'
            '"key_missing_fields":[],"extraction_confidence":0.9}'
        )

    def create(self, **_request: Any) -> Any:
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(
                prompt_tokens=23,
                completion_tokens=11,
                total_tokens=34,
            ),
        )


class FakeOpenAIEmbeddings:
    """OpenAI SDK-shaped test double for embeddings."""

    def create(self, **request: Any) -> Any:
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[0.1, 0.2, 0.3])
                for _text in request["input"]
            ],
            usage={"prompt_tokens": 7, "total_tokens": 7},
        )


def test_metrics_endpoint_reports_http_metrics() -> None:
    test_app = create_app()
    client = TestClient(test_app)

    health_response = client.get("/health")
    metrics_response = client.get("/metrics")

    assert health_response.status_code == 200
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["status"] == "ok"
    assert payload["http"]["requests_total"] >= 1
    assert payload["http"]["by_route"]["GET /health"]["requests_total"] == 1
    assert payload["openai"]["total"]["calls_total"] == 0


def test_openai_chat_metrics_track_payload_size_and_tokens() -> None:
    metrics = MetricsCollector()
    completions = FakeOpenAICompletions()
    fake_sdk_client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    model_config = ModelRegistry.from_directory(Path("config/models")).get("extraction")
    client = OpenAIClient(
        api_key=None,
        client=fake_sdk_client,
        metrics_collector=metrics,
    )

    client.create_structured_output(
        model_config=model_config,
        system_prompt="Extract fields.",
        user_content="Vendor: Acme Corp",
        schema_model=ContractExtractionResult,
    )

    payload = metrics.snapshot()["openai"]
    total = payload["total"]
    assert total["calls_total"] == 1
    assert total["calls_succeeded"] == 1
    assert total["input_items_total"] == 2
    assert total["input_text_chars_total"] == len("Extract fields.") + len("Vendor: Acme Corp")
    assert total["request_payload_chars_total"] > total["input_text_chars_total"]
    assert total["response_text_chars_total"] == len(completions.content)
    assert total["prompt_tokens_total"] == 23
    assert total["completion_tokens_total"] == 11
    assert total["total_tokens_total"] == 34
    assert payload["by_operation"]["chat.completions"]["calls_total"] == 1
    assert payload["by_model"]["gpt-4o-mini"]["calls_total"] == 1


def test_openai_embedding_metrics_track_input_volume() -> None:
    metrics = MetricsCollector()
    fake_sdk_client = SimpleNamespace(embeddings=FakeOpenAIEmbeddings())
    client = OpenAIEmbeddingClient(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=3,
        client=fake_sdk_client,
        metrics_collector=metrics,
    )

    vectors = client.embed_texts([" first ", "", "second"])

    assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    payload = metrics.snapshot()["openai"]
    total = payload["total"]
    assert total["calls_total"] == 1
    assert total["calls_succeeded"] == 1
    assert total["input_items_total"] == 2
    assert total["input_text_chars_total"] == len("first") + len("second")
    assert total["prompt_tokens_total"] == 7
    assert total["total_tokens_total"] == 7
    assert payload["by_operation"]["embeddings.create"]["calls_total"] == 1
    assert payload["by_model"]["text-embedding-3-small"]["calls_total"] == 1
