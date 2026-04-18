"""API response models for foundation diagnostics."""

from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health response with non-secret runtime details."""

    status: Literal["ok"]
    app_name: str
    environment: str
    model_configs: list[str]


class ModelRegistryResponse(BaseModel):
    """Public view of YAML-backed model configurations."""

    configs: dict[str, dict[str, Any]]

