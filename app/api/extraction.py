"""Structured extraction endpoints for parsed documents."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import MetricsCollectorDep, ModelRegistryDep, SettingsDep
from app.domain.models.document import ParsedDocument
from app.domain.models.extraction import DocumentExtraction
from app.infra.llm.openai_client import OpenAIClient, OpenAIClientConfigurationError
from app.services.extraction_service import ExtractionError, ExtractionService

router = APIRouter(prefix="/extractions", tags=["extractions"])


@router.post(
    "/contract",
    response_model=DocumentExtraction,
    status_code=status.HTTP_200_OK,
)
def extract_contract(
    document: ParsedDocument,
    settings: SettingsDep,
    registry: ModelRegistryDep,
    metrics_collector: MetricsCollectorDep,
) -> DocumentExtraction:
    """Extract structured contract fields from parsed document text."""
    try:
        client = OpenAIClient(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            metrics_collector=metrics_collector,
        )
    except OpenAIClientConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    service = ExtractionService(
        model_registry=registry,
        prompt_dir=settings.prompt_dir,
        llm_client=client,
    )
    try:
        extraction = service.extract_document(document)
    except ExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return DocumentExtraction(
        document_id=document.document_id,
        filename=document.filename,
        extraction=extraction,
    )
