"""Clause-level policy retrieval for extracted contract fields."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.core.exceptions import RetrievalError, SearchClientError
from app.domain.models.extraction import ContractExtractionResult
from app.domain.models.retrieval import RetrievedContextChunk, RetrievalResult


@dataclass(frozen=True)
class ClauseQuerySpec:
    """Mapping from an extracted field to a searchable policy clause type."""

    field_name: str
    clause_type: str | None = None
    doc_type: str | None = None


class SearchClient(Protocol):
    """Protocol for search adapters used by retrieval."""

    def search(
        self,
        *,
        query: str,
        top: int,
        clause_type: str | None = None,
        doc_type: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return raw search results for a query and optional metadata filters."""


CLAUSE_QUERY_SPECS: tuple[ClauseQuerySpec, ...] = (
    ClauseQuerySpec("liability_clause", clause_type="liability"),
    ClauseQuerySpec("data_usage_clause", clause_type="data_usage"),
    ClauseQuerySpec("termination_clause", clause_type="termination"),
    ClauseQuerySpec("payment_terms", clause_type="payment_terms"),
    ClauseQuerySpec("renewal_clause", clause_type="renewal"),
    ClauseQuerySpec("governing_law", clause_type="governing_law"),
    ClauseQuerySpec("vendor_name"),
    ClauseQuerySpec("contract_type"),
)


class RetrievalService:
    """Retrieve policy context for each useful extracted contract clause."""

    def __init__(
        self,
        *,
        search_client: SearchClient,
        top_results_per_clause: int = 3,
        max_chunks: int = 10,
    ) -> None:
        if top_results_per_clause < 1:
            raise ValueError("top_results_per_clause must be at least 1.")
        if max_chunks < 1:
            raise ValueError("max_chunks must be at least 1.")
        self.search_client = search_client
        self.top_results_per_clause = top_results_per_clause
        self.max_chunks = max_chunks

    def retrieve_for_extraction(self, extraction: ContractExtractionResult) -> RetrievalResult:
        """Retrieve, normalize, deduplicate, and rank policy context."""
        warnings: list[str] = []
        chunks_by_id: dict[str, RetrievedContextChunk] = {}
        query_specs = self._query_specs(extraction)

        if not query_specs:
            return RetrievalResult(
                warnings=["No extracted fields were available for policy retrieval."]
            )

        for spec, query in query_specs:
            try:
                raw_results = self.search_client.search(
                    query=query,
                    top=self.top_results_per_clause,
                    clause_type=spec.clause_type,
                    doc_type=spec.doc_type,
                )
            except SearchClientError as exc:
                raise RetrievalError(f"Search failed for {spec.field_name}: {exc}") from exc

            if not raw_results:
                warnings.append(f"No policy context found for {spec.field_name}.")
                continue

            for raw_result in raw_results:
                chunk = self._normalize_result(raw_result)
                if chunk is None:
                    warnings.append(f"Skipped malformed search result for {spec.field_name}.")
                    continue
                existing = chunks_by_id.get(chunk.chunk_id)
                if existing is None or chunk.score > existing.score:
                    chunks_by_id[chunk.chunk_id] = chunk

        chunks = sorted(chunks_by_id.values(), key=lambda chunk: chunk.score, reverse=True)
        limited_chunks = chunks[: self.max_chunks]
        if not limited_chunks:
            warnings.append("No retrieved policy context was available for classification.")
        return RetrievalResult(chunks=limited_chunks, warnings=warnings)

    def retrieve_chunks(self, extraction: ContractExtractionResult) -> list[RetrievedContextChunk]:
        """Return only retrieved chunks for callers that do not need warnings."""
        return self.retrieve_for_extraction(extraction).chunks

    def _query_specs(
        self,
        extraction: ContractExtractionResult,
    ) -> list[tuple[ClauseQuerySpec, str]]:
        query_specs: list[tuple[ClauseQuerySpec, str]] = []
        for spec in CLAUSE_QUERY_SPECS:
            value = _clean_string(getattr(extraction, spec.field_name, None))
            if value:
                query_specs.append((spec, value))
        return query_specs

    def _normalize_result(self, raw_result: Mapping[str, Any]) -> RetrievedContextChunk | None:
        content = _clean_string(raw_result.get("content"))
        if not content:
            return None

        raw_chunk_id = _clean_string(raw_result.get("chunk_id") or raw_result.get("id"))
        chunk_id = raw_chunk_id or _content_chunk_id(content)
        source = _clean_string(raw_result.get("source")) or "unknown"
        doc_type = _clean_string(raw_result.get("doc_type")) or "unknown"
        clause_type = _clean_string(raw_result.get("clause_type"))
        score = _score(raw_result)

        return RetrievedContextChunk(
            chunk_id=chunk_id,
            source=source,
            doc_type=doc_type,
            clause_type=clause_type,
            content=content,
            score=score,
        )


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _score(raw_result: Mapping[str, Any]) -> float:
    value = (
        raw_result.get("@search.score")
        if "@search.score" in raw_result
        else raw_result.get("score", raw_result.get("search_score", 0.0))
    )
    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _content_chunk_id(content: str) -> str:
    digest = hashlib.sha1(content.encode("utf-8")).hexdigest()
    return f"content-{digest[:16]}"
