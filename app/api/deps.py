"""FastAPI dependencies shared by API endpoints."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.model_registry import ModelRegistry
from app.infra.db.repository import PersistenceRepository


def get_model_registry(request: Request) -> ModelRegistry:
    """Return the application-level model registry."""
    return request.app.state.model_registry


SettingsDep = Annotated[Settings, Depends(get_settings)]
ModelRegistryDep = Annotated[ModelRegistry, Depends(get_model_registry)]


def get_persistence_repository(settings: SettingsDep) -> Iterator[PersistenceRepository]:
    """Return a request-scoped persistence repository."""
    repository = PersistenceRepository(settings.database_url)
    try:
        yield repository
    finally:
        repository.close()


PersistenceRepositoryDep = Annotated[PersistenceRepository, Depends(get_persistence_repository)]
