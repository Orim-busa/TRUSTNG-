import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
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
    persisted = {}
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: calls.append(("reserve", args))
        or {"decision": "RESERVED", "operation": None},
    )
    def update(*args, **kwargs):
        calls.append(("update", args, kwargs))
        persisted["result"] = args[2]
        return True

    monkeypatch.setattr(
        service.database, "update_provider_operation_status", update
    )

    adapter = SandboxPaymentAdapter()
    transaction = make_transaction()
    prepared = adapter.prepare(transaction)
    monkeypatch.setattr(
        service.database,
        "get_provider_operation",
        lambda key: {
            "idempotency_key": key,
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": prepared["fingerprint"],
            "status": "SUCCEEDED",
            "result": persisted.get("result"),
        },
    )
    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
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
    prepared = adapter.prepare(transaction)
    calls = []
    persisted = {}

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "CHECK_PROVIDER_STATUS", "operation": {
            "idempotency_key": args[0],
            "provider": args[1],
            "transaction_id": args[2],
            "request_fingerprint": args[3],
            "status": "PENDING",
        }},
    )

    def update(*args, **kwargs):
        calls.append((args, kwargs))
        persisted["result"] = args[2]
        return True

    monkeypatch.setattr(
        service.database, "update_provider_operation_status", update
    )
    monkeypatch.setattr(
        service.database,
        "get_provider_operation",
        lambda key: {
            "idempotency_key": key,
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": prepared["fingerprint"],
            "status": "SUCCEEDED",
            "result": persisted.get("result"),
        },
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
    )

    assert result["decision"] == "COMPLETED"
    assert result["result"]["status"] == original["status"]
    assert result["result"]["replayed"] is True
    assert len(calls) == 1




@pytest.mark.parametrize(
    "operation_factory",
    [
        pytest.param(lambda prepared: None, id="missing-operation"),
        pytest.param(lambda prepared: [], id="wrong-operation-type"),
        pytest.param(
            lambda prepared: {
                "status": "PENDING",
                "idempotency_key": "different-key",
                "provider": prepared["provider"],
                "transaction_id": prepared["request"]["transaction_id"],
                "request_fingerprint": prepared["fingerprint"],
            },
            id="wrong-idempotency-key",
        ),
        pytest.param(
            lambda prepared: {
                "status": "PENDING",
                "idempotency_key": prepared["idempotency_key"],
                "provider": prepared["provider"],
                "transaction_id": "different-transaction",
                "request_fingerprint": prepared["fingerprint"],
            },
            id="wrong-transaction",
        ),
        pytest.param(
            lambda prepared: {
                "status": "SUCCEEDED",
                "idempotency_key": prepared["idempotency_key"],
                "provider": prepared["provider"],
                "transaction_id": prepared["request"]["transaction_id"],
                "request_fingerprint": prepared["fingerprint"],
            },
            id="not-pending",
        ),
    ],
)
def test_invalid_pending_reservation_fails_closed_without_inspection(
    monkeypatch, operation_factory
):
    transaction = make_transaction()
    prepared = SandboxPaymentAdapter().prepare(transaction)
    updates = []

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {
            "decision": "CHECK_PROVIDER_STATUS",
            "operation": operation_factory(prepared),
        },
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: updates.append((args, kwargs)) or True,
    )

    class NeverInspectAdapter(SandboxPaymentAdapter):
        def inspect(self, *args, **kwargs):
            raise AssertionError(
                "Invalid reservation must be rejected before inspection"
            )

        def submit(self, *args, **kwargs):
            raise AssertionError(
                "Invalid reservation must never trigger submission"
            )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=NeverInspectAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
    assert updates == []


def test_existing_pending_without_result_requires_reconciliation(monkeypatch):
    updates = []
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "CHECK_PROVIDER_STATUS", "operation": {
            "idempotency_key": args[0],
            "provider": args[1],
            "transaction_id": args[2],
            "request_fingerprint": args[3],
            "status": "PENDING",
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
    transaction = make_transaction()
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)
    stored_result = {
        "provider": prepared["provider"],
        "sandbox": True,
        "transaction_id": prepared["request"]["transaction_id"],
        "idempotency_key": prepared["idempotency_key"],
        "fingerprint": prepared["fingerprint"],
        "status": "SIMULATED_SUCCESS",
        "outcome_uncertain": False,
    }
    operation = {
        "idempotency_key": prepared["idempotency_key"],
        "provider": prepared["provider"],
        "transaction_id": prepared["request"]["transaction_id"],
        "request_fingerprint": prepared["fingerprint"],
        "status": "SUCCEEDED",
        "result": stored_result,
    }
    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "REPLAY", "operation": operation},
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
    )

    assert result["decision"] == "REPLAY"
    assert result["result"] == stored_result
    assert result["status"] == "SUCCEEDED"
    assert result["outcome_uncertain"] is False



@pytest.mark.parametrize(
    ("target", "field", "bad_value"),
    [
        ("result", "status", "RECONCILIATION_REQUIRED"),
        ("result", "transaction_id", "DIFFERENT-TRANSACTION"),
        ("result", "fingerprint", "wrong-fingerprint"),
        ("result", "sandbox", False),
        ("operation", "idempotency_key", "wrong-idempotency-key"),
        ("operation", "provider", "wrong-provider"),
        ("operation", "transaction_id", "DIFFERENT-TRANSACTION"),
        ("operation", "request_fingerprint", "wrong-fingerprint"),
    ],
)
def test_final_replay_rejects_inconsistent_stored_result(
    monkeypatch, target, field, bad_value
):
    transaction = make_transaction()
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)

    stored_result = {
        "provider": prepared["provider"],
        "sandbox": True,
        "transaction_id": prepared["request"]["transaction_id"],
        "idempotency_key": prepared["idempotency_key"],
        "fingerprint": prepared["fingerprint"],
        "status": "SIMULATED_SUCCESS",
        "outcome_uncertain": False,
    }
    operation = {
        "idempotency_key": prepared["idempotency_key"],
        "provider": prepared["provider"],
        "transaction_id": prepared["request"]["transaction_id"],
        "request_fingerprint": prepared["fingerprint"],
        "status": "SUCCEEDED",
        "result": stored_result,
    }

    if target == "result":
        stored_result[field] = bad_value
    else:
        operation[field] = bad_value

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {
            "decision": "REPLAY",
            "operation": operation,
        },
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True

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
            "operation": {
                "idempotency_key": args[0],
                "provider": args[1],
                "transaction_id": args[2],
                "request_fingerprint": args[3],
                "status": "PENDING",
            },
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


def test_restart_after_persistence_failure_never_resubmits(monkeypatch):
    """A fresh adapter must not resubmit an uncertain pending operation."""
    transaction = make_transaction()
    reservation_calls = []

    def reserve_or_inspect(*args):
        reservation_calls.append(args)
        if len(reservation_calls) == 1:
            return {"decision": "RESERVED", "operation": None}
        return {
            "decision": "CHECK_PROVIDER_STATUS",
            "operation": {
                "idempotency_key": args[0],
                "provider": args[1],
                "transaction_id": args[2],
                "request_fingerprint": args[3],
                "status": "PENDING",
            },
        }

    def fail_persistence(*args, **kwargs):
        raise RuntimeError("simulated database persistence failure")

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        reserve_or_inspect,
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        fail_persistence,
    )

    class CountingSandboxAdapter(SandboxPaymentAdapter):
        def __init__(self):
            super().__init__()
            self.submit_count = 0

        def submit(self, transaction, **kwargs):
            self.submit_count += 1
            return super().submit(transaction, **kwargs)

    # First process: reservation succeeds and simulation runs, but the
    # database cannot confirm that the result was persisted.
    first_adapter = CountingSandboxAdapter()
    first_result = service.run_sandbox_provider_operation(
        transaction, adapter=first_adapter
    )

    assert first_result["decision"] == "RECONCILE"
    assert first_result["outcome_uncertain"] is True
    assert first_adapter.submit_count == 1

    # Simulated restart: a fresh adapter has no in-memory provider record.
    second_adapter = CountingSandboxAdapter()
    recovery_result = service.run_sandbox_provider_operation(
        transaction, adapter=second_adapter
    )

    assert recovery_result["decision"] == "RECONCILE"
    assert recovery_result["status"] == "RECONCILIATION_REQUIRED"
    assert recovery_result["outcome_uncertain"] is True
    assert second_adapter.submit_count == 0
    assert len(reservation_calls) == 2


def test_recovery_persists_reconciliation_when_database_returns(monkeypatch):
    """Recovery records uncertainty durably without resubmitting."""
    transaction = make_transaction()
    reservation_calls = []
    update_calls = []
    durable_state = {"status": "PENDING", "result": None}

    def reserve_or_inspect(*args):
        reservation_calls.append(args)

        if len(reservation_calls) == 1:
            return {"decision": "RESERVED", "operation": None}

        if durable_state["status"] == "RECONCILIATION_REQUIRED":
            return {
                "decision": "RECONCILE",
                "operation": {
                    "status": durable_state["status"],
                    "result": durable_state["result"],
                },
            }

        return {
            "decision": "CHECK_PROVIDER_STATUS",
            "operation": {
                "idempotency_key": args[0],
                "provider": args[1],
                "transaction_id": args[2],
                "request_fingerprint": args[3],
                "status": "PENDING",
            },
        }

    def update_status(*args, **kwargs):
        update_calls.append((args, kwargs))

        # The first write fails after the simulated operation has run.
        if len(update_calls) == 1:
            raise RuntimeError("database temporarily unavailable")

        # The recovery attempt must only record uncertainty, never success.
        assert args[1] == "RECONCILIATION_REQUIRED"
        durable_state["status"] = args[1]
        durable_state["result"] = args[2]
        return True

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        reserve_or_inspect,
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        update_status,
    )

    class CountingSandboxAdapter(SandboxPaymentAdapter):
        def __init__(self):
            super().__init__()
            self.submit_count = 0

        def submit(self, transaction, **kwargs):
            self.submit_count += 1
            return super().submit(transaction, **kwargs)

    # First attempt: sandbox submission runs, but persistence fails.
    first_adapter = CountingSandboxAdapter()
    first_result = service.run_sandbox_provider_operation(
        transaction, adapter=first_adapter
    )

    assert first_result["decision"] == "RECONCILE"
    assert first_result["outcome_uncertain"] is True
    assert first_adapter.submit_count == 1
    assert durable_state["status"] == "PENDING"

    # Recovery: fresh adapter cannot inspect the old in-memory result.
    second_adapter = CountingSandboxAdapter()
    second_result = service.run_sandbox_provider_operation(
        transaction, adapter=second_adapter
    )

    assert second_result["decision"] == "RECONCILE"
    assert second_result["status"] == "RECONCILIATION_REQUIRED"
    assert second_result["outcome_uncertain"] is True
    assert second_adapter.submit_count == 0
    assert durable_state["status"] == "RECONCILIATION_REQUIRED"
    assert len(update_calls) == 2

    # Later request reads the durable reconciliation state.
    third_adapter = CountingSandboxAdapter()
    third_result = service.run_sandbox_provider_operation(
        transaction, adapter=third_adapter
    )

    assert third_result["decision"] == "RECONCILE"
    assert third_result["status"] == "RECONCILIATION_REQUIRED"
    assert third_adapter.submit_count == 0
    assert len(reservation_calls) == 3
    assert len(update_calls) == 2


def test_mismatched_database_readback_never_reports_success(monkeypatch):
    transaction = make_transaction()
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "RESERVED", "operation": None},
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        service.database,
        "get_provider_operation",
        lambda key: {
            "idempotency_key": key,
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": "deliberately-wrong-fingerprint",
            "status": "SUCCEEDED",
            "result": {"status": "SIMULATED_SUCCESS"},
        },
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
    assert result["decision"] != "COMPLETED"


@pytest.mark.parametrize("invalid_result", [None, "invalid-result"])
def test_invalid_adapter_result_requires_reconciliation(
    monkeypatch, invalid_result
):
    transaction = make_transaction()
    update_calls = []

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "RESERVED", "operation": None},
    )

    def update_status(*args, **kwargs):
        update_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        update_status,
    )

    class InvalidResultAdapter(SandboxPaymentAdapter):
        def submit(self, transaction, **kwargs):
            return invalid_result

    result = service.run_sandbox_provider_operation(
        transaction, adapter=InvalidResultAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True

    assert len(update_calls) == 1
    args, _kwargs = update_calls[0]
    assert args[1] == "RECONCILIATION_REQUIRED"
    assert "invalid result type" in args[2]["reason"].lower()



def test_concurrent_requests_submit_only_once(monkeypatch):
    """Only the caller winning the reservation may submit."""
    transaction = make_transaction("CONCURRENT-SERVICE-TEST-001")
    reservation_lock = threading.Lock()
    submit_lock = threading.Lock()
    reservation_count = 0
    submit_count = 0
    start_barrier = threading.Barrier(2)

    def reserve(*args):
        nonlocal reservation_count

        with reservation_lock:
            reservation_count += 1
            if reservation_count == 1:
                return {"decision": "RESERVED", "operation": None}

            return {
                "decision": "CHECK_PROVIDER_STATUS",
                "operation": {
                    "idempotency_key": args[0],
                    "provider": args[1],
                    "transaction_id": args[2],
                    "request_fingerprint": args[3],
                    "status": "PENDING",
                },
            }

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        reserve,
    )
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        service,
        "_persist_sandbox_result",
        lambda prepared, result: {
            "decision": "COMPLETED",
            "status": "SIMULATED_SUCCESS",
            "sandbox": True,
            "outcome_uncertain": False,
            "result": result,
        },
    )

    class CountingAdapter(SandboxPaymentAdapter):
        def submit(self, transaction, **kwargs):
            nonlocal submit_count
            with submit_lock:
                submit_count += 1
            return super().submit(transaction, **kwargs)

    adapter = CountingAdapter()

    def run_concurrent_request():
        start_barrier.wait(timeout=5)
        return service.run_sandbox_provider_operation(
            transaction,
            adapter=adapter,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_concurrent_request)
            for _ in range(2)
        ]
        results = [future.result(timeout=10) for future in futures]

    assert reservation_count == 2
    assert submit_count == 1
    assert all(isinstance(result, dict) for result in results)
    assert any(
        result.get("decision") == "COMPLETED"
        for result in results
    )


def test_uncertain_simulated_success_must_not_be_persisted_as_succeeded(
    monkeypatch,
):
    """A contradictory success result must fail closed."""
    transaction = make_transaction()
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)
    update_calls = []
    persisted = {}

    class ContradictoryAdapter(SandboxPaymentAdapter):
        def submit(self, transaction, **kwargs):
            details = self.prepare(transaction)
            return {
                "provider": details["provider"],
                "sandbox": True,
                "transaction_id": details["request"]["transaction_id"],
                "idempotency_key": details["idempotency_key"],
                "fingerprint": details["fingerprint"],
                "status": "SIMULATED_SUCCESS",
                "outcome_uncertain": True,
            }

    def update_status(*args, **kwargs):
        update_calls.append((args, kwargs))
        persisted["status"] = args[1]
        persisted["result"] = args[2]
        return True

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "RESERVED", "operation": None},
    )
    monkeypatch.setattr(
        service.database, "update_provider_operation_status", update_status
    )
    monkeypatch.setattr(
        service.database,
        "get_provider_operation",
        lambda key: {
            "idempotency_key": key,
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": prepared["fingerprint"],
            "status": persisted.get("status", "PENDING"),
            "result": persisted.get("result"),
        },
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=ContradictoryAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
    assert persisted.get("status") != "SUCCEEDED"
    assert update_calls
    assert update_calls[0][0][1] == "RECONCILIATION_REQUIRED"


def test_recovered_uncertain_success_requires_reconciliation(monkeypatch):
    """Recovery must not persist uncertain success as a final success."""
    transaction = make_transaction()
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)
    update_calls = []

    class UncertainRecoveryAdapter(SandboxPaymentAdapter):
        def inspect(self, transaction):
            details = self.prepare(transaction)
            return {
                "provider": details["provider"],
                "sandbox": True,
                "transaction_id": details["request"]["transaction_id"],
                "idempotency_key": details["idempotency_key"],
                "fingerprint": details["fingerprint"],
                "status": "SIMULATED_SUCCESS",
                "outcome_uncertain": True,
            }

        def submit(self, transaction, **kwargs):
            raise AssertionError("Recovery must never resubmit")

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {
            "decision": "CHECK_PROVIDER_STATUS",
            "operation": {
                "idempotency_key": args[0],
                "provider": args[1],
                "transaction_id": args[2],
                "request_fingerprint": args[3],
                "status": "PENDING",
            },
        },
    )

    def update_status(*args, **kwargs):
        update_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(
        service.database, "update_provider_operation_status", update_status
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=UncertainRecoveryAdapter()
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
    assert update_calls
    assert update_calls[0][0][1] == "RECONCILIATION_REQUIRED"
    assert all(
        call[0][1] != "SUCCEEDED"
        for call in update_calls
    )


def test_final_replay_rejects_uncertain_simulated_success(monkeypatch):
    """A stored success with an uncertain outcome must not be replayed."""
    transaction = make_transaction()
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)

    stored_result = {
        "provider": prepared["provider"],
        "sandbox": True,
        "transaction_id": prepared["request"]["transaction_id"],
        "idempotency_key": prepared["idempotency_key"],
        "fingerprint": prepared["fingerprint"],
        "status": "SIMULATED_SUCCESS",
        "outcome_uncertain": True,
    }
    operation = {
        "idempotency_key": prepared["idempotency_key"],
        "provider": prepared["provider"],
        "transaction_id": prepared["request"]["transaction_id"],
        "request_fingerprint": prepared["fingerprint"],
        "status": "SUCCEEDED",
        "result": stored_result,
    }

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {"decision": "REPLAY", "operation": operation},
    )

    result = service.run_sandbox_provider_operation(
        transaction, adapter=adapter
    )

    assert result["decision"] == "RECONCILE"
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True


def test_persistence_race_rejects_mismatched_final_record(monkeypatch):
    """A competing final record must pass identity checks before replay."""
    transaction = make_transaction("RECOVERY-RACE-IDENTITY-001")
    adapter = SandboxPaymentAdapter()
    prepared = adapter.prepare(transaction)
    result = adapter.submit(transaction)

    # Simulate another worker winning the status transition, but the
    # record returned afterward belongs to a different transaction.
    monkeypatch.setattr(
        service.database,
        "update_provider_operation_status",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        service.database,
        "get_provider_operation",
        lambda key: {
            "idempotency_key": key,
            "provider": prepared["provider"],
            "transaction_id": "DIFFERENT-TRANSACTION",
            "request_fingerprint": prepared["fingerprint"],
            "status": "SUCCEEDED",
            "result": result,
        },
    )

    recovered = service._persist_sandbox_result(prepared, result)

    assert recovered["decision"] == "RECONCILE"
    assert recovered["status"] == "RECONCILIATION_REQUIRED"
    assert recovered["outcome_uncertain"] is True



def test_malformed_inspect_results_require_reconciliation(monkeypatch):
    """Malformed recovery data must never trigger another submission."""
    transaction = make_transaction()
    real_adapter = SandboxPaymentAdapter()
    updates = []

    class MalformedInspectAdapter:
        def __init__(self, response):
            self.response = response

        def prepare(self, value):
            return real_adapter.prepare(value)

        def inspect(self, value):
            return self.response

        def submit(self, *args, **kwargs):
            raise AssertionError("Recovery must never resubmit")

    monkeypatch.setattr(
        service.database,
        "reserve_or_inspect_provider_operation",
        lambda *args: {
            "decision": "CHECK_PROVIDER_STATUS",
            "operation": {
                "idempotency_key": args[0],
                "provider": args[1],
                "transaction_id": args[2],
                "request_fingerprint": args[3],
                "status": "PENDING",
            },
        },
    )

    def record_update(*args, **kwargs):
        updates.append((args, kwargs))
        return True

    monkeypatch.setattr(
        service.database, "update_provider_operation_status", record_update
    )

    for malformed_response in (None, [], "unexpected response"):
        result = service.run_sandbox_provider_operation(
            transaction,
            adapter=MalformedInspectAdapter(malformed_response),
        )

        assert result["decision"] == "RECONCILE"
        assert result["status"] == "RECONCILIATION_REQUIRED"
        assert result["outcome_uncertain"] is True

    assert len(updates) == 3
    assert all(
        call[0][1] == "RECONCILIATION_REQUIRED"
        for call in updates
    )
