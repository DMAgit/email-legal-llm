"""Tests for vector indexing and Azure Search vector queries."""

from __future__ import annotations

from typing import Any

from app.infra.search.azure_search_client import AzureSearchClient
from app.core.exceptions import SearchClientError
from scripts.seed_search_index import VECTOR_FIELD_NAME, _upload_documents, embed_documents

import pytest


class FakeEmbeddingClient:
    """Embedding test double with deterministic vectors."""

    def __init__(self) -> None:
        self.text_batches: list[list[str]] = []
        self.queries: list[str] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.text_batches.append(texts)
        return [[float(index), 0.1, 0.2] for index, _text in enumerate(texts)]

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.4, 0.5, 0.6]


class FakeAzureSearchSDKClient:
    """Azure Search SDK-shaped test double."""

    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def search(self, **request: Any) -> list[dict[str, Any]]:
        self.request = request
        return [
            {
                "id": "liability-policy",
                "content": "Unlimited liability requires legal review.",
                "doc_type": "policy",
                "clause_type": "liability",
                "source": "contract_review_policy.md",
                "@search.score": 2.4,
            }
        ]


class FakeUploadClient:
    """Azure Search upload-shaped test double."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def upload_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.results


def test_seed_documents_are_embedded_before_upload() -> None:
    embedding_client = FakeEmbeddingClient()
    documents = [
        {
            "id": "policy-1",
            "content": "Unlimited liability requires legal review.",
            "doc_type": "policy",
            "clause_type": "liability",
            "source": "policy.md",
            "label": "Liability",
            "risk_level": "high",
        }
    ]

    embedded = embed_documents(documents, embedding_client)

    assert embedded[0][VECTOR_FIELD_NAME] == [0.0, 0.1, 0.2]
    assert "Clause: liability" in embedding_client.text_batches[0][0]
    assert "Unlimited liability requires legal review." in embedding_client.text_batches[0][0]


def test_azure_search_client_sends_vector_query() -> None:
    sdk_client = FakeAzureSearchSDKClient()
    embedding_client = FakeEmbeddingClient()
    client = AzureSearchClient(
        endpoint=None,
        api_key=None,
        index_name="contract-kb",
        embedding_client=embedding_client,
        client=sdk_client,
    )

    results = client.search(query="uncapped liability", top=3, clause_type="liability")

    assert results[0]["chunk_id"] == "liability-policy"
    assert embedding_client.queries == ["uncapped liability"]
    assert sdk_client.request is not None
    assert sdk_client.request["search_text"] == "uncapped liability"
    assert sdk_client.request["filter"] == "clause_type eq 'liability'"
    assert sdk_client.request["vector_queries"]
    vector_query = sdk_client.request["vector_queries"][0]
    if isinstance(vector_query, dict):
        assert vector_query["vector"] == [0.4, 0.5, 0.6]
        assert vector_query["fields"] == VECTOR_FIELD_NAME


def test_upload_documents_counts_successful_indexing_results() -> None:
    client = FakeUploadClient(
        [
            {"key": "doc-1", "succeeded": True, "status_code": 200},
            {"key": "doc-2", "succeeded": True, "status_code": 201},
        ]
    )

    assert _upload_documents(client, [{"id": "doc-1"}, {"id": "doc-2"}]) == 2


def test_upload_documents_raises_when_azure_rejects_documents() -> None:
    client = FakeUploadClient(
        [
            {
                "key": "doc-1",
                "succeeded": False,
                "status_code": 400,
                "error_message": "Vector field has the wrong dimensions.",
            }
        ]
    )

    with pytest.raises(SearchClientError, match="wrong dimensions"):
        _upload_documents(client, [{"id": "doc-1"}])
