"""Tests for the local contract-risk demo script helpers."""

from pathlib import Path

from app.core.config import Settings
from scripts.demo_contract_risk import (
    DemoCase,
    DemoResult,
    _missing_live_settings,
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
