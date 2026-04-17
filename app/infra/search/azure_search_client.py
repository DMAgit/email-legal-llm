"""Azure AI Search adapter for policy retrieval."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import (
    SearchClientConfigurationError,
    SearchClientError,
    SearchIndexNotFoundError,
)


class AzureSearchClient:
    """Small adapter that isolates Azure AI Search SDK usage."""

    def __init__(
        self,
        *,
        endpoint: str | None,
        api_key: str | None,
        index_name: str,
        embedding_client: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.index_name = index_name
        self._embedding_client = embedding_client
        self._client = client
        if self._client is not None:
            return

        if not endpoint or not endpoint.strip():
            raise SearchClientConfigurationError("AZURE_SEARCH_ENDPOINT is required.")
        if not api_key or not api_key.strip():
            raise SearchClientConfigurationError("AZURE_SEARCH_API_KEY is required.")
        if not index_name or not index_name.strip():
            raise SearchClientConfigurationError("AZURE_SEARCH_INDEX_NAME is required.")

        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.search.documents import SearchClient as AzureSDKSearchClient
        except ModuleNotFoundError as exc:
            raise SearchClientConfigurationError(
                "The azure-search-documents package is required for Azure AI Search."
            ) from exc

        self._client = AzureSDKSearchClient(
            endpoint=endpoint.strip(),
            index_name=index_name.strip(),
            credential=AzureKeyCredential(api_key.strip()),
        )

    def search(
        self,
        *,
        query: str,
        top: int,
        clause_type: str | None = None,
        doc_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run metadata-filtered hybrid vector search and return raw dictionaries."""
        query_text = query.strip()
        if not query_text:
            return []
        if top < 1:
            raise ValueError("top must be at least 1.")
        if self._embedding_client is None:
            raise SearchClientConfigurationError("An embedding client is required for vector search.")

        filter_expression = _metadata_filter(clause_type=clause_type, doc_type=doc_type)
        try:
            query_vector = self._embedding_client.embed_query(query_text)
            results = self._client.search(
                search_text=query_text,
                top=top,
                filter=filter_expression,
                vector_queries=[_vectorized_query(query_vector, top)],
                select=["id", "content", "doc_type", "clause_type", "source", "label", "risk_level"],
            )
            return [_result_to_dict(result) for result in results]
        except Exception as exc:
            if exc.__class__.__name__ == "ResourceNotFoundError":
                raise SearchIndexNotFoundError(
                    f"Azure AI Search index not found: {self.index_name}."
                ) from exc
            raise SearchClientError(f"Azure AI Search request failed: {exc}") from exc


def _result_to_dict(result: Any) -> dict[str, Any]:
    item = dict(result)
    score = item.get("@search.score", item.get("score", item.get("search_score", 0.0)))
    item["score"] = score
    item["chunk_id"] = item.get("chunk_id") or item.get("id")
    return item


def _vectorized_query(vector: list[float], top: int) -> Any:
    try:
        from azure.search.documents.models import VectorizedQuery
    except ModuleNotFoundError:
        return {
            "vector": vector,
            "k_nearest_neighbors": top,
            "fields": "content_vector",
        }
    return VectorizedQuery(
        vector=vector,
        k_nearest_neighbors=top,
        fields="content_vector",
    )


def _metadata_filter(
    *,
    clause_type: str | None = None,
    doc_type: str | None = None,
) -> str | None:
    conditions: list[str] = []
    if clause_type and clause_type.strip():
        conditions.append(f"clause_type eq '{_escape_filter_value(clause_type)}'")
    if doc_type and doc_type.strip():
        conditions.append(f"doc_type eq '{_escape_filter_value(doc_type)}'")
    return " and ".join(conditions) or None


def _escape_filter_value(value: str) -> str:
    return value.strip().replace("'", "''")
