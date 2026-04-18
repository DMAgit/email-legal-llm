"""Application routes for foundation health and configuration checks."""

from fastapi import APIRouter

from app.api.deps import MetricsCollectorDep, ModelRegistryDep, SettingsDep
from app.api.extraction import router as extraction_router
from app.api.processes import router as processes_router
from app.api.webhook import router as webhook_router
from app.domain.models.system import HealthResponse, MetricsResponse, ModelRegistryResponse

router = APIRouter()
router.include_router(extraction_router)
router.include_router(processes_router)
router.include_router(webhook_router)


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep, registry: ModelRegistryDep) -> HealthResponse:
    """Report basic runtime health without exposing secrets."""
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.app_env,
        model_configs=registry.names(),
    )


@router.get("/model-configs", response_model=ModelRegistryResponse)
def model_configs(registry: ModelRegistryDep) -> ModelRegistryResponse:
    """Return loaded YAML model configuration names and public values."""
    return ModelRegistryResponse(configs=registry.public_configs())


@router.get("/metrics", response_model=MetricsResponse)
def metrics(metrics_collector: MetricsCollectorDep) -> MetricsResponse:
    """Return in-process API and OpenAI usage metrics."""
    return MetricsResponse.model_validate(metrics_collector.snapshot())
