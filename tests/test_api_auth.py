import os

from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


def test_health_endpoint_is_public():
    response = client.get("/v1/health")

    assert response.status_code == 200


def test_protected_route_rejects_missing_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    response = client.get("/fraud-cases")

    assert response.status_code == 401


def test_protected_route_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    response = client.get(
        "/fraud-cases",
        headers={"X-API-Key": "wrong-secret-key"},
    )

    assert response.status_code == 401


def test_protected_route_accepts_correct_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    response = client.get(
        "/fraud-cases",
        headers={"X-API-Key": "test-secret-key"},
    )

    assert response.status_code == 200


def test_protected_route_returns_503_without_configured_key(monkeypatch):
    monkeypatch.delenv("TRUSTNG_API_KEY", raising=False)

    response = client.get("/fraud-cases")

    assert response.status_code == 503
