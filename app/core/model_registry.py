"""YAML-backed LLM model configuration registry."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Validated LLM configuration loaded from a YAML file."""

    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    timeout_seconds: int | None = Field(default=None, gt=0)
    response_schema: str | None = None
    prompt_template: str | None = None


class ModelRegistry:
    """Load, validate, and serve named model configurations."""

    def __init__(self, configs: dict[str, ModelConfig]) -> None:
        """Initialize the registry with validated model configs."""
        self._configs = configs

    @classmethod
    def from_directory(cls, config_dir: Path) -> "ModelRegistry":
        """Load every YAML model config from a directory."""
        if not config_dir.exists():
            raise FileNotFoundError(f"Model config directory does not exist: {config_dir}")

        configs: dict[str, ModelConfig] = {}
        for path in sorted([*config_dir.glob("*.yaml"), *config_dir.glob("*.yml")]):
            raw_config = cls._read_yaml(path)
            config = ModelConfig.model_validate(raw_config)
            if config.name in configs:
                raise ValueError(f"Duplicate model config name: {config.name}")
            configs[config.name] = config

        if not configs:
            raise ValueError(f"No model config files found in {config_dir}")
        return cls(configs)

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        """Read a YAML file and ensure it contains a mapping."""
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        if not isinstance(data, dict):
            raise ValueError(f"Model config must be a mapping: {path}")
        return data

    def get(self, name: str) -> ModelConfig:
        """Return a model config by name."""
        try:
            return self._configs[name]
        except KeyError as exc:
            raise KeyError(f"Unknown model config: {name}") from exc

    def names(self) -> list[str]:
        """Return model config names in stable order."""
        return sorted(self._configs)

    def public_configs(self) -> dict[str, dict[str, Any]]:
        """Return serializable config values safe for diagnostic endpoints."""
        return {
            name: config.model_dump()
            for name, config in sorted(self._configs.items())
        }

