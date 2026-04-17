"""Document extraction and chunking through the Unstructured library."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from app.domain.models.document import DocumentChunk, ParsedDocument
from app.domain.models.email import AttachmentMetadata
from app.infra.parsers.base import document_id_for_path
from app.infra.parsers.exceptions import ParserDependencyError, ParserError

GENERIC_CONTENT_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
}


class UnstructuredParser:
    """Extract elements and RAG-ready chunks with `unstructured`."""

    parser_name = "unstructured_partition_chunk_parser"

    def __init__(
        self,
        file_type: str,
        max_characters: int = 1500,
        new_after_n_chars: int = 1000,
        overlap: int = 100,
    ) -> None:
        self.file_type = file_type
        self.max_characters = max_characters
        self.new_after_n_chars = new_after_n_chars
        self.overlap = overlap

    def parse(self, path: Path, metadata: AttachmentMetadata) -> ParsedDocument:
        """Partition a stored attachment and then chunk the resulting elements."""
        try:
            from unstructured.chunking.basic import chunk_elements
            from unstructured.partition.auto import partition
        except ModuleNotFoundError as exc:
            raise ParserDependencyError("Document parsing requires the unstructured package.") from exc

        try:
            elements = partition(
                filename=str(path),
                content_type=self._partition_content_type(metadata),
            )
            chunks = chunk_elements(
                elements,
                max_characters=self.max_characters,
                new_after_n_chars=self.new_after_n_chars,
                overlap=self.overlap,
            )
        except Exception as exc:
            raise ParserError(f"Unstructured failed to parse {metadata.filename}: {exc}") from exc

        raw_text = self._raw_text(elements)
        document_id = document_id_for_path(path)
        warnings = [] if raw_text else ["No extractable text found by unstructured."]

        return ParsedDocument(
            document_id=document_id,
            filename=metadata.filename,
            file_type=self.file_type,
            parser_name=self.parser_name,
            raw_text=raw_text,
            chunks=self._document_chunks(document_id, chunks),
            extracted_tables=self._tables(elements),
            parse_warnings=warnings,
            confidence_hint=0.9 if raw_text else 0.3,
        )

    def _partition_content_type(self, metadata: AttachmentMetadata) -> str | None:
        content_type = (metadata.content_type or "").split(";", maxsplit=1)[0].strip().lower()
        if content_type and content_type not in GENERIC_CONTENT_TYPES:
            return content_type
        if self.file_type == "csv":
            return "text/csv"
        if self.file_type == "pdf":
            return "application/pdf"
        return None

    def _raw_text(self, elements: list[Any]) -> str:
        return "\n\n".join(text for element in elements if (text := str(element).strip()))

    def _document_chunks(self, document_id: str, chunks: list[Any]) -> list[DocumentChunk]:
        document_chunks: list[DocumentChunk] = []
        for index, chunk in enumerate(chunks):
            text = str(chunk).strip()
            if not text:
                continue

            document_chunks.append(
                DocumentChunk(
                    chunk_id=self._chunk_id(document_id, index, text),
                    index=index,
                    text=text,
                    element_type=self._element_type(chunk),
                    metadata=self._metadata_dict(chunk),
                )
            )

        return document_chunks

    def _tables(self, elements: list[Any]) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        for index, element in enumerate(elements):
            element_type = self._element_type(element)
            if element_type not in {"Table", "TableChunk"}:
                continue

            metadata = self._metadata_dict(element)
            tables.append(
                {
                    "index": index,
                    "text": str(element).strip(),
                    "html": metadata.get("text_as_html"),
                    "metadata": metadata,
                }
            )

        return tables

    def _chunk_id(self, document_id: str, index: int, text: str) -> str:
        digest = sha256(f"{document_id}:{index}:{text}".encode("utf-8")).hexdigest()
        return digest[:16]

    def _element_type(self, element: Any) -> str:
        return str(getattr(element, "category", None) or element.__class__.__name__)

    def _metadata_dict(self, element: Any) -> dict[str, Any]:
        metadata = getattr(element, "metadata", None)
        if metadata is None:
            return {}

        if hasattr(metadata, "to_dict"):
            raw_metadata = metadata.to_dict()
        elif isinstance(metadata, dict):
            raw_metadata = metadata
        else:
            return {}

        return self._json_safe_metadata(raw_metadata)

    def _json_safe_metadata(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): self._json_safe_metadata(item)
                for key, item in value.items()
                if key not in {"orig_elements", "coordinates"}
            }
        if isinstance(value, list):
            return [self._json_safe_metadata(item) for item in value]
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        return str(value)
