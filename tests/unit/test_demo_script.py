"""Tests for the local contract-risk demo script helpers."""

from pathlib import Path

from app.core.config import Settings
from scripts.demo_contract_risk import (
    DemoCase,
    DemoResult,
    _mailgun_form_data,
    _missing_live_settings,
    _normalize_base_url,
    _payload_error,
    _print_case,
)


def test_demo_script_reports_missing_live_settings(tmp_path: Path) -> None:
    settings = Settings(
        upload_dir=tmp_path / "uploads",
        openai_api_key=None,
        azure_search_endpoint=None,
        azure_search_api_key=None,
        mailgun_webhook_secret="",
    )

    assert _missing_live_settings(settings) == [
        "OPENAI_API_KEY",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_API_KEY",
    ]


def test_demo_script_extracts_payload_errors() -> None:
    payload = {
        "classification_error": "Azure AI Search request failed.",
        "outcome": {"errors": ["fallback error"]},
    }

    assert _payload_error(payload) == "Azure AI Search request failed."


def test_demo_script_prints_expected_result_marker(capsys) -> None:
    demo_case = DemoCase(
        title="Clean SaaS Agreement (Acme Hosting)",
        path=Path("contract.pdf"),
        expected_action="auto_store",
        success_marker="✅",
    )

    _print_case(1, demo_case, DemoResult(action="auto_store"))

    output = capsys.readouterr().out
    assert "[1] Clean SaaS Agreement (Acme Hosting)" in output
    assert "→ Expected: auto_store" in output
    assert "→ Result: auto_store ✅" in output


def test_demo_script_normalizes_live_server_base_url() -> None:
    assert _normalize_base_url("127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert _normalize_base_url("https://example.test/api/") == "https://example.test/api"


def test_demo_script_adds_mailgun_signature_when_secret_is_configured(monkeypatch) -> None:
    monkeypatch.setattr("scripts.demo_contract_risk.time.time", lambda: 1234567890)

    data = _mailgun_form_data("Demo contract", webhook_secret="secret")

    assert data["timestamp"] == "1234567890"
    assert data["token"] == "demo-token"
    assert data["signature"] == (
        "c120186d3c918290cb4b07ad1b15318273070a35951d6ba0e1daf256f858b165"
    )
