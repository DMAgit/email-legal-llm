"""Structured contract extraction service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.core.model_registry import ModelConfig, ModelRegistry
from app.domain.models.document import ParsedDocument
from app.domain.models.extraction import (
    ContractExtractionResult,
    DocumentExtraction,
    DocumentExtractionError,
)
from app.infra.llm.openai_client import OpenAIClientError


class StructuredLLMClient(Protocol):
    """Protocol for LLM clients that can return schema-shaped JSON."""

    def create_structured_output(
        self,
        *,
        model_config: ModelConfig,
        system_prompt: str,
        user_content: str,
        schema_model: type[ContractExtractionResult],
    ) -> dict:
        """Return a JSON object generated under the supplied response schema."""


class ExtractionError(RuntimeError):
    """Raised when a parsed document cannot be converted into structured fields."""


class ExtractionService:
    """Extract structured contract fields from parsed document text."""

    def __init__(
        self,
        *,
        model_registry: ModelRegistry,
        prompt_dir: Path,
        llm_client: StructuredLLMClient,
        config_name: str = "extraction",
    ) -> None:
        self.model_registry = model_registry
        self.prompt_dir = prompt_dir
        self.llm_client = llm_client
        self.config_name = config_name

    def extract_document(self, document: ParsedDocument) -> ContractExtractionResult:
        """Run extraction for one parsed document and validate the LLM response."""
        raw_text = document.raw_text.strip()
        if not raw_text:
            raise ExtractionError(f"Parsed document has no extractable text: {document.filename}.")

        model_config = self._model_config()
        prompt = self._load_prompt(model_config)
        user_content = self._document_payload(document, raw_text)

        try:
            response = self.llm_client.create_structured_output(
                model_config=model_config,
                system_prompt=prompt,
                user_content=user_content,
                schema_model=ContractExtractionResult,
            )
        except OpenAIClientError as exc:
            raise ExtractionError(str(exc)) from exc

        try:
            return ContractExtractionResult.model_validate(response)
        except ValidationError as exc:
            raise ExtractionError(f"Extraction response failed schema validation: {exc}") from exc

    def extract_documents(
        self,
        documents: list[ParsedDocument],
    ) -> tuple[list[DocumentExtraction], list[DocumentExtractionError]]:
        """Extract multiple documents while preserving per-document failures."""
        extractions: list[DocumentExtraction] = []
        errors: list[DocumentExtractionError] = []

        for document in documents:
            try:
                extraction = self.extract_document(document)
            except ExtractionError as exc:
                errors.append(
                    DocumentExtractionError(
                        document_id=document.document_id,
                        filename=document.filename,
                        error=str(exc),
                    )
                )
                continue

            extractions.append(
                DocumentExtraction(
                    document_id=document.document_id,
                    filename=document.filename,
                    extraction=extraction,
                )
            )

        return extractions, errors

    def _model_config(self) -> ModelConfig:
        try:
            config = self.model_registry.get(self.config_name)
        except KeyError as exc:
            raise ExtractionError(str(exc)) from exc
        if config.provider.lower() != "openai":
            raise ExtractionError(f"Unsupported extraction provider: {config.provider}.")
        if config.response_schema != "ContractExtractionResult":
            raise ExtractionError(
                "Extraction model config must declare response_schema=ContractExtractionResult."
            )
        return config

    def _load_prompt(self, model_config: ModelConfig) -> str:
        template_name = model_config.prompt_template or "extraction_prompt_v1"
        path = self._prompt_path(template_name)
        try:
            prompt = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ExtractionError(f"Extraction prompt could not be read: {path}.") from exc

        if not prompt:
            raise ExtractionError(f"Extraction prompt is empty: {path}.")
        return prompt

    def _prompt_path(self, template_name: str) -> Path:
        if template_name == "extraction_prompt_v1":
            return self.prompt_dir / "extraction_prompt.txt"
        return self.prompt_dir / f"{template_name}.txt"

    def _document_payload(self, document: ParsedDocument, raw_text: str) -> str:
        tables = [
            {
                "index": table.get("index"),
                "text": table.get("text"),
                "html": table.get("html"),
            }
            for table in document.extracted_tables
        ]
        payload = {
            "document": {
                "document_id": document.document_id,
                "filename": document.filename,
                "file_type": document.file_type,
                "parser_name": document.parser_name,
                "confidence_hint": document.confidence_hint,
                "parse_warnings": document.parse_warnings,
                "tables": tables,
            },
            "document_text": raw_text,
        }
        return json.dumps(payload, ensure_ascii=True)
