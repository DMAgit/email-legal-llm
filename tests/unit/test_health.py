"""Tests for foundation FastAPI endpoints."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_loaded_model_configs() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "contract-risk-analyzer",
        "environment": "development",
        "model_configs": ["classification", "extraction"],
    }


def test_model_configs_endpoint_exposes_yaml_configs() -> None:
    client = TestClient(app)

    response = client.get("/model-configs")

    assert response.status_code == 200
    configs = response.json()["configs"]
    assert configs["classification"]["response_schema"] == "ClassificationResult"
    assert configs["extraction"]["temperature"] == 0.0

