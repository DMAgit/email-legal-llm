"""FastAPI dependencies shared by API endpoints."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.model_registry import ModelRegistry


def get_model_registry(request: Request) -> ModelRegistry:
    """Return the application-level model registry."""
    return request.app.state.model_registry


SettingsDep = Annotated[Settings, Depends(get_settings)]
ModelRegistryDep = Annotated[ModelRegistry, Depends(get_model_registry)]

