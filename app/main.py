"""FastAPI application entrypoint for the contract risk analyzer."""

from time import perf_counter

from fastapi import FastAPI
from starlette.requests import Request

from app.api.router import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.metrics import MetricsCollector
from app.core.model_registry import ModelRegistry


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Email-driven contract risk analyzer API.",
    )
    app.state.settings = settings
    app.state.model_registry = ModelRegistry.from_directory(settings.model_config_dir)
    app.state.metrics_collector = MetricsCollector()

    @app.middleware("http")
    async def collect_http_metrics(request: Request, call_next):
        start = perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            status_code = response.status_code if response is not None else 500
            app.state.metrics_collector.record_http_request(
                method=request.method,
                path=path,
                status_code=status_code,
                duration_seconds=perf_counter() - start,
            )

    app.include_router(router)
    return app


app = create_app()

