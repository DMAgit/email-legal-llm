"""Tests for YAML-backed model registry loading."""

from pathlib import Path

import pytest

from app.core.exceptions import ModelConfigError
from app.core.model_registry import ModelRegistry


def test_model_registry_loads_yaml_configs() -> None:
    registry = ModelRegistry.from_directory(Path("config/models"))

    assert registry.names() == ["classification", "extraction"]
    assert registry.get("extraction").model == "gpt-4o-mini"


def test_model_registry_rejects_unknown_name() -> None:
    registry = ModelRegistry.from_directory(Path("config/models"))

    with pytest.raises(KeyError):
        registry.get("missing")


def test_model_registry_rejects_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("name: [", encoding="utf-8")

    with pytest.raises(ModelConfigError, match="Invalid YAML model config"):
        ModelRegistry.from_directory(tmp_path)


def test_model_registry_rejects_missing_required_fields(tmp_path: Path) -> None:
    (tmp_path / "incomplete.yaml").write_text("name: extraction\n", encoding="utf-8")

    with pytest.raises(ModelConfigError, match="Invalid model config"):
        ModelRegistry.from_directory(tmp_path)
