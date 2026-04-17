"""Shared domain enumerations."""

from enum import StrEnum


class RiskLevel(StrEnum):
    """Contract risk levels produced by classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RoutingAction(StrEnum):
    """Deterministic routing actions used after risk classification."""

    AUTO_STORE = "auto_store"
    PROCUREMENT_REVIEW = "procurement_review"
    LEGAL_REVIEW = "legal_review"
    MANUAL_REVIEW = "manual_review"


class ProcessingStatus(StrEnum):
    """Lifecycle status for a contract processing run."""

    COMPLETED = "completed"
    FLAGGED = "flagged"
    FAILED = "failed"

