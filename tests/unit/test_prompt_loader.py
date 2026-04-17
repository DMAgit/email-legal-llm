"""Tests for YAML-backed prompt templates."""

from pathlib import Path

import pytest

from app.core.exceptions import ConfigurationError
from app.infra.llm.prompt_loader import PromptTemplate, PromptTemplateLoader


def test_prompt_loader_loads_named_yaml_prompt() -> None:
    template = PromptTemplateLoader(Path("app/infra/llm/prompts")).load("extraction_prompt_v1")

    assert template.name == "extraction_prompt_v1"
    assert "untrusted source data" in template.system
    assert template.input_variables == ["document_payload"]


def test_prompt_template_renders_user_content_separately() -> None:
    template = PromptTemplateLoader(Path("app/infra/llm/prompts")).load("extraction_prompt_v1")

    rendered = template.render_user(document_payload='{"document_text":"Vendor: Acme Corp"}')

    assert "<document_payload>" in rendered
    assert '{"document_text":"Vendor: Acme Corp"}' in rendered
    assert "You extract structured contract data" not in rendered


def test_prompt_template_rejects_undeclared_placeholders() -> None:
    with pytest.raises(ValueError, match="undeclared input variables"):
        PromptTemplate(
            name="bad_prompt",
            version="1.0",
            system="System instructions.",
            user="Payload: {missing_payload}",
            input_variables=[],
        )


def test_prompt_template_reports_missing_render_values() -> None:
    template = PromptTemplateLoader(Path("app/infra/llm/prompts")).load("classification_prompt_v1")

    with pytest.raises(ConfigurationError, match="classification_payload"):
        template.render_user()
