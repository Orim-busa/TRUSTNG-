from models import Transaction
import transaction_executor
from transaction_executor import execute_transaction, EXECUTED_TRANSACTIONS


def make_transaction(transaction_id):
    return Transaction(
        transaction_id=transaction_id,
        sender="sender_001",
        receiver="receiver_001",
        asset="NGN",
        amount=5000,
        channel="BANK",
        country="NG",
        device_id="device_001",
    )


def test_missing_execution_check_is_blocked(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = execute_transaction(make_transaction("EXEC-TEST-001"), None)

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"


def test_failed_execution_gate_is_blocked(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = execute_transaction(
        make_transaction("EXEC-TEST-002"),
        {"execution_allowed": False, "status": "BLOCKED"},
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"


def test_successful_simulated_execution(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    transaction_id = "EXEC-TEST-003"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is True
    assert result["status"] == "EXECUTED"
    assert result["transaction_id"] == transaction_id


def test_duplicate_transaction_execution_is_blocked(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    transaction_id = "EXEC-TEST-004"
    EXECUTED_TRANSACTIONS.discard(transaction_id)
    transaction = make_transaction(transaction_id)
    approved = {
        "execution_allowed": True,
        "status": "READY_FOR_EXECUTION",
    }

    first_result = execute_transaction(transaction, approved)
    second_result = execute_transaction(transaction, approved)

    assert first_result["executed"] is True
    assert second_result["executed"] is False
    assert second_result["status"] == "DUPLICATE"


def test_persistent_execution_completes_database_record(monkeypatch):
    transaction_id = "EXEC-PERSISTENT-001"
    calls = []

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        transaction_executor.database,
        "claim_transaction_execution",
        lambda value: calls.append(("claim", value)) or True,
    )
    monkeypatch.setattr(
        transaction_executor.database,
        "complete_transaction_execution",
        lambda value: calls.append(("complete", value)) or True,
    )

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is True
    assert result["status"] == "EXECUTED"
    assert calls == [
        ("claim", transaction_id),
        ("complete", transaction_id),
    ]


def test_persistent_execution_is_blocked_if_completion_fails(monkeypatch):
    transaction_id = "EXEC-PERSISTENT-002"

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        transaction_executor.database,
        "claim_transaction_execution",
        lambda value: True,
    )
    monkeypatch.setattr(
        transaction_executor.database,
        "complete_transaction_execution",
        lambda value: False,
    )

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert "could not be confirmed" in result["reason"]


# Direct tests for transaction reservation, replay, and finalization.

def reset_idempotency_state(monkeypatch):
    import idempotency

    monkeypatch.delenv("DATABASE_URL", raising=False)

    with idempotency.TRANSACTION_LOCK:
        idempotency.PROCESSED_TRANSACTIONS.clear()


def test_first_transaction_reservation_succeeds(monkeypatch):
    import idempotency

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-001")

    assert idempotency.reserve_transaction(transaction) is None

    stored = idempotency.check_transaction(transaction.transaction_id)
    assert stored is not None
    assert stored["result"]["status"] == "PROCESSING"


def test_identical_transaction_reservation_is_replay(monkeypatch):
    import idempotency

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-002")

    assert idempotency.reserve_transaction(transaction) is None

    result = idempotency.reserve_transaction(transaction)

    assert result["status"] == "REPLAY"
    assert result["transaction_id"] == transaction.transaction_id


def test_reused_transaction_id_with_changed_amount_is_rejected(monkeypatch):
    import idempotency

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-003")
    changed_transaction = transaction.model_copy(
        update={"amount": transaction.amount + 1}
    )

    assert idempotency.reserve_transaction(transaction) is None

    result = idempotency.reserve_transaction(changed_transaction)

    assert result["status"] == "ID_REUSE"
    assert result["transaction_id"] == transaction.transaction_id


def test_missing_transaction_id_is_rejected(monkeypatch):
    import idempotency

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-004").model_copy(
        update={"transaction_id": ""}
    )

    result = idempotency.reserve_transaction(transaction)

    assert result["status"] == "INVALID"


def test_reserved_transaction_can_be_finalized(monkeypatch):
    import idempotency

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-005")
    final_result = {
        "status": "BLOCKED",
        "reason": "Test risk decision",
    }

    assert idempotency.reserve_transaction(transaction) is None
    idempotency.store_transaction(transaction, final_result)

    stored = idempotency.check_transaction(transaction.transaction_id)
    assert stored["result"] == final_result


def test_final_transaction_result_cannot_be_overwritten(monkeypatch):
    import idempotency
    import pytest

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-006")

    assert idempotency.reserve_transaction(transaction) is None
    idempotency.store_transaction(
        transaction,
        {"status": "BLOCKED"},
    )

    with pytest.raises(RuntimeError, match="final result"):
        idempotency.store_transaction(
            transaction,
            {"status": "ALLOWED"},
        )

    stored = idempotency.check_transaction(transaction.transaction_id)
    assert stored["result"]["status"] == "BLOCKED"


def test_database_reservation_error_is_not_treated_as_success(
    monkeypatch,
):
    import idempotency
    import pytest

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")

    def fail_reservation(*args, **kwargs):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(
        idempotency.database,
        "save_processed_transaction",
        fail_reservation,
    )

    with pytest.raises(RuntimeError, match="simulated database failure"):
        idempotency.reserve_transaction(
            make_transaction("RESERVE-TEST-007")
        )


def test_concurrent_reservations_allow_only_one_first_reservation(
    monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor
    import idempotency

    reset_idempotency_state(monkeypatch)
    transaction = make_transaction("RESERVE-TEST-008")

    def reserve_once(_):
        return idempotency.reserve_transaction(transaction)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(reserve_once, range(24)))

    first_reservations = [result for result in results if result is None]
    replays = [
        result for result in results
        if isinstance(result, dict) and result.get("status") == "REPLAY"
    ]

    assert len(first_reservations) == 1
    assert len(replays) == 23
    assert len(idempotency.PROCESSED_TRANSACTIONS) == 1


def test_database_duplicate_reservation_is_identified_as_replay(monkeypatch):
    import idempotency

    transaction = make_transaction("DB-RESERVE-TEST-001")
    fingerprint = idempotency.create_transaction_fingerprint(transaction)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        idempotency.database, "save_processed_transaction",
        lambda *args: False,
    )
    monkeypatch.setattr(
        idempotency.database, "get_processed_transaction",
        lambda transaction_id: {
            "transaction_id": transaction_id,
            "fingerprint": fingerprint,
            "result": {"status": "PROCESSING"},
        },
    )

    result = idempotency.reserve_transaction(transaction)
    assert result["status"] == "REPLAY"
    assert result["transaction_id"] == transaction.transaction_id


def test_database_duplicate_reservation_detects_changed_fingerprint(monkeypatch):
    import idempotency

    transaction = make_transaction("DB-RESERVE-TEST-002")
    different_fingerprint = (
        "DB-RESERVE-TEST-002", "different-sender", "receiver_001",
        "NGN", 5000, "BANK", "NG", "device_001",
    )

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        idempotency.database, "save_processed_transaction",
        lambda *args: False,
    )
    monkeypatch.setattr(
        idempotency.database, "get_processed_transaction",
        lambda transaction_id: {
            "transaction_id": transaction_id,
            "fingerprint": different_fingerprint,
            "result": {"status": "PROCESSING"},
        },
    )

    result = idempotency.reserve_transaction(transaction)
    assert result["status"] == "ID_REUSE"


def test_database_duplicate_lookup_failure_propagates(monkeypatch):
    import idempotency
    import pytest

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        idempotency.database, "save_processed_transaction",
        lambda *args: False,
    )

    def fail_lookup(transaction_id):
        raise RuntimeError("simulated database lookup failure")

    monkeypatch.setattr(
        idempotency.database, "get_processed_transaction", fail_lookup,
    )

    with pytest.raises(RuntimeError, match="simulated database lookup failure"):
        idempotency.reserve_transaction(
            make_transaction("DB-RESERVE-TEST-003")
        )


def test_database_finalization_failure_is_not_reported_as_success(monkeypatch):
    import idempotency
    import pytest

    transaction = make_transaction("DB-RESERVE-TEST-004")
    fingerprint = idempotency.create_transaction_fingerprint(transaction)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        idempotency.database, "get_processed_transaction",
        lambda transaction_id: {
            "transaction_id": transaction_id,
            "fingerprint": fingerprint,
            "result": {"status": "PROCESSING"},
        },
    )
    monkeypatch.setattr(
        idempotency.database, "update_processed_transaction_result",
        lambda transaction_id, result: False,
    )

    with pytest.raises(
        RuntimeError, match="Could not update the reserved transaction result",
    ):
        idempotency.store_transaction(transaction, {"status": "BLOCKED"})


def test_database_final_result_cannot_be_overwritten(monkeypatch):
    import idempotency
    import pytest

    transaction = make_transaction("DB-RESERVE-TEST-005")
    fingerprint = idempotency.create_transaction_fingerprint(transaction)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        idempotency.database, "get_processed_transaction",
        lambda transaction_id: {
            "transaction_id": transaction_id,
            "fingerprint": fingerprint,
            "result": {"status": "BLOCKED"},
        },
    )

    def unexpected_update(*args, **kwargs):
        pytest.fail("Finalized transaction must not be updated")

    monkeypatch.setattr(
        idempotency.database, "update_processed_transaction_result",
        unexpected_update,
    )

    with pytest.raises(RuntimeError, match="final result"):
        idempotency.store_transaction(transaction, {"status": "ALLOWED"})
