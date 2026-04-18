"""Parser selection based on MIME type, file extension, and file signatures."""

from __future__ import annotations

import csv
from mimetypes import guess_type
from pathlib import Path

from app.infra.parsers.base import DocumentParser
from app.infra.parsers.exceptions import UnsupportedFileTypeError
from app.infra.parsers.unstructured_parser import UnstructuredParser


class ParserFactory:
    """Select an attachment parser from file metadata and lightweight sniffing."""

    _MIME_FILE_TYPES = {
        "application/pdf": "pdf",
        "text/csv": "csv",
        "application/csv": "csv",
        "application/vnd.ms-excel": "csv",
    }
    _EXTENSION_FILE_TYPES = {
        ".pdf": "pdf",
        ".csv": "csv",
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
        ".tif": "image",
        ".tiff": "image",
        ".bmp": "image",
        ".webp": "image",
    }

    def __init__(self, supported_file_types: set[str] | None = None) -> None:
        self.supported_file_types = (
            supported_file_types if supported_file_types is not None else {"pdf", "image", "csv"}
        )

    @classmethod
    def default(cls) -> "ParserFactory":
        """Create the default M2 parser factory."""
        return cls()

    def get_parser(self, path: Path, content_type: str | None = None) -> DocumentParser:
        """Return a parser for a stored attachment."""
        file_type = self.detect_file_type(path, content_type)
        if file_type not in self.supported_file_types:
            raise UnsupportedFileTypeError(f"No parser registered for file type: {file_type}.")
        return UnstructuredParser(file_type=file_type)

    def detect_file_type(self, path: Path, content_type: str | None = None) -> str:
        """Detect the best supported file type for an attachment."""
        detectors = (
            self._from_content_type(content_type),
            self._from_extension(path),
            self._from_content_type(guess_type(path.name)[0]),
            self._from_signature(path),
        )
        for file_type in detectors:
            if file_type is not None:
                return file_type

        raise UnsupportedFileTypeError(f"Unsupported attachment type for file: {path.name}.")

    def _from_content_type(self, content_type: str | None) -> str | None:
        if not content_type:
            return None

        normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
        if normalized.startswith("image/"):
            return "image"
        return self._MIME_FILE_TYPES.get(normalized)

    def _from_extension(self, path: Path) -> str | None:
        return self._EXTENSION_FILE_TYPES.get(path.suffix.lower())

    def _from_signature(self, path: Path) -> str | None:
        try:
            header = path.read_bytes()[:4096]
        except OSError:
            return None

        if header.startswith(b"%PDF"):
            return "pdf"
        if header.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM")):
            return "image"
        if header.startswith((b"II*\x00", b"MM\x00*")):
            return "image"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "image"

        return self._csv_from_signature(header)

    def _csv_from_signature(self, header: bytes) -> str | None:
        if not header or b"\x00" in header:
            return None

        try:
            text = header.decode("utf-8")
        except UnicodeDecodeError:
            return None

        if "," not in text and "\t" not in text and "\n" not in text:
            return None

        try:
            csv.Sniffer().sniff(text)
        except csv.Error:
            return None

        return "csv"
