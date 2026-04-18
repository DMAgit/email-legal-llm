"""Tests for M4 clause-level retrieval behavior."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from app.core.exceptions import RetrievalError, SearchClientError
from app.domain.models.extraction import ContractExtractionResult
from app.services.retrieval_service import RetrievalService


class FakeSearchClient:
    """Search test double that captures retrieval calls."""

    def __init__(self, results: dict[str | None, list[Mapping[str, Any]]]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        *,
        query: str,
        top: int,
        clause_type: str | None = None,
        doc_type: str | None = None,
    ) -> list[Mapping[str, Any]]:
        self.calls.append(
            {
                "query": query,
                "top": top,
                "clause_type": clause_type,
                "doc_type": doc_type,
            }
        )
        return self.results.get(clause_type, [])


class FailingSearchClient:
    """Search test double that simulates an adapter failure."""

    def search(
        self,
        *,
        query: str,
        top: int,
        clause_type: str | None = None,
        doc_type: str | None = None,
    ) -> list[Mapping[str, Any]]:
        raise SearchClientError("index unavailable")


def _extraction(**overrides: Any) -> ContractExtractionResult:
    payload = {
        "vendor_name": None,
        "contract_type": None,
        "payment_terms": None,
        "liability_clause": None,
        "termination_clause": None,
        "renewal_clause": None,
        "governing_law": None,
        "data_usage_clause": None,
        "key_missing_fields": [],
        "extraction_confidence": 0.9,
    }
    payload.update(overrides)
    return ContractExtractionResult.model_validate(payload)


def test_retrieval_queries_only_non_empty_extracted_clauses() -> None:
    fake_client = FakeSearchClient(
        {
            "liability": [
                {
                    "id": "liability-policy",
                    "source": "contract_review_policy.md",
                    "doc_type": "policy",
                    "clause_type": "liability",
                    "content": "Unlimited liability requires legal review.",
                    "@search.score": 3.5,
                }
            ],
            "data_usage": [
                {
                    "id": "data-policy",
                    "source": "contract_review_policy.md",
                    "doc_type": "policy",
                    "clause_type": "data_usage",
                    "content": "AI training on customer data is prohibited.",
                    "score": 4.2,
                }
            ],
        }
    )
    service = RetrievalService(search_client=fake_client, top_results_per_clause=2)

    result = service.retrieve_for_extraction(
        _extraction(
            liability_clause="Vendor has unlimited liability.",
            data_usage_clause="Vendor may train models on customer data.",
            payment_terms="  ",
        )
    )

    assert [call["clause_type"] for call in fake_client.calls] == ["liability", "data_usage"]
    assert fake_client.calls[0]["top"] == 2
    assert result.warnings == []
    assert [chunk.chunk_id for chunk in result.chunks] == ["data-policy", "liability-policy"]


def test_retrieval_deduplicates_chunks_and_keeps_highest_score() -> None:
    fake_client = FakeSearchClient(
        {
            "liability": [
                {
                    "id": "shared-policy",
                    "source": "policy.md",
                    "doc_type": "policy",
                    "clause_type": "liability",
                    "content": "Liability must be capped.",
                    "score": 1.0,
                },
                {
                    "id": "shared-policy",
                    "source": "policy.md",
                    "doc_type": "policy",
                    "clause_type": "liability",
                    "content": "Liability must be capped.",
                    "score": 5.0,
                },
            ]
        }
    )

    result = RetrievalService(search_client=fake_client).retrieve_for_extraction(
        _extraction(liability_clause="Unlimited liability.")
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_id == "shared-policy"
    assert result.chunks[0].score == 5.0


def test_empty_retrieval_preserves_warnings() -> None:
    fake_client = FakeSearchClient({"liability": []})

    result = RetrievalService(search_client=fake_client).retrieve_for_extraction(
        _extraction(liability_clause="Vendor has uncapped liability.")
    )

    assert result.chunks == []
    assert "No policy context found for liability_clause." in result.warnings
    assert "No retrieved policy context was available for classification." in result.warnings


def test_search_adapter_failures_become_retrieval_errors() -> None:
    service = RetrievalService(search_client=FailingSearchClient())

    with pytest.raises(RetrievalError, match="liability_clause"):
        service.retrieve_for_extraction(_extraction(liability_clause="Unlimited liability."))
