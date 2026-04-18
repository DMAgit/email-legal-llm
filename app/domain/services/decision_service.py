"""Compatibility wrapper for the deterministic decision service."""

from app.services.decision_service import (
    DEFAULT_CLASSIFICATION_CONFIDENCE_THRESHOLD,
    DecisionService,
)

__all__ = ["DEFAULT_CLASSIFICATION_CONFIDENCE_THRESHOLD", "DecisionService"]
