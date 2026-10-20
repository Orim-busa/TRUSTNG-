import os
import pytest

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


def test_evaluate_returns_reconciliation_required_on_reservation_error(
    monkeypatch,
):
    import main

    transaction = main.Transaction(
        transaction_id="reservation-error-boundary-test",
        sender="sender-test",
        receiver="receiver-test",
        asset="NGN",
        amount=100,
        channel="api_test",
        country="NG",
        device_id="device-test",
    )

    def fail_reservation(value):
        raise RuntimeError("simulated uncertain reservation")

    monkeypatch.setattr(main, "reserve_transaction", fail_reservation)

    def unexpected_evaluation(*args, **kwargs):
        raise AssertionError(
            "Evaluation must stop when reservation cannot be confirmed."
        )

    monkeypatch.setattr(main, "record_transaction", unexpected_evaluation)

    result = main.evaluate(transaction)

    assert result["transaction_id"] == "reservation-error-boundary-test"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert "No payment execution was attempted" in result["message"]
    assert "before retrying" in result["message"]


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


def test_evaluate_does_not_attempt_execution_or_require_reconciliation(monkeypatch):
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
    def unexpected_execution_path(**kwargs):
        raise AssertionError(
            "Risk evaluation must not invoke payment authorization or execution."
        )

    monkeypatch.setattr(
        main, "create_authorization", unexpected_execution_path, raising=False
    )
    monkeypatch.setattr(
        main, "validate_execution", unexpected_execution_path, raising=False
    )
    monkeypatch.setattr(
        main, "execute_transaction", unexpected_execution_path, raising=False
    )
    monkeypatch.setattr(main, "store_transaction", lambda tx, result: stored.append(result))

    result = main.evaluate(transaction)

    assert result["execution"]["status"] == "NOT_ATTEMPTED"
    assert result["execution"]["funds_moved"] is False
    assert result["execution_check"]["execution_allowed"] is False
    assert result.get("status") != "RECONCILIATION_REQUIRED"
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


def test_pending_reconciliation_route_requires_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    response = client.get("/v1/reconciliation/pending")

    assert response.status_code == 401


def test_pending_reconciliation_route_returns_candidates(monkeypatch):
    import main

    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")
    monkeypatch.setattr(
        main.database,
        "list_pending_transaction_executions",
        lambda older_than_minutes, limit: [{
            "transaction_id": "TX-UNCERTAIN-001",
            "execution_status": "PENDING",
            "claimed_at": "2026-01-01T00:00:00+00:00",
            "executed_at": None,
            "transaction_status": "RECONCILIATION_REQUIRED",
            "transaction_message": "Check provider status",
            "resolution": "REQUIRES_PROVIDER_STATUS_CHECK",
        }],
    )

    response = client.get(
        "/v1/reconciliation/pending?older_than_minutes=5&limit=20",
        headers={"X-API-Key": "test-secret-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["transaction_id"] == "TX-UNCERTAIN-001"
    assert body["items"][0]["resolution"] == (
        "REQUIRES_PROVIDER_STATUS_CHECK"
    )


def test_pending_reconciliation_route_rejects_invalid_limit(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    response = client.get(
        "/v1/reconciliation/pending?limit=201",
        headers={"X-API-Key": "test-secret-key"},
    )

    assert response.status_code == 400


def test_openapi_documents_api_key_for_protected_routes():
    schema = app.openapi()

    scheme = schema["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "Required for protected endpoints. "
            "Use the API key supplied by the TrustNG operator."
        ),
    }

    protected_operations = [
        ("/fraud-cases", "get"),
        ("/fraud-cases/{case_id}/resolve", "post"),
        ("/v1/reconciliation/pending", "get"),
        ("/v1/research/candidates/{candidate_id}/review", "post"),
        ("/v1/research/candidates/{candidate_id}/promote", "post"),
        ("/v1/transactions/check", "post"),
    ]

    for route, method in protected_operations:
        operation = schema["paths"][route][method]
        assert operation["security"] == [{"APIKeyHeader": []}]


def test_openapi_keeps_public_routes_unauthenticated():
    schema = app.openapi()

    public_operations = [
        ("/", "get"),
        ("/v1/health", "get"),
        ("/dashboard", "get"),
    ]

    for route, method in public_operations:
        operation = schema["paths"][route][method]
        assert operation["security"] == []


@pytest.mark.parametrize(
    ("method", "route"),
    [
        ("GET", "/v1/dashboard/summary"),
        ("GET", "/v1/dashboard/research"),
        ("POST", "/v1/research/candidates/test-candidate/review"),
        ("POST", "/v1/research/candidates/test-candidate/promote"),
        ("GET", "/v1/dashboard/proposals"),
        ("GET", "/v1/dashboard/benchmarks"),
        ("POST", "/evaluate"),
        ("GET", "/v1/reconciliation/pending"),
        ("GET", "/fraud-cases"),
        ("GET", "/fraud-cases/statistics"),
        ("GET", "/fraud-cases/test-case"),
        ("GET", "/transactions/test-transaction/fraud-cases"),
        ("POST", "/fraud-cases/test-case/notes"),
        ("POST", "/fraud-cases/test-case/actions"),
        ("POST", "/fraud-cases/test-case/resolve"),
        ("POST", "/fraud-cases/test-case/dismiss"),
        ("GET", "/fraud-cases/test-case/audit"),
        ("GET", "/audit/integrity"),
        ("POST", "/v1/transactions/check"),
    ],
)
def test_all_sensitive_routes_reject_missing_api_key(
    monkeypatch, method, route
):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-secret-key")

    response = client.request(method, route)

    assert response.status_code == 401, (
        f"{method} {route} should reject a missing API key; "
        f"got HTTP {response.status_code}"
    )
