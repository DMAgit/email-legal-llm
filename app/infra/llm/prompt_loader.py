"""YAML-backed prompt templates for LLM requests."""

from __future__ import annotations

from pathlib import Path
from string import Formatter

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.core.exceptions import ConfigurationError


class PromptTemplate(BaseModel):
    """Validated prompt template with separate system and user messages."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str | None = None
    system: str = Field(min_length=1)
    user: str = Field(min_length=1)
    input_variables: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_declared_variables(self) -> "PromptTemplate":
        """Ensure user-message placeholders are declared explicitly."""
        placeholders = {
            field_name
            for _literal, field_name, _format_spec, _conversion in Formatter().parse(self.user)
            if field_name
        }
        undeclared = placeholders - set(self.input_variables)
        if undeclared:
            joined = ", ".join(sorted(undeclared))
            raise ValueError(f"Prompt template has undeclared input variables: {joined}")
        return self

    def render_user(self, **values: str) -> str:
        """Render the user message with explicit content insertion values."""
        missing = [name for name in self.input_variables if name not in values]
        if missing:
            joined = ", ".join(sorted(missing))
            raise ConfigurationError(f"Missing prompt input variables: {joined}")
        return self.user.format(**values)


class PromptTemplateLoader:
    """Load named prompt templates from YAML files in a prompt directory."""

    def __init__(self, prompt_dir: Path) -> None:
        self.prompt_dir = prompt_dir

    def load(self, template_name: str) -> PromptTemplate:
        """Load a prompt template by configured name."""
        candidates = self._candidate_paths(template_name)
        for path in candidates:
            if not path.exists():
                continue
            template = self._read_prompt(path)
            if template.name == template_name or path.stem == template_name:
                return template

        for path in sorted([*self.prompt_dir.glob("*.yaml"), *self.prompt_dir.glob("*.yml")]):
            template = self._read_prompt(path)
            if template.name == template_name:
                return template

        raise ConfigurationError(f"Prompt template not found: {template_name}")

    def _candidate_paths(self, template_name: str) -> list[Path]:
        base_name = template_name.removesuffix("_v1")
        return [
            self.prompt_dir / f"{template_name}.yaml",
            self.prompt_dir / f"{template_name}.yml",
            self.prompt_dir / f"{base_name}.yaml",
            self.prompt_dir / f"{base_name}.yml",
        ]

    def _read_prompt(self, path: Path) -> PromptTemplate:
        try:
            with path.open("r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML prompt template: {path}") from exc
        except OSError as exc:
            raise ConfigurationError(f"Could not read prompt template: {path}") from exc

        if not isinstance(data, dict):
            raise ConfigurationError(f"Prompt template must be a mapping: {path}")

        try:
            return PromptTemplate.model_validate(data)
        except ValidationError as exc:
            raise ConfigurationError(f"Invalid prompt template in {path}: {exc}") from exc


def prompt_messages(template: PromptTemplate, **values: str) -> list[dict[str, str]]:
    """Return chat messages for an LLM request from a rendered prompt template."""
    return [
        {"role": "system", "content": template.system},
        {"role": "user", "content": template.render_user(**values)},
    ]
