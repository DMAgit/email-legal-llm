"""Structured logging helpers for local development and service startup."""

import logging
from collections.abc import Mapping
from typing import Any


LOG_CONTEXT_FIELDS = ("process_id", "document_id", "stage", "context_filename")
LOG_CONTEXT_ALIASES = {"filename": "context_filename"}


class LoggingContextFilter(logging.Filter):
    """Ensure log records always include the standard workflow context fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add placeholder values for missing workflow context fields."""
        for field in LOG_CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, "-")
        return True


class ContextLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that carries process, document, stage, and filename context."""

    def process(
        self,
        msg: str,
        kwargs: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """Merge adapter context with per-call logging context."""
        adapter_extra = _normalize_context(self.extra)
        call_extra = kwargs.get("extra", {})
        if isinstance(call_extra, Mapping):
            adapter_extra.update(_normalize_extra(call_extra))
        kwargs["extra"] = adapter_extra
        return msg, kwargs


def configure_logging(level: str) -> None:
    """Configure stdout logging with compact workflow context fields."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "process_id=%(process_id)s document_id=%(document_id)s "
            "stage=%(stage)s filename=%(context_filename)s %(message)s"
        ),
        force=True,
    )
    context_filter = LoggingContextFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(context_filter)


def get_logger(name: str, **context: str | None) -> ContextLoggerAdapter:
    """Return a logger adapter with optional workflow context."""
    return ContextLoggerAdapter(logging.getLogger(name), _normalize_context(context))


def _normalize_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Return standard context fields plus any extra logging metadata."""
    normalized = {field: "-" for field in LOG_CONTEXT_FIELDS}
    normalized.update(_normalize_extra(context))
    return normalized


def _normalize_extra(context: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize caller-provided extra values without resetting defaults."""
    return {
        LOG_CONTEXT_ALIASES.get(key, key): value
        for key, value in context.items()
        if value is not None
    }
