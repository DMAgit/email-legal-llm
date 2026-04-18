"""OpenAI embedding client adapter for vector indexing and search."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.core.exceptions import OpenAIClientConfigurationError, OpenAIClientError
from app.core.metrics import MetricsCollector


class OpenAIEmbeddingClient:
    """Small adapter around the OpenAI embeddings API."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        client: Any | None = None,
        metrics_collector: MetricsCollector | None = None,
    ) -> None:
        if dimensions < 1:
            raise ValueError("Embedding dimensions must be at least 1.")
        self.model = model
        self.dimensions = dimensions
        self._client = client
        self._metrics_collector = metrics_collector
        if self._client is not None:
            return

        if not api_key or not api_key.strip():
            raise OpenAIClientConfigurationError("OPENAI_API_KEY is required for embeddings.")

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise OpenAIClientConfigurationError(
                "The openai package is required. Install requirements before embedding documents."
            ) from exc

        kwargs: dict[str, str] = {"api_key": api_key}
        if base_url and base_url.strip():
            kwargs["base_url"] = base_url.strip()
        self._client = OpenAI(**kwargs)

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector for each supplied text."""
        clean_texts = [text.strip() for text in texts if text.strip()]
        if not clean_texts:
            return []

        input_text_chars = sum(len(text) for text in clean_texts)
        request_payload_chars = _json_chars(
            {
                "model": self.model,
                "input": clean_texts,
                "dimensions": self.dimensions,
                "encoding_format": "float",
            }
        )
        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=clean_texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except Exception as exc:
            self._record_embedding_call(
                success=False,
                input_items=len(clean_texts),
                input_text_chars=input_text_chars,
                request_payload_chars=request_payload_chars,
            )
            raise OpenAIClientError(f"OpenAI embedding request failed: {exc}") from exc

        usage = _usage_values(response)
        vectors = [item.embedding for item in response.data]
        if len(vectors) != len(clean_texts):
            self._record_embedding_call(
                success=False,
                input_items=len(clean_texts),
                input_text_chars=input_text_chars,
                request_payload_chars=request_payload_chars,
                usage=usage,
            )
            raise OpenAIClientError("OpenAI embedding response count did not match input count.")
        for vector in vectors:
            if len(vector) != self.dimensions:
                self._record_embedding_call(
                    success=False,
                    input_items=len(clean_texts),
                    input_text_chars=input_text_chars,
                    request_payload_chars=request_payload_chars,
                    usage=usage,
                )
                raise OpenAIClientError(
                    f"OpenAI embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}."
                )
        self._record_embedding_call(
            success=True,
            input_items=len(clean_texts),
            input_text_chars=input_text_chars,
            request_payload_chars=request_payload_chars,
            usage=usage,
        )
        return vectors

    def embed_query(self, query: str) -> list[float]:
        """Return a single embedding vector for a search query."""
        vectors = self.embed_texts([query])
        if not vectors:
            raise OpenAIClientError("Cannot embed an empty query.")
        return vectors[0]

    def _record_embedding_call(
        self,
        *,
        success: bool,
        input_items: int,
        input_text_chars: int,
        request_payload_chars: int,
        usage: dict[str, int] | None = None,
    ) -> None:
        if self._metrics_collector is None:
            return
        usage = usage or {}
        self._metrics_collector.record_openai_call(
            operation="embeddings.create",
            model=self.model,
            success=success,
            input_items=input_items,
            input_text_chars=input_text_chars,
            request_payload_chars=request_payload_chars,
            prompt_tokens=usage.get("prompt_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )


def _json_chars(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=True, default=str))
    except TypeError:
        return 0


def _usage_values(response: Any) -> dict[str, int]:
    usage = _get_value(response, "usage")
    if usage is None:
        return {}
    values: dict[str, int] = {}
    for key in ("prompt_tokens", "total_tokens"):
        raw_value = _get_value(usage, key)
        try:
            values[key] = int(raw_value)
        except (TypeError, ValueError):
            continue
    return values


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
