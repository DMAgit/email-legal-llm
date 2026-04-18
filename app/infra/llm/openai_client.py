"""OpenAI client adapter for structured LLM responses."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.exceptions import OpenAIClientConfigurationError, OpenAIClientError
from app.core.metrics import MetricsCollector
from app.core.model_registry import ModelConfig

SchemaModel = TypeVar("SchemaModel", bound=BaseModel)


class OpenAIClient:
    """Small adapter around the OpenAI SDK for JSON-schema constrained output."""

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        client: Any | None = None,
        metrics_collector: MetricsCollector | None = None,
    ) -> None:
        """Initialize the OpenAI SDK client or accept a test double."""
        self._client = client
        self._metrics_collector = metrics_collector
        if self._client is not None:
            return

        if not api_key or not api_key.strip():
            raise OpenAIClientConfigurationError("OPENAI_API_KEY is required for extraction.")

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise OpenAIClientConfigurationError(
                "The openai package is required. Install requirements before running extraction."
            ) from exc

        kwargs: dict[str, str] = {"api_key": api_key}
        if base_url and base_url.strip():
            kwargs["base_url"] = base_url.strip()
        self._client = OpenAI(**kwargs)

    def create_structured_output(
        self,
        *,
        model_config: ModelConfig,
        system_prompt: str,
        user_content: str,
        schema_model: type[SchemaModel],
    ) -> dict[str, Any]:
        """Call OpenAI and return decoded JSON matching the supplied schema shape."""
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_model.__name__,
                "strict": True,
                "schema": _strict_json_schema(schema_model),
            },
        }

        request: dict[str, Any] = {
            "model": model_config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": model_config.temperature,
            "response_format": response_format,
        }
        if model_config.max_output_tokens is not None:
            request["max_tokens"] = model_config.max_output_tokens
        if model_config.timeout_seconds is not None:
            request["timeout"] = model_config.timeout_seconds

        input_text_chars = len(system_prompt) + len(user_content)
        request_payload_chars = _json_chars(request)
        try:
            response = self._client.chat.completions.create(**request)
        except Exception as exc:
            self._record_chat_completion(
                model=model_config.model,
                success=False,
                input_text_chars=input_text_chars,
                request_payload_chars=request_payload_chars,
            )
            raise OpenAIClientError(f"OpenAI request failed: {exc}") from exc

        usage = _usage_values(response)
        response_text_chars = _chat_response_text_chars(response)
        try:
            decoded = self._decode_chat_completion(response)
        except OpenAIClientError:
            self._record_chat_completion(
                model=model_config.model,
                success=False,
                input_text_chars=input_text_chars,
                request_payload_chars=request_payload_chars,
                response_text_chars=response_text_chars,
                usage=usage,
            )
            raise

        self._record_chat_completion(
            model=model_config.model,
            success=True,
            input_text_chars=input_text_chars,
            request_payload_chars=request_payload_chars,
            response_text_chars=response_text_chars,
            usage=usage,
        )
        return decoded

    def _record_chat_completion(
        self,
        *,
        model: str,
        success: bool,
        input_text_chars: int,
        request_payload_chars: int,
        response_text_chars: int = 0,
        usage: dict[str, int] | None = None,
    ) -> None:
        if self._metrics_collector is None:
            return
        usage = usage or {}
        self._metrics_collector.record_openai_call(
            operation="chat.completions",
            model=model,
            success=success,
            input_items=2,
            input_text_chars=input_text_chars,
            request_payload_chars=request_payload_chars,
            response_text_chars=response_text_chars,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    def _decode_chat_completion(self, response: Any) -> dict[str, Any]:
        try:
            message = response.choices[0].message
        except (AttributeError, IndexError) as exc:
            raise OpenAIClientError("OpenAI response did not include a message.") from exc

        refusal = getattr(message, "refusal", None)
        if refusal:
            raise OpenAIClientError(f"OpenAI refused the extraction request: {refusal}")

        content = getattr(message, "content", None)
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise OpenAIClientError("OpenAI response did not include JSON content.")

        try:
            decoded = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError("OpenAI response was not valid JSON.") from exc

        if not isinstance(decoded, dict):
            raise OpenAIClientError("OpenAI response JSON must be an object.")
        return decoded


def _strict_json_schema(schema_model: type[BaseModel]) -> dict[str, Any]:
    """Return a JSON schema adjusted for OpenAI strict structured outputs."""
    schema_factory = getattr(schema_model, "openai_json_schema", None)
    schema = schema_factory() if callable(schema_factory) else schema_model.model_json_schema()
    return _make_strict(schema)


def _make_strict(value: Any) -> Any:
    if isinstance(value, dict):
        strict_value = {
            key: _make_strict(item)
            for key, item in value.items()
            if key != "default"
        }

        properties = strict_value.get("properties")
        if isinstance(properties, dict):
            strict_value["additionalProperties"] = False
            strict_value["required"] = list(properties)

        for key in ("$defs", "items", "anyOf", "oneOf", "allOf"):
            if key in strict_value:
                strict_value[key] = _make_strict(strict_value[key])

        return strict_value

    if isinstance(value, list):
        return [_make_strict(item) for item in value]

    return value


def _json_chars(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=True, default=str))
    except TypeError:
        return 0


def _usage_values(response: Any) -> dict[str, int]:
    usage = _get_value(response, "usage")
    if usage is None:
        return {}
    values: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        raw_value = _get_value(usage, key)
        try:
            values[key] = int(raw_value)
        except (TypeError, ValueError):
            continue
    return values


def _chat_response_text_chars(response: Any) -> int:
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, TypeError):
        return 0
    content = getattr(message, "content", None)
    if isinstance(content, list):
        return sum(
            len(str(item.get("text", "")))
            for item in content
            if isinstance(item, dict)
        )
    if isinstance(content, str):
        return len(content)
    return 0


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
