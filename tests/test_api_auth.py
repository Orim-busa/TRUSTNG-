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


def test_replay_response_returns_original_summary_fields(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    previous_result = {
        "transaction_id": "replay-regression-test",
        "decision": {
            "decision": "REVIEW",
            "risk_level": "MEDIUM",
            "action": "HOLD_FOR_REVIEW",
            "reasons": ["Beneficiary trust level is LOW"],
        },
        "trust": {"score": 30, "level": "LOW"},
    }

    replay_result = {
        "transaction_id": "replay-regression-test",
        "status": "REPLAY",
        "message": "Transaction has already been processed",
        "previous_result": previous_result,
    }

    monkeypatch.setattr(
        main,
        "evaluate",
        lambda transaction: replay_result,
    )

    response = client.post(
        "/v1/transactions/check",
        headers={"X-API-Key": "test-secret-key"},
        json={
            "transaction_id": "replay-regression-test",
            "sender": "test-sender",
            "receiver": "test-receiver",
            "asset": "NGN",
            "amount": 1500,
            "channel": "api_test",
            "country": "NG",
            "device_id": "test-device",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "REVIEW"
    assert body["risk_level"] == "MEDIUM"
    assert body["action"] == "HOLD_FOR_REVIEW"
    assert body["reasons"] == ["Beneficiary trust level is LOW"]
    assert body["trust"] == {"score": 30, "level": "LOW"}
    assert body["analysis"]["status"] == "REPLAY"


def test_evaluate_propagates_pre_execution_failure(monkeypatch):
    import pytest
    import main

    transaction = {
        "transaction_id": "failure-isolation-test",
        "sender": "sender-test",
        "receiver": "receiver-test",
        "asset": "NGN",
        "amount": 100,
        "channel": "api_test",
        "country": "NG",
        "device_id": "device-test",
    }

    monkeypatch.setattr(
        main,
        "reserve_transaction",
        lambda value: None,
    )

    def fail_recording(value):
        raise RuntimeError("simulated pre-execution failure")

    monkeypatch.setattr(main, "record_transaction", fail_recording)

    with pytest.raises(RuntimeError, match="simulated pre-execution failure"):
        main.evaluate(main.Transaction(**transaction))
