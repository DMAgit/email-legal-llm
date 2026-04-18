"""OpenAI embedding client adapter for vector indexing and search."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.exceptions import OpenAIClientConfigurationError, OpenAIClientError


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
    ) -> None:
        if dimensions < 1:
            raise ValueError("Embedding dimensions must be at least 1.")
        self.model = model
        self.dimensions = dimensions
        self._client = client
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

        try:
            response = self._client.embeddings.create(
                model=self.model,
                input=clean_texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
        except Exception as exc:
            raise OpenAIClientError(f"OpenAI embedding request failed: {exc}") from exc

        vectors = [item.embedding for item in response.data]
        if len(vectors) != len(clean_texts):
            raise OpenAIClientError("OpenAI embedding response count did not match input count.")
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise OpenAIClientError(
                    f"OpenAI embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}."
                )
        return vectors

    def embed_query(self, query: str) -> list[float]:
        """Return a single embedding vector for a search query."""
        vectors = self.embed_texts([query])
        if not vectors:
            raise OpenAIClientError("Cannot embed an empty query.")
        return vectors[0]
