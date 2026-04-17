"""Logging configuration for local development and service startup."""

import logging


def configure_logging(level: str) -> None:
    """Configure stdout logging with a compact, consistent format."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

