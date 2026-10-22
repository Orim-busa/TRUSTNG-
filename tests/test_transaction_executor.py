from models import Transaction
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
    monkeypatch.delenv('DATABASE_URL', raising=False)
    result = execute_transaction(make_transaction("EXEC-TEST-001"), None)

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"


def test_failed_execution_gate_is_blocked(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    result = execute_transaction(
        make_transaction("EXEC-TEST-002"),
        {"execution_allowed": False, "status": "BLOCKED"},
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"


def test_successful_simulated_execution(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    transaction_id = "EXEC-TEST-003"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "SIMULATED_EXECUTION"
    assert result["simulation"] is True
    assert result["funds_moved"] is False
    assert result["transaction_id"] == transaction_id


def test_duplicate_transaction_execution_is_blocked(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    transaction_id = "EXEC-TEST-004"
    EXECUTED_TRANSACTIONS.discard(transaction_id)
    transaction = make_transaction(transaction_id)
    approved = {"execution_allowed": True, "status": "READY_FOR_EXECUTION"}

    first_result = execute_transaction(transaction, approved)
    second_result = execute_transaction(transaction, approved)

    assert first_result["executed"] is False
    assert second_result["executed"] is False
    assert second_result["status"] == "DUPLICATE"

def test_persistent_simulation_records_database_status(monkeypatch):
    import transaction_executor

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
        "mark_transaction_execution_simulated",
        lambda value: calls.append(("mark_simulated", value)) or True,
    )

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "SIMULATED_EXECUTION"
    assert result["simulation"] is True
    assert result["funds_moved"] is False
    assert calls == [
        ("claim", transaction_id),
        ("mark_simulated", transaction_id),
    ]


def test_persistent_simulation_is_blocked_if_status_recording_fails(monkeypatch):
    import transaction_executor

    transaction_id = "EXEC-PERSISTENT-002"

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")
    monkeypatch.setattr(
        transaction_executor.database,
        "claim_transaction_execution",
        lambda value: True,
    )
    monkeypatch.setattr(
        transaction_executor.database,
        "mark_transaction_execution_simulated",
        lambda value: False,
    )

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
    assert result["simulation"] is True
    assert result["funds_moved"] is False
    assert "do not retry automatically" in result["reason"]


def test_database_claim_exception_fails_closed(monkeypatch):
    import transaction_executor

    transaction_id = "EXEC-CLAIM-ERROR-001"
    calls = []

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")

    def fail_claim(value):
        calls.append(("claim", value))
        raise RuntimeError("simulated database error")

    def mark_simulated(value):
        calls.append(("mark_simulated", value))
        return True

    monkeypatch.setattr(
        transaction_executor.database,
        "claim_transaction_execution",
        fail_claim,
    )
    monkeypatch.setattr(
        transaction_executor.database,
        "mark_transaction_execution_simulated",
        mark_simulated,
    )

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert "duplicate protection is unavailable" in result["reason"]
    assert calls == [("claim", transaction_id)]


def test_simulation_status_exception_fails_closed(monkeypatch):
    import transaction_executor

    transaction_id = "EXEC-MARK-ERROR-001"
    calls = []

    monkeypatch.setenv("DATABASE_URL", "postgresql://test-only")

    def claim(value):
        calls.append(("claim", value))
        return True

    def fail_mark(value):
        calls.append(("mark_simulated", value))
        raise RuntimeError("simulated database error")

    monkeypatch.setattr(
        transaction_executor.database,
        "claim_transaction_execution",
        claim,
    )
    monkeypatch.setattr(
        transaction_executor.database,
        "mark_transaction_execution_simulated",
        fail_mark,
    )

    result = execute_transaction(
        make_transaction(transaction_id),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["outcome_uncertain"] is True
    assert result["simulation"] is True
    assert result["funds_moved"] is False
    assert "do not retry automatically" in result["reason"]
    assert calls == [
        ("claim", transaction_id),
        ("mark_simulated", transaction_id),
    ]

def test_reused_transaction_id_with_changed_details_is_blocked(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    transaction_id = "EXEC-ID-REUSE-001"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    original = make_transaction(transaction_id)
    changed = original.model_copy(
        update={"receiver": "receiver_different", "amount": 99999}
    )
    approved = {
        "execution_allowed": True,
        "status": "READY_FOR_EXECUTION",
    }

    first_result = execute_transaction(original, approved)
    second_result = execute_transaction(changed, approved)

    assert first_result["status"] == "SIMULATED_EXECUTION"
    assert first_result["funds_moved"] is False
    assert second_result["status"] == "DUPLICATE"
    assert second_result["executed"] is False

    EXECUTED_TRANSACTIONS.discard(transaction_id)

def test_string_execution_check_is_blocked_without_claiming(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    transaction_id = "EXEC-INVALID-GATE-STRING"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    result = execute_transaction(make_transaction(transaction_id), "yes")

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert transaction_id not in EXECUTED_TRANSACTIONS


def test_list_execution_check_is_blocked_without_claiming(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    transaction_id = "EXEC-INVALID-GATE-LIST"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    result = execute_transaction(
        make_transaction(transaction_id),
        ["approved"],
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert transaction_id not in EXECUTED_TRANSACTIONS


def test_execution_check_with_raising_truthiness_is_blocked(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    transaction_id = "EXEC-GATE-RAISING-BOOL"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    class RaisingTruthiness:
        def __bool__(self):
            raise RuntimeError("unexpected truthiness error")

    result = execute_transaction(
        make_transaction(transaction_id),
        RaisingTruthiness(),
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert "invalid" in result["reason"].lower()
    assert transaction_id not in EXECUTED_TRANSACTIONS


def test_execution_check_dict_subclass_is_blocked(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    transaction_id = "EXEC-GATE-RAISING-GET"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    class RaisingGateDict(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("unexpected gate inspection error")

    result = execute_transaction(
        make_transaction(transaction_id),
        RaisingGateDict({"execution_allowed": True}),
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert "invalid" in result["reason"].lower()
    assert transaction_id not in EXECUTED_TRANSACTIONS


def test_invalid_transaction_data_is_blocked_before_claim(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    transaction_id = "EXEC-INVALID-TRANSACTION-DATA"
    EXECUTED_TRANSACTIONS.discard(transaction_id)

    class BrokenTransaction:
        def __init__(self):
            self.transaction_id = transaction_id

        @property
        def sender(self):
            raise RuntimeError("transaction data unavailable")

    result = execute_transaction(
        BrokenTransaction(),
        {"execution_allowed": True, "status": "READY_FOR_EXECUTION"},
    )

    assert result["executed"] is False
    assert result["status"] == "BLOCKED"
    assert "could not be validated" in result["reason"]
    assert transaction_id not in EXECUTED_TRANSACTIONS
