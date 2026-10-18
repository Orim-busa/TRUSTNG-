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
