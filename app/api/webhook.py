"""Inbound webhook endpoints."""

import hmac
import time

from fastapi import APIRouter, HTTPException, Request, status
from starlette.datastructures import FormData

from app.api.deps import SettingsDep
from app.domain.models.email import AttachmentMetadata
from app.domain.models.ingestion import AttachmentProcessingSummary, InboundEmailProcessingResult
from app.services.ingestion_service import IngestionError, IngestionService
from app.services.parsing_service import ParsingService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
MAILGUN_SIGNATURE_MAX_AGE_SECONDS = 15 * 60


@router.post(
    "/mailgun/inbound",
    response_model=InboundEmailProcessingResult,
    status_code=status.HTTP_200_OK,
)
async def mailgun_inbound(request: Request, settings: SettingsDep) -> InboundEmailProcessingResult:
    """Receive a Mailgun inbound email webhook and parse stored attachments."""
    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Form parsing is unavailable: {exc}",
        ) from exc

    _validate_mailgun_signature(form, settings.mailgun_webhook_secret)

    ingestion_service = IngestionService(settings.upload_dir)
    parsing_service = ParsingService()

    try:
        ingested = await ingestion_service.ingest_mailgun_form(form)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    documents, errors = parsing_service.parse_attachments(ingested.attachments)

    return InboundEmailProcessingResult(
        process_id=ingested.process_id,
        email=ingested.email,
        attachments=[_public_attachment(attachment) for attachment in ingested.attachments],
        documents=documents,
        errors=errors,
    )


def _validate_mailgun_signature(form: FormData, secret: str | None) -> None:
    secret = secret.strip() if secret else ""
    if not secret:
        return

    timestamp = _form_string(form, "timestamp")
    token = _form_string(form, "token")
    signature = _form_string(form, "signature")
    if not timestamp or not token or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Mailgun webhook signature fields.",
        )

    try:
        timestamp_value = float(timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Mailgun webhook signature.",
        ) from exc

    if abs(time.time() - timestamp_value) > MAILGUN_SIGNATURE_MAX_AGE_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Mailgun webhook signature.",
        )

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}{token}".encode("utf-8"),
        "sha256",
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature.lower()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Mailgun webhook signature.",
        )


def _form_string(form: FormData, name: str) -> str | None:
    value = form.get(name)
    if isinstance(value, str):
        return value.strip()
    return None


def _public_attachment(attachment: AttachmentMetadata) -> AttachmentProcessingSummary:
    return AttachmentProcessingSummary(
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
    )
