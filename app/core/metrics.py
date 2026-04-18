"""In-process observability metrics for the API runtime."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


@dataclass
class HttpMetricsBucket:
    """Aggregated HTTP request counters."""

    requests_total: int = 0
    errors_total: int = 0
    total_duration_ms: float = 0.0
    max_duration_ms: float = 0.0

    def record(self, *, status_code: int, duration_seconds: float) -> None:
        duration_ms = max(duration_seconds, 0.0) * 1000
        self.requests_total += 1
        if status_code >= 500:
            self.errors_total += 1
        self.total_duration_ms += duration_ms
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)

    def snapshot(self) -> dict[str, float | int]:
        average_duration_ms = (
            self.total_duration_ms / self.requests_total
            if self.requests_total
            else 0.0
        )
        return {
            "requests_total": self.requests_total,
            "errors_total": self.errors_total,
            "total_duration_ms": round(self.total_duration_ms, 3),
            "average_duration_ms": round(average_duration_ms, 3),
            "max_duration_ms": round(self.max_duration_ms, 3),
        }


@dataclass
class OpenAIMetricsBucket:
    """Aggregated OpenAI request counters without storing prompt contents."""

    calls_total: int = 0
    calls_succeeded: int = 0
    calls_failed: int = 0
    input_items_total: int = 0
    input_text_chars_total: int = 0
    request_payload_chars_total: int = 0
    response_text_chars_total: int = 0
    prompt_tokens_total: int = 0
    completion_tokens_total: int = 0
    total_tokens_total: int = 0

    def record(
        self,
        *,
        success: bool,
        input_items: int,
        input_text_chars: int,
        request_payload_chars: int,
        response_text_chars: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        self.calls_total += 1
        if success:
            self.calls_succeeded += 1
        else:
            self.calls_failed += 1
        self.input_items_total += max(input_items, 0)
        self.input_text_chars_total += max(input_text_chars, 0)
        self.request_payload_chars_total += max(request_payload_chars, 0)
        self.response_text_chars_total += max(response_text_chars, 0)
        self.prompt_tokens_total += max(prompt_tokens, 0)
        self.completion_tokens_total += max(completion_tokens, 0)
        self.total_tokens_total += max(total_tokens, 0)

    def snapshot(self) -> dict[str, int]:
        return {
            "calls_total": self.calls_total,
            "calls_succeeded": self.calls_succeeded,
            "calls_failed": self.calls_failed,
            "input_items_total": self.input_items_total,
            "input_text_chars_total": self.input_text_chars_total,
            "request_payload_chars_total": self.request_payload_chars_total,
            "response_text_chars_total": self.response_text_chars_total,
            "prompt_tokens_total": self.prompt_tokens_total,
            "completion_tokens_total": self.completion_tokens_total,
            "total_tokens_total": self.total_tokens_total,
        }


@dataclass
class MetricsState:
    """Mutable metrics state protected by the collector lock."""

    http_total: HttpMetricsBucket = field(default_factory=HttpMetricsBucket)
    http_by_route: dict[str, HttpMetricsBucket] = field(default_factory=dict)
    http_by_status: dict[str, int] = field(default_factory=dict)
    openai_total: OpenAIMetricsBucket = field(default_factory=OpenAIMetricsBucket)
    openai_by_operation: dict[str, OpenAIMetricsBucket] = field(default_factory=dict)
    openai_by_model: dict[str, OpenAIMetricsBucket] = field(default_factory=dict)


class MetricsCollector:
    """Thread-safe in-memory metrics collector for one API process."""

    def __init__(self) -> None:
        self.started_at = datetime.now(UTC)
        self._lock = Lock()
        self._state = MetricsState()

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record an HTTP request by route template and status code."""
        route_key = f"{method.upper()} {path}"
        status_key = str(status_code)
        with self._lock:
            self._state.http_total.record(
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            self._state.http_by_route.setdefault(route_key, HttpMetricsBucket()).record(
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            self._state.http_by_status[status_key] = (
                self._state.http_by_status.get(status_key, 0) + 1
            )

    def record_openai_call(
        self,
        *,
        operation: str,
        model: str,
        success: bool,
        input_items: int,
        input_text_chars: int,
        request_payload_chars: int,
        response_text_chars: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Record a completed or failed OpenAI SDK call."""
        model_key = model.strip() or "unknown"
        operation_key = operation.strip() or "unknown"
        with self._lock:
            for bucket in (
                self._state.openai_total,
                self._state.openai_by_operation.setdefault(
                    operation_key,
                    OpenAIMetricsBucket(),
                ),
                self._state.openai_by_model.setdefault(model_key, OpenAIMetricsBucket()),
            ):
                bucket.record(
                    success=success,
                    input_items=input_items,
                    input_text_chars=input_text_chars,
                    request_payload_chars=request_payload_chars,
                    response_text_chars=response_text_chars,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )

    def snapshot(self) -> dict[str, object]:
        """Return a serializable point-in-time metrics snapshot."""
        now = datetime.now(UTC)
        with self._lock:
            state = deepcopy(self._state)
        return {
            "status": "ok",
            "started_at": self.started_at,
            "uptime_seconds": round((now - self.started_at).total_seconds(), 3),
            "http": {
                **state.http_total.snapshot(),
                "by_route": {
                    route: bucket.snapshot()
                    for route, bucket in sorted(state.http_by_route.items())
                },
                "by_status": dict(sorted(state.http_by_status.items())),
            },
            "openai": {
                "total": state.openai_total.snapshot(),
                "by_operation": {
                    operation: bucket.snapshot()
                    for operation, bucket in sorted(state.openai_by_operation.items())
                },
                "by_model": {
                    model: bucket.snapshot()
                    for model, bucket in sorted(state.openai_by_model.items())
                },
            },
        }
