"""Tests for YAML-backed model registry loading."""

from pathlib import Path

import pytest

from app.core.model_registry import ModelRegistry


def test_model_registry_loads_yaml_configs() -> None:
    registry = ModelRegistry.from_directory(Path("config/models"))

    assert registry.names() == ["classification", "extraction"]
    assert registry.get("extraction").model == "gpt-4o-mini"


def test_model_registry_rejects_unknown_name() -> None:
    registry = ModelRegistry.from_directory(Path("config/models"))

    with pytest.raises(KeyError):
        registry.get("missing")
