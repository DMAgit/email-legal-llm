"""Regression tests for shared M1 foundation conventions."""

import logging

import pytest

from app.core.exceptions import (
    ApplicationError,
    ConfigurationError,
    ExternalServiceError,
    ExtractionError,
    IngestionError,
    OpenAIClientConfigurationError,
    OpenAIClientError,
    ParserDependencyError,
    ParserError,
    PersistenceError,
    UnsupportedFileTypeError,
)
from app.core.logging import LoggingContextFilter, get_logger


def test_existing_exception_boundaries_use_core_taxonomy() -> None:
    from app.infra.llm.openai_client import OpenAIClientConfigurationError as LLMConfigError
    from app.infra.llm.openai_client import OpenAIClientError as LLMError
    from app.infra.parsers.exceptions import ParserDependencyError as ParserDependency
    from app.infra.parsers.exceptions import UnsupportedFileTypeError as ParserUnsupported
    from app.services.extraction_service import ExtractionError as ServiceExtractionError
    from app.services.ingestion_service import IngestionError as ServiceIngestionError

    assert issubclass(ConfigurationError, ApplicationError)
    assert issubclass(PersistenceError, ApplicationError)
    assert issubclass(ParserError, ApplicationError)
    assert issubclass(ParserDependencyError, ParserError)
    assert issubclass(UnsupportedFileTypeError, ParserError)
    assert issubclass(ExternalServiceError, ApplicationError)
    assert issubclass(OpenAIClientError, ExternalServiceError)
    assert issubclass(OpenAIClientConfigurationError, ConfigurationError)

    assert ServiceIngestionError is IngestionError
    assert ServiceExtractionError is ExtractionError
    assert ParserDependency is ParserDependencyError
    assert ParserUnsupported is UnsupportedFileTypeError
    assert LLMError is OpenAIClientError
    assert LLMConfigError is OpenAIClientConfigurationError


def test_logging_context_filter_adds_workflow_defaults() -> None:
    record = logging.LogRecord(
        name="tests.logging",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    assert LoggingContextFilter().filter(record) is True
    assert record.process_id == "-"
    assert record.document_id == "-"
    assert record.stage == "-"
    assert record.context_filename == "-"


def test_context_logger_adapter_merges_workflow_context() -> None:
    logger = get_logger("tests.logging", process_id="process-1", stage="parse")

    _message, kwargs = logger.process(
        "message",
        {"extra": {"document_id": "document-1", "filename": "contract.csv"}},
    )

    assert kwargs["extra"]["process_id"] == "process-1"
    assert kwargs["extra"]["document_id"] == "document-1"
    assert kwargs["extra"]["stage"] == "parse"
    assert kwargs["extra"]["context_filename"] == "contract.csv"
