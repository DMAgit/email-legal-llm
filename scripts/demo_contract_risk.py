"""Run the bundled three-contract risk analyzer demo."""

from __future__ import annotations

import argparse
import hmac
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import Settings, get_settings  # noqa: E402
from app.main import app  # noqa: E402


@dataclass(frozen=True)
class DemoCase:
    """One sample contract and its expected deterministic routing action."""

    title: str
    path: Path
    expected_action: str
    success_marker: str


@dataclass(frozen=True)
class DemoResult:
    """Observed routing result for one demo case."""

    action: str | None
    error: str | None = None


DEMO_CASES = (
    DemoCase(
        title="Clean SaaS Agreement (Acme Hosting)",
        path=Path("data/test files/saas_master_services_agreement_northstar_acme.pdf"),
        expected_action="auto_store",
        success_marker="✅",
    ),
    DemoCase(
        title="Analytics Vendor Contract (BluePeak)",
        path=Path("data/test files/vendor_services_agreement_brightpath_bluepeak.pdf"),
        expected_action="procurement_review",
        success_marker="⚠️",
    ),
    DemoCase(
        title="AI Vendor Contract (DataForge)",
        path=Path("data/test files/saas_ai_services_agreement_specimen_northstar_dataforge.pdf"),
        expected_action="legal_review",
        success_marker="🚨",
    ),
)


def main() -> int:
    """Run the local demo and return a process exit code."""
    _configure_stdout()
    args = _parse_args()

    missing_files = _missing_files(DEMO_CASES)
    if missing_files:
        print("=== Contract Risk Analyzer Demo ===\n")
        print("Missing demo contract files:")
        for path in missing_files:
            print(f"- {path}")
        return 2

    if args.base_url:
        return _run_live_demo(_normalize_base_url(args.base_url))

    settings = Settings()
    missing_settings = _missing_live_settings(settings)
    if missing_settings:
        print("=== Contract Risk Analyzer Demo ===\n")
        print("Missing required live settings:")
        for name in missing_settings:
            print(f"- {name}")
        print("\nSet these in .env, seed Azure AI Search, then run the demo again.")
        return 2

    if args.keep_artifacts:
        upload_dir = REPO_ROOT / "data" / "demo_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{(REPO_ROOT / 'data' / 'demo.db').as_posix()}"
        return _run_demo(settings, upload_dir=upload_dir, database_url=database_url)

    with tempfile.TemporaryDirectory(prefix="contract-risk-demo-") as temp_dir:
        temp_path = Path(temp_dir)
        upload_dir = temp_path / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{(temp_path / 'demo.db').as_posix()}"
        return _run_demo(settings, upload_dir=upload_dir, database_url=database_url)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        help=(
            "Send demo requests to a running API server, for example "
            "http://127.0.0.1:8000. This updates that server's /metrics counters."
        ),
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Store demo uploads and SQLite records under data/demo_* instead of a temp directory.",
    )
    args = parser.parse_args()
    if args.base_url and args.keep_artifacts:
        parser.error("--keep-artifacts only applies when running the in-process demo.")
    return args


def _run_demo(settings: Settings, *, upload_dir: Path, database_url: str) -> int:
    demo_settings = settings.model_copy(
        update={
            "upload_dir": upload_dir,
            "database_url": database_url,
            "mailgun_webhook_secret": "",
        }
    )
    app.dependency_overrides[get_settings] = lambda: demo_settings

    print("=== Contract Risk Analyzer Demo ===\n")
    try:
        client = TestClient(app)
        return _run_cases(client)
    finally:
        app.dependency_overrides.clear()


def _run_live_demo(base_url: str) -> int:
    try:
        import httpx
    except ModuleNotFoundError:
        print("=== Contract Risk Analyzer Demo ===\n")
        print("The httpx package is required for --base-url mode.")
        return 2

    webhook_secret = Settings().mailgun_webhook_secret
    print("=== Contract Risk Analyzer Demo ===\n")
    try:
        with httpx.Client(base_url=base_url, timeout=300.0) as client:
            return _run_cases(client, webhook_secret=webhook_secret)
    except httpx.RequestError as exc:
        print(f"Could not reach API server at {base_url}: {_truncate(str(exc))}")
        return 2


def _run_cases(client: Any, webhook_secret: str | None = None) -> int:
    exit_code = 0
    for index, demo_case in enumerate(DEMO_CASES, start=1):
        result = _run_case(client, demo_case, webhook_secret=webhook_secret)
        if result.action != demo_case.expected_action:
            exit_code = 1
        _print_case(index, demo_case, result)
    return exit_code


def _run_case(
    client: Any,
    demo_case: DemoCase,
    webhook_secret: str | None = None,
) -> DemoResult:
    path = REPO_ROOT / demo_case.path
    data = _mailgun_form_data(demo_case.title, webhook_secret=webhook_secret)
    with path.open("rb") as file:
        response = client.post(
            "/webhooks/mailgun/inbound?classify=true",
            data=data,
            files={"attachment-1": (path.name, file, "application/pdf")},
        )

    payload = _response_payload(response)
    if response.status_code != 200:
        return DemoResult(action=None, error=_payload_error(payload) or response.text)

    outcome = payload.get("outcome")
    action = outcome.get("final_action") if isinstance(outcome, dict) else None
    return DemoResult(action=action, error=_payload_error(payload))


def _mailgun_form_data(title: str, webhook_secret: str | None = None) -> dict[str, str]:
    data = {
        "sender": "demo@example.com",
        "recipient": "contracts@example.com",
        "subject": title,
        "body-plain": "Please review this demo contract.",
        "attachment-count": "1",
    }
    secret = webhook_secret.strip() if webhook_secret else ""
    if not secret:
        return data

    timestamp = str(int(time.time()))
    token = "demo-token"
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}{token}".encode("utf-8"),
        "sha256",
    ).hexdigest()
    data.update(
        {
            "timestamp": timestamp,
            "token": token,
            "signature": signature,
        }
    )
    return data


def _print_case(index: int, demo_case: DemoCase, result: DemoResult) -> None:
    print(f"[{index}] {demo_case.title}")
    print(f"→ Expected: {demo_case.expected_action}")
    marker = demo_case.success_marker if result.action == demo_case.expected_action else "❌"
    print(f"→ Result: {result.action or 'error'} {marker}")
    if result.error and result.action != demo_case.expected_action:
        print(f"  Error: {_truncate(result.error)}")
    if index < len(DEMO_CASES):
        print()


def _response_payload(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_error(payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("detail"), str):
        return payload["detail"]
    if isinstance(payload.get("classification_error"), str):
        return payload["classification_error"]

    outcome = payload.get("outcome")
    if isinstance(outcome, dict):
        errors = outcome.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(error) for error in errors if error)

    for key in ("extraction_errors", "errors"):
        values = payload.get(key)
        if isinstance(values, list) and values:
            messages = [
                str(item.get("error") if isinstance(item, dict) else item)
                for item in values
            ]
            joined = "; ".join(message for message in messages if message)
            if joined:
                return joined
    return None


def _missing_live_settings(settings: Settings) -> list[str]:
    required = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "AZURE_SEARCH_ENDPOINT": settings.azure_search_endpoint,
        "AZURE_SEARCH_API_KEY": settings.azure_search_api_key,
    }
    return [name for name, value in required.items() if not value or not value.strip()]


def _missing_files(demo_cases: tuple[DemoCase, ...]) -> list[Path]:
    return [
        demo_case.path
        for demo_case in demo_cases
        if not (REPO_ROOT / demo_case.path).exists()
    ]


def _normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        return normalized
    if normalized.startswith(("http://", "https://")):
        return normalized
    return f"http://{normalized}"


def _truncate(value: str, limit: int = 220) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
