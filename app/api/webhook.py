"""Inbound webhook endpoints."""

import hmac
import time

from fastapi import APIRouter, HTTPException, Request, status
from starlette.datastructures import FormData

from app.api.deps import ModelRegistryDep, SettingsDep
from app.core.exceptions import ClassificationError, OpenAIClientError, RetrievalError, SearchClientError
from app.domain.enums import ProcessingStage, ProcessingStatus, RoutingAction
from app.domain.models.classification import ClassificationResult
from app.domain.models.email import AttachmentMetadata
from app.domain.models.extraction import DocumentExtraction, DocumentExtractionError
from app.domain.models.ingestion import AttachmentProcessingSummary, InboundEmailProcessingResult
from app.domain.models.persistence import DocumentEvaluation, ProcessingOutcome
from app.domain.models.retrieval import RetrievedContextChunk
from app.infra.db.repository import PersistenceRepository
from app.infra.llm.embedding_client import OpenAIEmbeddingClient
from app.infra.llm.openai_client import OpenAIClient, OpenAIClientConfigurationError
from app.infra.search.azure_search_client import AzureSearchClient
from app.services.classification_service import ClassificationService
from app.services.decision_service import DecisionService
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionError, IngestionService
from app.services.parsing_service import ParsingService
from app.services.persistence_service import PersistenceService
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
MAILGUN_SIGNATURE_MAX_AGE_SECONDS = 15 * 60


@router.post(
    "/mailgun/inbound",
    response_model=InboundEmailProcessingResult,
    status_code=status.HTTP_200_OK,
)
async def mailgun_inbound(
    request: Request,
    settings: SettingsDep,
    registry: ModelRegistryDep,
    extract: bool = False,
    classify: bool = False,
) -> InboundEmailProcessingResult:
    """Receive a Mailgun inbound email webhook and optionally run the risk workflow."""
    if classify:
        extract = True

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
    retrieved_contexts: list[RetrievedContextChunk] = []
    classification: ClassificationResult | None = None
    classification_error: str | None = None
    outcome: ProcessingOutcome | None = None
    document_evaluations: list[DocumentEvaluation] = []

    try:
        ingested = await ingestion_service.ingest_mailgun_form(form)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    repository = PersistenceRepository(settings.database_url)
    persistence_service = PersistenceService(repository)
    try:
        persistence_service.save_received(
            process_id=ingested.process_id,
            email=ingested.email,
            attachments=ingested.attachments,
        )

        repository.update_processing_run(
            ingested.process_id,
            status=ProcessingStage.PARSING.value,
            current_stage=ProcessingStage.PARSING.value,
        )
        documents, errors = parsing_service.parse_attachments(ingested.attachments)
        persistence_service.save_parsing_result(
            process_id=ingested.process_id,
            documents=documents,
            errors=errors,
        )

        extractions: list[DocumentExtraction] = []
        extraction_errors: list[DocumentExtractionError] = []

        if extract and not documents:
            persistence_service.save_failed_run(
                process_id=ingested.process_id,
                current_stage=ProcessingStage.PARSING.value,
                error_type="DocumentParseError",
                error_message=_join_error_messages(error.error for error in errors)
                or "No parsed documents were available for extraction.",
            )

        if extract and documents:
            repository.update_processing_run(
                ingested.process_id,
                status=ProcessingStage.EXTRACTING.value,
                current_stage=ProcessingStage.EXTRACTING.value,
            )
            try:
                extraction_service = ExtractionService(
                    model_registry=registry,
                    prompt_dir=settings.prompt_dir,
                    llm_client=OpenAIClient(
                        api_key=settings.openai_api_key,
                        base_url=settings.openai_base_url,
                    ),
                )
                extractions, extraction_errors = extraction_service.extract_documents(documents)
            except OpenAIClientConfigurationError as exc:
                extraction_errors = [
                    DocumentExtractionError(
                        document_id=document.document_id,
                        filename=document.filename,
                        error=str(exc),
                    )
                    for document in documents
                ]

            persistence_service.save_extraction_result(
                process_id=ingested.process_id,
                extractions=extractions,
                errors=extraction_errors,
            )
            if extraction_errors and not extractions:
                persistence_service.save_failed_run(
                    process_id=ingested.process_id,
                    current_stage=ProcessingStage.EXTRACTING.value,
                    error_type="DocumentExtractionError",
                    error_message=_join_error_messages(error.error for error in extraction_errors),
                )

        if classify and extractions:
            active_extraction = extractions[0]
            try:
                embedding_client = OpenAIEmbeddingClient(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                    model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                )
                search_client = AzureSearchClient(
                    endpoint=settings.azure_search_endpoint,
                    api_key=settings.azure_search_api_key,
                    index_name=settings.azure_search_index_name,
                    embedding_client=embedding_client,
                )
                retrieval_service = RetrievalService(search_client=search_client)
                classification_service = ClassificationService(
                    model_registry=registry,
                    prompt_dir=settings.prompt_dir,
                    llm_client=OpenAIClient(
                        api_key=settings.openai_api_key,
                        base_url=settings.openai_base_url,
                    ),
                )
                decision_service = DecisionService()
                document_outcomes: list[ProcessingOutcome] = []

                for document_extraction in extractions:
                    active_extraction = document_extraction
                    repository.update_processing_run(
                        ingested.process_id,
                        status=ProcessingStage.RETRIEVING.value,
                        current_stage=ProcessingStage.RETRIEVING.value,
                    )
                    retrieval_result = retrieval_service.retrieve_for_extraction(
                        document_extraction.extraction
                    )
                    retrieved_contexts.extend(retrieval_result.chunks)
                    repository.save_retrieved_contexts(
                        ingested.process_id,
                        document_extraction.document_id,
                        retrieval_result.chunks,
                    )

                    repository.update_processing_run(
                        ingested.process_id,
                        status=ProcessingStage.CLASSIFYING.value,
                        current_stage=ProcessingStage.CLASSIFYING.value,
                    )
                    document_classification = classification_service.classify_retrieval_result(
                        document_extraction.extraction,
                        retrieval_result,
                    )

                    repository.update_processing_run(
                        ingested.process_id,
                        status=ProcessingStage.DECIDING.value,
                        current_stage=ProcessingStage.DECIDING.value,
                    )
                    document_outcome = decision_service.build_outcome(
                        process_id=ingested.process_id,
                        extraction=document_extraction.extraction,
                        classification=document_classification,
                        retrieved_context_available=bool(retrieval_result.chunks),
                    )
                    document_outcomes.append(document_outcome)
                    document_evaluation = _document_evaluation_from_outcome(
                        process_id=ingested.process_id,
                        document_extraction=document_extraction,
                        retrieved_contexts=retrieval_result.chunks,
                        outcome=document_outcome,
                    )
                    document_evaluations.append(document_evaluation)
                    persistence_service.save_document_evaluation(document_evaluation)

                if extraction_errors and document_outcomes:
                    document_outcomes.append(
                        decision_service.build_outcome(
                            process_id=ingested.process_id,
                            extraction=document_outcomes[0].extraction,
                            classification=document_outcomes[0].classification,
                            errors=[error.error for error in extraction_errors],
                        )
                    )

                outcome = _select_overall_outcome(document_outcomes)
                classification = outcome.classification
                persistence_service.save_processing_result(
                    process_id=ingested.process_id,
                    classification=classification,
                    outcome=outcome,
                )
            except (OpenAIClientError, SearchClientError, RetrievalError, ClassificationError) as exc:
                classification_error = str(exc)
                process_record = repository.get_process(ingested.process_id)
                persistence_service.save_failed_run(
                    process_id=ingested.process_id,
                    current_stage=(
                        process_record.current_stage
                        if process_record is not None
                        else ProcessingStage.CLASSIFYING.value
                    ),
                    error_type=exc.__class__.__name__,
                    error_message=classification_error,
                )
                outcome = DecisionService().build_outcome(
                    process_id=ingested.process_id,
                    extraction=active_extraction.extraction,
                    classification=None,
                    errors=[classification_error],
                    failed=True,
                )
                persistence_service.save_outcome(
                    process_id=ingested.process_id,
                    outcome=outcome,
                )

        if not extract:
            if documents or not errors:
                persistence_service.mark_completed_without_decision(
                    ingested.process_id,
                    ProcessingStage.PARSING.value,
                )
        elif extractions and not classify:
            persistence_service.mark_completed_without_decision(
                ingested.process_id,
                ProcessingStage.EXTRACTING.value,
            )
    finally:
        repository.close()

    return InboundEmailProcessingResult(
        process_id=ingested.process_id,
        email=ingested.email,
        attachments=[_public_attachment(attachment) for attachment in ingested.attachments],
        documents=documents,
        extractions=extractions,
        extraction_errors=extraction_errors,
        retrieved_contexts=retrieved_contexts,
        classification=classification,
        classification_error=classification_error,
        outcome=outcome,
        document_evaluations=document_evaluations,
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


def _document_evaluation_from_outcome(
    *,
    process_id: str,
    document_extraction: DocumentExtraction,
    retrieved_contexts: list[RetrievedContextChunk],
    outcome: ProcessingOutcome,
) -> DocumentEvaluation:
    return DocumentEvaluation(
        process_id=process_id,
        document_id=document_extraction.document_id,
        filename=document_extraction.filename,
        extraction=document_extraction.extraction,
        retrieved_contexts=retrieved_contexts,
        classification=outcome.classification,
        status=outcome.status,
        review_required=outcome.review_required,
        final_action=outcome.final_action,
        decision_reason=outcome.decision_reason,
        errors=outcome.errors,
    )


def _select_overall_outcome(outcomes: list[ProcessingOutcome]) -> ProcessingOutcome:
    return max(outcomes, key=_outcome_priority)


def _outcome_priority(outcome: ProcessingOutcome) -> int:
    if outcome.status == ProcessingStatus.FAILED:
        return 100
    return {
        RoutingAction.LEGAL_REVIEW: 90,
        RoutingAction.PROCUREMENT_REVIEW: 80,
        RoutingAction.MANUAL_REVIEW: 70,
        RoutingAction.AUTO_STORE: 0,
        None: 0,
    }[outcome.final_action]


def _join_error_messages(errors: object) -> str:
    return "; ".join(str(error) for error in errors if str(error))
