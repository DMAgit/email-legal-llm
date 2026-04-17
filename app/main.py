"""FastAPI application entrypoint for the contract risk analyzer."""

from fastapi import FastAPI

from app.api.router import router
from app.core.config import get_settings
from app.core.logging import configure_logging
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
    app.include_router(router)
    return app


app = create_app()

