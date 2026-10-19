from models import Transaction
import sandbox_provider_service as service
from provider_adapter import SandboxPaymentAdapter


def make_transaction(transaction_id="SERVICE-TEST-001", amount=1500):
    return Transaction(
        transaction_id=transaction_id,
        sender="customer-001",
        receiver="merchant-001",
        asset="NGN",
        amount=amount,
        channel="sandbox_test",
        country="NG",
        device_id="device-001",
    )


def test_new_reservation_submits_once_and_persists_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: calls.append(("reserve", args))
        or {"decision": "RESERVED", "operation": None},
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: calls.append(("update", args, kwargs))
        or True,
    )

    adapter = SandboxPaymentAdapter()
    result = service.run_sandbox_provider_operation(
        make_transaction(), adapter=adapter
    )

    assert result["decision"] == "COMPLETED"
    assert result["operation_status"] == "SUCCEEDED"
    assert result["result"]["status"] == "SIMULATED_SUCCESS"
    assert [call[0] for call in calls] == ["reserve", "update"]
    assert calls[-1][1][1] == "SUCCEEDED"
    assert calls[-1][2]["authoritative"] is True


def test_existing_pending_with_recoverable_result_does_not_resubmit(
    monkeypatch,
):
    adapter = SandboxPaymentAdapter()
    transaction = make_transaction()
    original = adapter.submit(transaction)
    calls = []

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "CHECK_PROVIDER_STATUS", "operation": {
            "status": "PENDING"
        }},
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
    )

    assert result["decision"] == "COMPLETED"
    assert result["result"]["status"] == original["status"]
    assert result["result"]["replayed"] is True
    assert len(calls) == 1


def test_existing_pending_without_result_requires_reconciliation(monkeypatch):
    updates = []
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "CHECK_PROVIDER_STATUS", "operation": {
            "status": "PENDING"
        }},
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: updates.append((args, kwargs)) or True,
    )

    result = service.run_sandbox_provider_operation(
        make_transaction(), adapter=SandboxPaymentAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["outcome_uncertain"] is True
    assert len(updates) == 1
    assert updates[0][0][1] == "RECONCILIATION_REQUIRED"


def test_existing_reconciliation_state_never_submits(monkeypatch):
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "RECONCILE", "operation": {
            "status": "RECONCILIATION_REQUIRED"
        }},
    )

    adapter = SandboxPaymentAdapter()
    result = service.run_sandbox_provider_operation(
        make_transaction(), adapter=adapter
    )

    assert result["decision"] == "RECONCILE"
    assert adapter.inspect(make_transaction())["status"] == "NOT_FOUND"


def test_final_result_is_replayed_without_submission(monkeypatch):
    stored_result = {"status": "SIMULATED_SUCCESS", "sandbox": True}
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "REPLAY", "operation": {
            "status": "SUCCEEDED",
            "result": stored_result,
        }},
    )

    result = service.run_sandbox_provider_operation(
        make_transaction(), adapter=SandboxPaymentAdapter()
    )

    assert result["decision"] == "REPLAY"
    assert result["result"] == stored_result
    assert result["status"] == "SUCCEEDED"


def test_reservation_database_error_fails_closed(monkeypatch):
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: (_ for _ in ()).throw(RuntimeError("database down")),
    )

    result = service.run_sandbox_provider_operation(
        make_transaction(), adapter=SandboxPaymentAdapter()
    )

    assert result["decision"] == "DATABASE_UNAVAILABLE"
    assert result["status"] == "BLOCKED"
    assert result["outcome_uncertain"] is True


def test_uncertain_sandbox_outcome_is_persisted_for_reconciliation(
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "RESERVED", "operation": None},
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )

    result = service.run_sandbox_provider_operation(
        make_transaction(),
        adapter=SandboxPaymentAdapter(),
        simulate_uncertain_outcome=True,
    )

    assert result["decision"] == "RECONCILE"
    assert result["outcome_uncertain"] is True
    assert calls[0][0][1] == "RECONCILIATION_REQUIRED"


def test_recovered_result_with_wrong_fingerprint_is_not_accepted(monkeypatch):
    transaction = make_transaction()
    real_adapter = SandboxPaymentAdapter()
    prepared = real_adapter.prepare(transaction)
    updates = []

    class MismatchedAdapter:
        def prepare(self, value):
            return real_adapter.prepare(value)

        def inspect(self, value):
            return {
                "provider": prepared["provider"],
                "sandbox": True,
                "transaction_id": prepared["request"]["transaction_id"],
                "idempotency_key": prepared["idempotency_key"],
                "fingerprint": "wrong-fingerprint",
                "status": "SIMULATED_SUCCESS",
                "outcome_uncertain": False,
            }

        def submit(self, *args, **kwargs):
            raise AssertionError("Recovery must never resubmit")

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {
            "decision": "CHECK_PROVIDER_STATUS",
            "operation": {"status": "PENDING"},
        },
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: updates.append((args, kwargs)) or True,
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=MismatchedAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["outcome_uncertain"] is True
    assert updates
    assert updates[0][0][1] == "RECONCILIATION_REQUIRED"


def test_database_failure_persisting_success_returns_uncertain(monkeypatch):
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "RESERVED", "operation": None},
    )

    def fail_persistence(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        fail_persistence,
    )

    result = service.run_sandbox_provider_operation(
        make_transaction(), adapter=SandboxPaymentAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
