"""Risk classification result models."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import RiskLevel, RoutingAction


class PolicyConflict(BaseModel):
    """A concrete conflict between an extracted clause and retrieved policy."""

    clause_type: str = Field(
        description="Canonical clause type, such as payment_terms, liability, or data_usage."
    )
    issue: str = Field(description="Specific policy issue grounded in extracted text and context.")


class ClauseEvaluation(BaseModel):
    """Risk assessment for one extracted contract clause."""

    risk: RiskLevel
    reason: str = Field(description="Concise evidence-based reason for the clause risk.")


class ClauseEvaluationItem(ClauseEvaluation):
    """Strict-schema friendly clause evaluation returned by the LLM."""

    clause_type: str = Field(
        description="Canonical clause type, such as payment_terms, liability, or data_usage."
    )


class ClassificationResult(BaseModel):
    """Structured risk classification returned by the classifier."""

    risk_level: RiskLevel
    policy_conflicts: list[PolicyConflict] = Field(default_factory=list)
    recommended_action: RoutingAction
    rationale: list[str]
    clause_evaluations: dict[str, ClauseEvaluation] = Field(default_factory=dict)
    final_confidence: float = Field(ge=0.0, le=1.0)

    @classmethod
    def openai_json_schema(cls) -> dict[str, Any]:
        """Return a strict-output-friendly schema for dynamic clause keys.

        OpenAI strict JSON schema does not support arbitrary object maps like
        dict[str, ClauseEvaluation]. The runtime model keeps the API-friendly
        keyed object, while the LLM-facing schema asks for a list of typed
        clause evaluation items and the validator below folds it back.
        """
        schema = super().model_json_schema()
        clause_item_schema = ClauseEvaluationItem.model_json_schema(
            ref_template="#/$defs/{model}"
        )
        clause_item_schema.pop("$defs", None)
        schema.setdefault("$defs", {})["ClauseEvaluationItem"] = clause_item_schema
        schema.setdefault("properties", {})["clause_evaluations"] = {
            "title": "Clause Evaluations",
            "description": "Clause evaluations keyed by clause_type in application output.",
            "type": "array",
            "items": {"$ref": "#/$defs/ClauseEvaluationItem"},
        }
        return schema

    @field_validator("policy_conflicts", mode="before")
    @classmethod
    def _normalize_policy_conflicts(cls, value: Any) -> Any:
        """Accept legacy string conflicts while emitting structured conflicts."""
        if value is None:
            return []
        if not isinstance(value, list):
            return value

        normalized: list[Any] = []
        for conflict in value:
            if isinstance(conflict, str):
                normalized.append({"clause_type": "general", "issue": conflict})
            else:
                normalized.append(conflict)
        return normalized

    @field_validator("rationale", mode="before")
    @classmethod
    def _normalize_rationale(cls, value: Any) -> Any:
        """Accept the previous single-string rationale shape."""
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("clause_evaluations", mode="before")
    @classmethod
    def _normalize_clause_evaluations(cls, value: Any) -> Any:
        """Accept LLM array items and fold them into the keyed API shape."""
        if value is None:
            return {}
        if not isinstance(value, list):
            return value

        normalized: dict[str, Any] = {}
        for item in value:
            if isinstance(item, ClauseEvaluationItem):
                normalized[item.clause_type] = {
                    "risk": item.risk,
                    "reason": item.reason,
                }
                continue
            if not isinstance(item, dict):
                continue
            clause_type = str(item.get("clause_type", "")).strip()
            if not clause_type:
                continue
            normalized[clause_type] = {
                "risk": item.get("risk"),
                "reason": item.get("reason"),
            }
        return normalized

