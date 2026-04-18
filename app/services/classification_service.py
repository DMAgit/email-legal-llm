"""Risk classification service grounded by retrieved policy context."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, Sequence

from pydantic import ValidationError

from app.core.exceptions import ClassificationError, ConfigurationError
from app.core.model_registry import ModelConfig, ModelRegistry
from app.domain.models.classification import ClassificationResult
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.retrieval import RetrievedContextChunk, RetrievalResult
from app.infra.llm.openai_client import OpenAIClientError
from app.infra.llm.prompt_loader import PromptTemplate, PromptTemplateLoader

CLAUSE_FIELD_SPECS: tuple[tuple[str, str], ...] = (
    ("payment_terms", "payment_terms"),
    ("liability_clause", "liability"),
    ("data_usage_clause", "data_usage"),
    ("termination_clause", "termination"),
    ("renewal_clause", "renewal"),
    ("governing_law", "governing_law"),
    ("vendor_name", "vendor"),
    ("contract_type", "contract_type"),
)


class ClassificationLLMClient(Protocol):
    """Protocol for LLM clients that return schema-shaped classification JSON."""

    def create_structured_output(
        self,
        *,
        model_config: ModelConfig,
        system_prompt: str,
        user_content: str,
        schema_model: type[ClassificationResult],
    ) -> dict[str, Any]:
        """Return a JSON object generated under the supplied response schema."""


class ClassificationService:
    """Classify risk from extracted fields plus retrieved policy context."""

    def __init__(
        self,
        *,
        model_registry: ModelRegistry,
        prompt_dir: Path,
        llm_client: ClassificationLLMClient,
        config_name: str = "classification",
        max_context_chars: int = 6000,
        max_chunks: int = 10,
        max_chunk_chars: int = 1200,
    ) -> None:
        self.model_registry = model_registry
        self.prompt_dir = prompt_dir
        self.llm_client = llm_client
        self.config_name = config_name
        self.max_context_chars = max_context_chars
        self.max_chunks = max_chunks
        self.max_chunk_chars = max_chunk_chars

    def classify(
        self,
        extraction: ContractExtractionResult,
        retrieved_chunks: Sequence[RetrievedContextChunk],
        retrieval_warnings: Sequence[str] | None = None,
    ) -> ClassificationResult:
        """Return a validated risk classification without making final routing decisions."""
        model_config = self._model_config()
        prompt = self._load_prompt(model_config)
        classification_payload = self._classification_payload(
            extraction=extraction,
            retrieved_chunks=retrieved_chunks,
            retrieval_warnings=retrieval_warnings or [],
        )

        try:
            user_content = prompt.render_user(classification_payload=classification_payload)
        except ConfigurationError as exc:
            raise ClassificationError(str(exc)) from exc

        try:
            response = self.llm_client.create_structured_output(
                model_config=model_config,
                system_prompt=prompt.system,
                user_content=user_content,
                schema_model=ClassificationResult,
            )
        except OpenAIClientError as exc:
            raise ClassificationError(str(exc)) from exc

        try:
            return ClassificationResult.model_validate(response)
        except ValidationError as exc:
            raise ClassificationError(
                f"Classification response failed schema validation: {exc}"
            ) from exc

    def classify_retrieval_result(
        self,
        extraction: ContractExtractionResult,
        retrieval_result: RetrievalResult,
    ) -> ClassificationResult:
        """Classify using a full retrieval result with chunks and warnings."""
        return self.classify(
            extraction=extraction,
            retrieved_chunks=retrieval_result.chunks,
            retrieval_warnings=retrieval_result.warnings,
        )

    def _model_config(self) -> ModelConfig:
        try:
            config = self.model_registry.get(self.config_name)
        except KeyError as exc:
            raise ClassificationError(str(exc)) from exc
        if config.provider.lower() != "openai":
            raise ClassificationError(f"Unsupported classification provider: {config.provider}.")
        if config.response_schema != "ClassificationResult":
            raise ClassificationError(
                "Classification model config must declare response_schema=ClassificationResult."
            )
        return config

    def _load_prompt(self, model_config: ModelConfig) -> PromptTemplate:
        template_name = model_config.prompt_template or "classification_prompt_v1"
        try:
            return PromptTemplateLoader(self.prompt_dir).load(template_name)
        except ConfigurationError as exc:
            raise ClassificationError(str(exc)) from exc

    def _classification_payload(
        self,
        *,
        extraction: ContractExtractionResult,
        retrieved_chunks: Sequence[RetrievedContextChunk],
        retrieval_warnings: Sequence[str],
    ) -> str:
        bounded_context = self._bounded_context(retrieved_chunks)
        payload = {
            "extraction": extraction.model_dump(mode="json"),
            "clause_inputs": self._clause_inputs(extraction),
            "clause_contexts": self._clause_contexts(bounded_context),
            "retrieved_context": bounded_context,
            "retrieval_warnings": list(retrieval_warnings),
            "classification_contract": {
                "clause_evaluations": (
                    "Evaluate each clause_input independently using matching clause_contexts "
                    "before assigning the aggregate risk_level."
                ),
                "policy_conflicts": (
                    "Return structured conflicts only when retrieved policy context supports "
                    "a concrete mismatch."
                ),
                "rationale": (
                    "Return a list of evidence-based reasons, not a generic summary."
                ),
            },
            "routing_scope": (
                "recommended_action is advisory. Final workflow routing and persistence "
                "are applied later by deterministic application logic."
            ),
        }
        return json.dumps(payload, ensure_ascii=True)

    def _clause_inputs(self, extraction: ContractExtractionResult) -> dict[str, dict[str, str]]:
        clause_inputs: dict[str, dict[str, str]] = {}
        for field_name, clause_type in CLAUSE_FIELD_SPECS:
            value = _clean_string(getattr(extraction, field_name, None))
            if value:
                clause_inputs[clause_type] = {
                    "field_name": field_name,
                    "text": value,
                }
        return clause_inputs

    def _clause_contexts(
        self,
        bounded_context: Sequence[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        clause_contexts: dict[str, list[dict[str, Any]]] = {}
        for chunk in bounded_context:
            clause_type = _clean_string(chunk.get("clause_type")) or "general"
            clause_contexts.setdefault(clause_type, []).append(dict(chunk))
        return clause_contexts

    def _bounded_context(
        self,
        retrieved_chunks: Sequence[RetrievedContextChunk],
    ) -> list[dict[str, Any]]:
        bounded_chunks: list[dict[str, Any]] = []
        remaining_chars = self.max_context_chars
        for chunk in retrieved_chunks[: self.max_chunks]:
            if remaining_chars <= 0:
                break
            chunk_payload = chunk.model_dump(mode="json")
            content = str(chunk_payload.get("content", "")).strip()
            if not content:
                continue
            limit = min(self.max_chunk_chars, remaining_chars)
            chunk_payload["content"] = _truncate(content, limit)
            bounded_chunks.append(chunk_payload)
            remaining_chars -= len(chunk_payload["content"])
        return bounded_chunks


def _truncate(value: str, limit: int) -> str:
    if limit < 1:
        return ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return f"{value[: limit - 3].rstrip()}..."


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
