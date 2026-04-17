"""Retrieved policy context models."""

from pydantic import BaseModel


class RetrievedContextChunk(BaseModel):
    """A policy or clause-library chunk retrieved for classification context."""

    chunk_id: str
    source: str
    doc_type: str
    clause_type: str | None = None
    content: str
    score: float

