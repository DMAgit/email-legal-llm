"""Contract field extraction result models."""

from pydantic import BaseModel, Field


class ContractExtractionResult(BaseModel):
    """Structured contract fields extracted from parsed text."""

    vendor_name: str | None = None
    contract_type: str | None = None
    payment_terms: str | None = None
    liability_clause: str | None = None
    termination_clause: str | None = None
    renewal_clause: str | None = None
    governing_law: str | None = None
    data_usage_clause: str | None = None
    key_missing_fields: list[str] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0.0, le=1.0)

