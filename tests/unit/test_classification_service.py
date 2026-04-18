"""Tests for M4 risk classification behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.core.model_registry import ModelConfig, ModelRegistry
from app.domain.enums import RiskLevel, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.retrieval import RetrievedContextChunk, RetrievalResult
from app.infra.llm.openai_client import _strict_json_schema
from app.services.classification_service import ClassificationError, ClassificationService


class FakeLLMClient:
    """Test double that captures structured classification requests."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create_structured_output(
        self,
        *,
        model_config: ModelConfig,
        system_prompt: str,
        user_content: str,
        schema_model: type[ClassificationResult],
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


def _extraction() -> ContractExtractionResult:
    return ContractExtractionResult(
        vendor_name="Globex AI",
        contract_type="SaaS agreement",
        payment_terms="Net 60",
        liability_clause="Customer has unlimited liability for all damages.",
        termination_clause=None,
        renewal_clause=None,
        governing_law=None,
        data_usage_clause="Vendor may train AI models on customer data.",
        key_missing_fields=[],
        extraction_confidence=0.84,
    )


def _retrieved_chunk() -> RetrievedContextChunk:
    return RetrievedContextChunk(
        chunk_id="data-policy",
        source="contract_review_policy.md",
        doc_type="policy",
        clause_type="data_usage",
        content="Training AI models on customer data is prohibited unless legal approves.",
        score=4.5,
    )


def test_classification_service_validates_structured_llm_output() -> None:
    fake_client = FakeLLMClient(
        {
            "risk_level": "high",
            "policy_conflicts": [
                {
                    "clause_type": "data_usage",
                    "issue": "AI training on customer data conflicts with policy.",
                }
            ],
            "recommended_action": "legal_review",
            "rationale": [
                "Data usage: retrieved policy prohibits AI training on customer data.",
                "Liability: customer has unlimited liability exposure.",
            ],
            "clause_evaluations": [
                {
                    "clause_type": "data_usage",
                    "risk": "high",
                    "reason": "Vendor may train AI models on customer data.",
                },
                {
                    "clause_type": "liability",
                    "risk": "high",
                    "reason": "Customer has unlimited liability for all damages.",
                },
            ],
            "final_confidence": 0.88,
        }
    )
    service = ClassificationService(
        model_registry=ModelRegistry.from_directory(Path("config/models")),
        prompt_dir=Path("app/infra/llm/prompts"),
        llm_client=fake_client,
    )

    result = service.classify(
        extraction=_extraction(),
        retrieved_chunks=[_retrieved_chunk()],
        retrieval_warnings=[],
    )

    assert result.risk_level == RiskLevel.HIGH
    assert result.recommended_action == RoutingAction.LEGAL_REVIEW
    assert result.policy_conflicts[0].clause_type == "data_usage"
    assert result.policy_conflicts[0].issue == "AI training on customer data conflicts with policy."
    assert result.rationale[0].startswith("Data usage")
    assert result.clause_evaluations["data_usage"].risk == RiskLevel.HIGH
    call = fake_client.calls[0]
    assert call["model_config"].name == "classification"
    assert call["schema_model"] is ClassificationResult
    assert "Do not invent policy conflicts" in call["system_prompt"]
    assert "Evaluate clause_inputs one clause at a time" in call["system_prompt"]
    assert "recommended_action is advisory" in call["user_content"]
    assert "clause_inputs" in call["user_content"]
    assert "clause_contexts" in call["user_content"]
    assert "Globex AI" in call["user_content"]
    assert "data-policy" in call["user_content"]


def test_classification_service_accepts_full_retrieval_result() -> None:
    fake_client = FakeLLMClient(
        {
            "risk_level": "medium",
            "policy_conflicts": [],
            "recommended_action": "manual_review",
            "rationale": ["No context was retrieved, so confidence is limited."],
            "clause_evaluations": [
                {
                    "clause_type": "payment_terms",
                    "risk": "medium",
                    "reason": "No retrieved payment policy context was available.",
                }
            ],
            "final_confidence": 0.42,
        }
    )
    service = ClassificationService(
        model_registry=ModelRegistry.from_directory(Path("config/models")),
        prompt_dir=Path("app/infra/llm/prompts"),
        llm_client=fake_client,
    )

    result = service.classify_retrieval_result(
        _extraction(),
        RetrievalResult(warnings=["No retrieved policy context was available for classification."]),
    )

    assert result.final_confidence == 0.42
    assert "No retrieved policy context" in fake_client.calls[0]["user_content"]


def test_malformed_classification_output_raises_typed_error() -> None:
    service = ClassificationService(
        model_registry=ModelRegistry.from_directory(Path("config/models")),
        prompt_dir=Path("app/infra/llm/prompts"),
        llm_client=FakeLLMClient(
            {
                "risk_level": "severe",
                "policy_conflicts": [],
                "recommended_action": "legal_review",
                "rationale": "Invalid risk level.",
                "clause_evaluations": {},
                "final_confidence": 1.5,
            }
        ),
    )

    with pytest.raises(ClassificationError, match="schema validation"):
        service.classify(_extraction(), [_retrieved_chunk()])


def test_classification_result_normalizes_legacy_explainability_shapes() -> None:
    result = ClassificationResult(
        risk_level=RiskLevel.LOW,
        policy_conflicts=["Missing DPA."],
        recommended_action=RoutingAction.MANUAL_REVIEW,
        rationale="Legacy single-string rationale.",
        final_confidence=0.8,
    )

    assert result.policy_conflicts[0].clause_type == "general"
    assert result.policy_conflicts[0].issue == "Missing DPA."
    assert result.rationale == ["Legacy single-string rationale."]


def test_classification_schema_uses_strict_friendly_clause_evaluation_items() -> None:
    schema = _strict_json_schema(ClassificationResult)

    assert schema["required"] == list(schema["properties"])
    clause_schema = schema["properties"]["clause_evaluations"]
    assert clause_schema["type"] == "array"
    assert clause_schema["items"] == {"$ref": "#/$defs/ClauseEvaluationItem"}
    assert "additionalProperties" not in clause_schema
    item_schema = schema["$defs"]["ClauseEvaluationItem"]
    assert item_schema["required"] == list(item_schema["properties"])
    assert item_schema["additionalProperties"] is False
