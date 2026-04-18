"""API response models for foundation diagnostics."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health response with non-secret runtime details."""

    status: Literal["ok"]
    app_name: str
    environment: str
    model_configs: list[str]


class ModelRegistryResponse(BaseModel):
    """Public view of YAML-backed model configurations."""

    configs: dict[str, dict[str, Any]]


class HttpMetricsBucket(BaseModel):
    """Aggregated HTTP request metrics."""

    requests_total: int
    errors_total: int
    total_duration_ms: float
    average_duration_ms: float
    max_duration_ms: float


class OpenAIMetricsBucket(BaseModel):
    """Aggregated OpenAI call metrics."""

    calls_total: int
    calls_succeeded: int
    calls_failed: int
    input_items_total: int
    input_text_chars_total: int
    request_payload_chars_total: int
    response_text_chars_total: int
    prompt_tokens_total: int
    completion_tokens_total: int
    total_tokens_total: int


class HttpMetricsResponse(HttpMetricsBucket):
    """HTTP metrics grouped by status and route."""

    by_route: dict[str, HttpMetricsBucket]
    by_status: dict[str, int]


class OpenAIMetricsResponse(BaseModel):
    """OpenAI metrics grouped by operation and model."""

    total: OpenAIMetricsBucket
    by_operation: dict[str, OpenAIMetricsBucket]
    by_model: dict[str, OpenAIMetricsBucket]


class MetricsResponse(BaseModel):
    """In-process observability metrics for this API worker."""

    status: Literal["ok"]
    started_at: datetime
    uptime_seconds: float
    http: HttpMetricsResponse
    openai: OpenAIMetricsResponse
