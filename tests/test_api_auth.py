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


def test_evaluate_records_pre_execution_failure(monkeypatch):
    import main

    transaction_data = {
        "transaction_id": "failure-isolation-test",
        "sender": "sender-test",
        "receiver": "receiver-test",
        "asset": "NGN",
        "amount": 100,
        "channel": "api_test",
        "country": "NG",
        "device_id": "device-test",
    }
    stored = []

    monkeypatch.setattr(main, "reserve_transaction", lambda value: None)

    def fail_recording(value):
        raise RuntimeError("simulated pre-execution failure")

    monkeypatch.setattr(main, "record_transaction", fail_recording)
    monkeypatch.setattr(
        main,
        "store_transaction",
        lambda transaction, result: stored.append(result),
    )

    result = main.evaluate(main.Transaction(**transaction_data))

    assert result["status"] == "FAILED"
    assert result["transaction_id"] == "failure-isolation-test"
    assert "before execution" in result["message"]
    assert stored == [result]


def test_evaluate_requires_reconciliation_if_execution_throws(monkeypatch):
    import main

    transaction = main.Transaction(
        transaction_id="execution-outcome-uncertain-test",
        sender="sender-test",
        receiver="receiver-test",
        asset="NGN",
        amount=100,
        channel="api_test",
        country="NG",
        device_id="device-test",
    )
    stored = []

    monkeypatch.setattr(main, "reserve_transaction", lambda value: None)
    monkeypatch.setattr(main, "record_transaction", lambda value: {"recorded": True})
    monkeypatch.setattr(main, "analyze_transaction", lambda value: [])
    monkeypatch.setattr(main, "analyze_relationship_risk", lambda value: [])
    history = {
        "window_minutes": 60,
        "transaction_count": 0,
        "unique_senders": 0,
        "unique_receivers": 0,
        "total_amount": 0,
    }
    monkeypatch.setattr(main, "analyze_transaction_history", lambda *a, **k: history)
    monkeypatch.setattr(main, "analyze_transaction_velocity", lambda *a, **k: None)
    monkeypatch.setattr(main, "get_beneficiary_profile", lambda value: {"verification_level": "UNKNOWN"})
    monkeypatch.setattr(main, "analyze_behavioral_anomaly", lambda *a, **k: [])
    monkeypatch.setattr(main, "calculate_trust", lambda *a, **k: {"trust_level": "MEDIUM", "score": 50})
    monkeypatch.setattr(main, "analyze_transaction_with_ai", lambda **k: {"engine": "test", "confidence_status": "NOT_CALIBRATED"})
    monkeypatch.setattr(main, "evaluate_transaction", lambda *a, **k: {
        "decision": "APPROVE", "risk_level": "LOW", "restrictions": [],
        "reasons": [], "policy": "test", "policy_version": "1", "action": "ALLOW",
    })
    monkeypatch.setattr(main, "create_authorization", lambda **k: {"authorization_id": "test"})
    monkeypatch.setattr(main, "validate_execution", lambda **k: {"execution_allowed": True})

    def fail_execution(**kwargs):
        raise RuntimeError("simulated uncertain execution")

    monkeypatch.setattr(main, "execute_transaction", fail_execution)
    monkeypatch.setattr(main, "store_transaction", lambda tx, result: stored.append(result))

    result = main.evaluate(transaction)

    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert "Reconcile" in result["message"]
    assert stored == [result]


def test_evaluate_returns_reconciliation_required_if_recovery_cannot_be_saved(monkeypatch):
    import main

    transaction = main.Transaction(
        transaction_id="recovery-storage-failure-test",
        sender="sender-test",
        receiver="receiver-test",
        asset="NGN",
        amount=100,
        channel="api_test",
        country="NG",
        device_id="device-test",
    )
    monkeypatch.setattr(main, "reserve_transaction", lambda value: None)
    monkeypatch.setattr(
        main,
        "record_transaction",
        lambda value: (_ for _ in ()).throw(RuntimeError("simulated pre-execution failure")),
    )
    monkeypatch.setattr(
        main,
        "store_transaction",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
    )

    result = main.evaluate(transaction)

    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert "Do not retry" in result["message"]
