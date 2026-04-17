"""Mailgun webhook normalization and attachment storage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from starlette.datastructures import FormData, UploadFile

from app.core.exceptions import IngestionError
from app.domain.models.email import AttachmentMetadata, InboundEmail


@dataclass(frozen=True)
class IngestedEmail:
    """Email metadata and attachment references produced by ingestion."""

    process_id: str
    email: InboundEmail
    attachments: list[AttachmentMetadata]


class IngestionService:
    """Normalize Mailgun form fields and persist attachments locally."""

    def __init__(self, upload_dir: Path) -> None:
        self.upload_dir = upload_dir

    async def ingest_mailgun_form(self, form: FormData) -> IngestedEmail:
        """Persist attachments and return normalized email metadata."""
        uploads = self._extract_uploads(form)
        if not uploads:
            raise IngestionError("No attachments found in inbound Mailgun payload.")

        email = self._build_email(form, attachment_count=len(uploads))
        process_id = uuid4().hex
        attachments = await self.persist_uploads(process_id, uploads)

        return IngestedEmail(
            process_id=process_id,
            email=email,
            attachments=attachments,
        )

    async def persist_uploads(
        self,
        process_id: str,
        uploads: list[UploadFile],
    ) -> list[AttachmentMetadata]:
        """Store inbound upload files under the process-specific upload path."""
        process_dir = self.upload_dir / process_id
        process_dir.mkdir(parents=True, exist_ok=True)

        attachments: list[AttachmentMetadata] = []
        used_names: set[str] = set()

        for index, upload in enumerate(uploads, start=1):
            filename = self._safe_filename(upload.filename, fallback=f"attachment-{index}")
            filename = self._deduplicate_filename(filename, used_names)
            destination = process_dir / filename

            content = await upload.read()
            destination.write_bytes(content)
            await upload.close()

            attachments.append(
                AttachmentMetadata(
                    filename=filename,
                    content_type=upload.content_type,
                    size_bytes=len(content),
                    storage_path=str(destination),
                )
            )

        return attachments

    def _build_email(self, form: FormData, attachment_count: int) -> InboundEmail:
        sender = self._required_field(form, "sender", "from")
        recipient = self._required_field(form, "recipient", "to")
        subject = self._string_field(form, "subject") or ""
        declared_count = self._int_field(form, "attachment-count", "attachment_count")

        return InboundEmail(
            message_id=self._string_field(form, "Message-Id", "Message-ID", "message-id", "message_id"),
            sender=sender,
            recipient=recipient,
            subject=subject,
            plain_text_body=self._string_field(form, "body-plain", "body_plain", "stripped-text"),
            attachment_count=declared_count if declared_count is not None else attachment_count,
            received_at=datetime.now(UTC),
        )

    def _extract_uploads(self, form: FormData) -> list[UploadFile]:
        uploads: list[UploadFile] = []
        for _name, value in form.multi_items():
            if isinstance(value, UploadFile):
                uploads.append(value)
        return uploads

    def _required_field(self, form: FormData, *names: str) -> str:
        value = self._string_field(form, *names)
        if value is None or value == "":
            joined = ", ".join(names)
            raise IngestionError(f"Missing required Mailgun field: {joined}.")
        return value

    def _string_field(self, form: FormData, *names: str) -> str | None:
        for name in names:
            value = form.get(name)
            if isinstance(value, str):
                return value.strip()
        return None

    def _int_field(self, form: FormData, *names: str) -> int | None:
        value = self._string_field(form, *names)
        if value is None or value == "":
            return None
        try:
            return int(value)
        except ValueError as exc:
            joined = ", ".join(names)
            raise IngestionError(f"Invalid integer Mailgun field {joined}: {value}.") from exc

    def _safe_filename(self, filename: str | None, fallback: str) -> str:
        candidate = Path(filename or fallback).name.replace("\x00", "")
        candidate = re.sub(r"[^A-Za-z0-9._ -]+", "_", candidate).strip(" .")
        return candidate or fallback

    def _deduplicate_filename(self, filename: str, used_names: set[str]) -> str:
        if filename not in used_names:
            used_names.add(filename)
            return filename

        path = Path(filename)
        stem = path.stem or "attachment"
        suffix = path.suffix
        counter = 2

        while True:
            candidate = f"{stem}-{counter}{suffix}"
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
            counter += 1
