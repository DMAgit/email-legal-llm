"""Retrieved policy context models."""

from pydantic import BaseModel, Field


class RetrievedContextChunk(BaseModel):
    """A policy or clause-library chunk retrieved for classification context."""

    chunk_id: str
    source: str
    doc_type: str
    clause_type: str | None = None
    content: str
    score: float = Field(ge=0.0)


class RetrievalResult(BaseModel):
    """Retrieved chunks plus non-fatal retrieval warnings."""

    chunks: list[RetrievedContextChunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
