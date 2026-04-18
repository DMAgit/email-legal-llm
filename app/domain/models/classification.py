"""Risk classification result models."""

from pydantic import BaseModel, Field

from app.domain.enums import RiskLevel, RoutingAction


class ClassificationResult(BaseModel):
    """Structured risk classification returned by the classifier."""

    risk_level: RiskLevel
    policy_conflicts: list[str] = Field(default_factory=list)
    recommended_action: RoutingAction
    rationale: str
    final_confidence: float = Field(ge=0.0, le=1.0)

