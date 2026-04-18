"""Seed Azure AI Search with the demo contract-risk knowledge base."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.exceptions import SearchClientConfigurationError, SearchClientError
from app.infra.llm.embedding_client import OpenAIEmbeddingClient


DEFAULT_KB_DIR = Path("data/kb")
VECTOR_FIELD_NAME = "content_vector"
VECTOR_PROFILE_NAME = "contract-kb-vector-profile"
VECTOR_ALGORITHM_NAME = "contract-kb-hnsw"


@dataclass(frozen=True)
class SeedResult:
    """Summary of one Azure AI Search seed run."""

    attempted: int
    succeeded: int
    document_count: int | None


def build_documents(kb_dir: Path = DEFAULT_KB_DIR) -> list[dict[str, Any]]:
    """Build searchable Azure documents from local demo KB files."""
    documents: list[dict[str, Any]] = []
    for path in sorted(kb_dir.glob("*.md")):
        if path.name == "approved_clause_library.md" and (kb_dir / "clause_library.md").exists():
            continue
        documents.extend(_markdown_documents(path, _markdown_doc_type(path)))
    vendor_path = kb_dir / "vendors.csv"
    if vendor_path.exists():
        documents.extend(_vendor_documents(vendor_path))
    historical_reviews_path = kb_dir / "historical_reviews.json"
    if historical_reviews_path.exists():
        documents.extend(_historical_review_documents(historical_reviews_path))
    return documents


def embed_documents(
    documents: list[dict[str, Any]],
    embedding_client: OpenAIEmbeddingClient,
    *,
    batch_size: int = 32,
) -> list[dict[str, Any]]:
    """Attach OpenAI embedding vectors to search documents."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    embedded_documents: list[dict[str, Any]] = []
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        vectors = embedding_client.embed_texts([_embedding_text(document) for document in batch])
        for document, vector in zip(batch, vectors, strict=True):
            embedded = dict(document)
            embedded[VECTOR_FIELD_NAME] = vector
            embedded_documents.append(embedded)
    return embedded_documents


def seed_search_index(documents: list[dict[str, Any]], settings: Settings) -> SeedResult:
    """Create or update the configured Azure AI Search index, then upload documents."""
    if not settings.azure_search_endpoint or not settings.azure_search_api_key:
        raise SearchClientConfigurationError(
            "AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY are required to seed search."
        )
    if not settings.openai_api_key:
        raise SearchClientConfigurationError("OPENAI_API_KEY is required to embed KB documents.")

    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration,
            SearchableField,
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SimpleField,
            VectorSearch,
            VectorSearchProfile,
        )
    except ModuleNotFoundError as exc:
        raise SearchClientConfigurationError(
            "The azure-search-documents package is required to seed Azure AI Search."
        ) from exc

    credential = AzureKeyCredential(settings.azure_search_api_key)
    index_client = SearchIndexClient(settings.azure_search_endpoint, credential)
    index = SearchIndex(
        name=settings.azure_search_index_name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
            SearchField(
                name=VECTOR_FIELD_NAME,
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=settings.embedding_dimensions,
                vector_search_profile_name=VECTOR_PROFILE_NAME,
            ),
            SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="clause_type", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="document_title", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="label", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="risk_level", type=SearchFieldDataType.String, filterable=True),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME)],
            profiles=[
                VectorSearchProfile(
                    name=VECTOR_PROFILE_NAME,
                    algorithm_configuration_name=VECTOR_ALGORITHM_NAME,
                )
            ],
        ),
    )
    index_client.create_or_update_index(index)

    embedded_documents = embed_documents(
        documents,
        OpenAIEmbeddingClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        ),
    )
    search_client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=credential,
    )
    succeeded = _upload_documents(search_client, embedded_documents)
    return SeedResult(
        attempted=len(embedded_documents),
        succeeded=succeeded,
        document_count=_document_count(search_client),
    )


def main() -> int:
    """Command-line entrypoint for local demo seeding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-dir", type=Path, default=DEFAULT_KB_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    documents = build_documents(args.kb_dir)
    if args.dry_run:
        print(json.dumps(documents, indent=2, ensure_ascii=True))
        return 0

    settings = Settings()
    result = seed_search_index(documents, settings)
    print(f"Target service: {settings.azure_search_endpoint}")
    print(f"Target index: {settings.azure_search_index_name}")
    print(f"Uploaded {result.succeeded}/{result.attempted} documents into Azure AI Search.")
    if result.document_count is None:
        print("Azure document count could not be verified by the SDK.")
    else:
        print(f"Azure document count reported by the index: {result.document_count}")
    return 0


def _markdown_documents(path: Path, doc_type: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    document_title = _markdown_title(text)
    sections = _split_markdown_sections(text)
    return [
        _document(
            source=path.name,
            doc_type=doc_type,
            document_title=document_title,
            label=_section_label(section),
            content=section,
            index=index,
        )
        for index, section in enumerate(sections)
    ]


def _markdown_doc_type(path: Path) -> str:
    name = path.stem.lower()
    if "approved_clause" in name or "clause_library" in name:
        return "clause_library"
    if "escalation" in name:
        return "escalation_matrix"
    return "policy"


def _vendor_documents(path: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        for index, row in enumerate(csv.DictReader(file)):
            vendor_name = row.get("vendor_name", "").strip()
            status = row.get("status", "").strip()
            tier = row.get("tier", "").strip()
            notes = row.get("notes", "").strip().rstrip(".")
            content = f"Vendor {vendor_name}. Status: {status}. Tier: {tier}. Notes: {notes}."
            documents.append(
                _document(
                    source=path.name,
                    doc_type="vendor",
                    label=vendor_name or "vendor",
                    content=content,
                    index=index,
                    risk_level=row.get("risk_level") or _vendor_risk_level(status=status, tier=tier),
                )
            )
    return documents


def _historical_review_documents(path: Path) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    documents: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        decision = str(record.get("decision") or record.get("outcome") or "unknown")
        clause_text = str(record.get("clause_text") or record.get("summary") or "")
        reason = str(record.get("reason") or record.get("summary") or "")
        content = " ".join(
            [
                f"Clause type: {record.get('clause_type', 'unknown')}.",
                f"Decision: {decision}.",
                f"Clause text: {clause_text}",
                f"Reason: {reason}",
            ]
        )
        documents.append(
            _document(
                source=path.name,
                doc_type="historical_review",
                label=f"{record.get('clause_type', 'unknown')} {decision}",
                content=content,
                index=index,
                clause_type=record.get("clause_type"),
                risk_level=record.get("risk_level") or _decision_risk_level(decision),
                infer_risk_level=False,
            )
        )
    return documents


def _document(
    *,
    source: str,
    doc_type: str,
    label: str,
    content: str,
    index: int,
    document_title: str | None = None,
    clause_type: str | None = None,
    risk_level: str | None = None,
    infer_risk_level: bool = True,
) -> dict[str, Any]:
    clause = clause_type or _infer_clause_type(label=label, content=content)
    return {
        "id": _slug(f"{source}-{index}-{label}"),
        "content": content,
        "doc_type": doc_type,
        "clause_type": clause,
        "source": source,
        "document_title": document_title,
        "label": label,
        "risk_level": risk_level or (_infer_risk_level(content) if infer_risk_level else None),
    }


def _embedding_text(document: dict[str, Any]) -> str:
    metadata = [
        f"Source: {document.get('source')}",
        f"Type: {document.get('doc_type')}",
        f"Title: {document.get('document_title') or 'untitled'}",
        f"Clause: {document.get('clause_type') or 'general'}",
        f"Label: {document.get('label')}",
        f"Risk: {document.get('risk_level') or 'unspecified'}",
    ]
    return "\n".join([*metadata, "", str(document["content"])])


def _upload_documents(search_client: Any, documents: list[dict[str, Any]]) -> int:
    if not documents:
        return 0

    results = search_client.upload_documents(documents=documents)
    failures: list[str] = []
    succeeded = 0
    for result in results:
        if _indexing_result_succeeded(result):
            succeeded += 1
            continue
        failures.append(_indexing_result_message(result))

    if failures:
        preview = "; ".join(failures[:5])
        raise SearchClientError(
            f"Azure AI Search rejected {len(failures)} uploaded documents. {preview}"
        )
    return succeeded


def _document_count(search_client: Any) -> int | None:
    try:
        return int(search_client.get_document_count())
    except Exception:
        return None


def _indexing_result_succeeded(result: Any) -> bool:
    if isinstance(result, dict):
        succeeded = result.get("succeeded")
    else:
        succeeded = getattr(result, "succeeded", None)
    return True if succeeded is None else bool(succeeded)


def _indexing_result_message(result: Any) -> str:
    if isinstance(result, dict):
        key = result.get("key") or result.get("id") or "unknown"
        status_code = result.get("status_code") or result.get("statusCode") or "unknown"
        error_message = result.get("error_message") or result.get("errorMessage") or "no error message"
    else:
        key = getattr(result, "key", "unknown")
        status_code = getattr(result, "status_code", "unknown")
        error_message = getattr(result, "error_message", "no error message")
    return f"{key} status={status_code}: {error_message}"


def _split_markdown_sections(text: str) -> list[str]:
    parts = re.split(r"(?m)^##\s+", text.strip())
    sections = [
        part.strip()
        for part in parts
        if part.strip() and not _is_title_only_section(part.strip())
    ]
    return sections or [text.strip()]


def _section_label(section: str) -> str:
    first_line = section.splitlines()[0].strip("# ").strip()
    return first_line or "knowledge base section"


def _markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped.removeprefix("# ").strip() or None
    return None


def _is_title_only_section(section: str) -> bool:
    lines = [line for line in section.splitlines() if line.strip()]
    return len(lines) == 1 and lines[0].startswith("# ")


def _infer_clause_type(*, label: str, content: str) -> str | None:
    label_lowered = label.lower()
    label_map = {
        "liability": "liability",
        "data usage": "data_usage",
        "privacy": "data_usage",
        "payment": "payment_terms",
        "termination": "termination",
        "renewal": "renewal",
        "governing law": "governing_law",
        "jurisdiction": "governing_law",
    }
    for keyword, clause_type in label_map.items():
        if keyword in label_lowered:
            return clause_type

    lowered = content.lower()
    clause_keywords = {
        "liability": ("liability", "indemnity", "damages"),
        "payment_terms": ("payment", "invoice", "net 30", "net 45", "net 60"),
        "renewal": ("renewal", "auto-renew", "non-renewal"),
        "termination": ("termination", "terminate", "notice period"),
        "governing_law": ("governing law", "jurisdiction", "venue"),
        "data_usage": ("data", "privacy", "personal information", "ai training"),
    }
    for clause_type, keywords in clause_keywords.items():
        if any(keyword in lowered for keyword in keywords):
            return clause_type
    return None


def _infer_risk_level(content: str) -> str | None:
    lowered = content.lower()
    if any(
        term in lowered
        for term in (
            "prohibited",
            "prohibited clause",
            "must escalate",
            "requires legal review",
            "unlimited liability",
        )
    ) or "legal review" in lowered:
        return "high"
    if any(
        term in lowered
        for term in (
            "negotiable",
            "requires review",
            "procurement review",
            "procurement approval",
            "non-standard",
            "net 60",
        )
    ):
        return "medium"
    if any(term in lowered for term in ("acceptable", "approved", "standard", "low risk")):
        return "low"
    return None


def _vendor_risk_level(*, status: str, tier: str) -> str | None:
    status_lowered = status.lower()
    tier_lowered = tier.lower()
    if status_lowered in {"blocked", "watchlist"}:
        return "high"
    if status_lowered == "conditional" or tier_lowered == "tier_1":
        return "medium"
    if status_lowered == "approved":
        return "low"
    return None


def _decision_risk_level(decision: str) -> str | None:
    decision_lowered = decision.lower()
    if decision_lowered == "legal_review":
        return "high"
    if decision_lowered == "procurement_review":
        return "medium"
    if decision_lowered == "auto_store":
        return "low"
    return None


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-").lower()
    return slug[:128] or "kb-document"


if __name__ == "__main__":
    raise SystemExit(main())
