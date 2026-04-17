"""Attachment parsing service."""

from pathlib import Path

from app.domain.models.document import DocumentParseError, ParsedDocument
from app.domain.models.email import AttachmentMetadata
from app.infra.parsers.exceptions import ParserError
from app.infra.parsers.parser_factory import ParserFactory


class ParsingService:
    """Coordinate file-type detection and parser execution."""

    def __init__(self, parser_factory: ParserFactory | None = None) -> None:
        self.parser_factory = parser_factory or ParserFactory.default()

    def parse_attachment(self, attachment: AttachmentMetadata) -> ParsedDocument:
        """Parse one stored attachment into normalized document text."""
        path = Path(attachment.storage_path)
        parser = self.parser_factory.get_parser(path, attachment.content_type)
        return parser.parse(path, attachment)

    def parse_attachments(
        self,
        attachments: list[AttachmentMetadata],
    ) -> tuple[list[ParsedDocument], list[DocumentParseError]]:
        """Parse attachments, preserving per-file failures as response errors."""
        documents: list[ParsedDocument] = []
        errors: list[DocumentParseError] = []

        for attachment in attachments:
            parser = None
            try:
                path = Path(attachment.storage_path)
                parser = self.parser_factory.get_parser(path, attachment.content_type)
                documents.append(parser.parse(path, attachment))
            except (OSError, ParserError) as exc:
                errors.append(
                    DocumentParseError(
                        filename=attachment.filename,
                        file_type=getattr(parser, "file_type", None),
                        parser_name=getattr(parser, "parser_name", None),
                        error=str(exc),
                    )
                )

        return documents, errors
