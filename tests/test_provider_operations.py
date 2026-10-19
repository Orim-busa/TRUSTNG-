from datetime import datetime, timezone

import pytest

import database


def install_fake_connection(monkeypatch, row=None, error=None):
    calls = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            calls.append((statement, parameters))
            if error is not None:
                raise error
            return self

        def fetchone(self):
            return row

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )
    return calls


def test_initialize_database_creates_provider_operations_table(monkeypatch):
    statements = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            statements.append(statement)
            return self

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    database.initialize_database()

    schema = "\n".join(statements)
    assert "CREATE TABLE IF NOT EXISTS provider_operations" in schema
    assert "idempotency_key TEXT PRIMARY KEY" in schema
    assert "request_fingerprint TEXT NOT NULL" in schema
    assert "'RECONCILIATION_REQUIRED'" in schema
    assert "UNIQUE (provider, transaction_id)" in schema
    assert "CREATE INDEX IF NOT EXISTS idx_provider_operations_status_updated" in schema


def test_reserve_provider_operation_returns_true_for_new_record(monkeypatch):
    calls = install_fake_connection(
        monkeypatch,
        row={"idempotency_key": "key-001"},
    )

    result = database.reserve_provider_operation(
        "key-001", "sandbox", "TX-001", "fingerprint-001"
    )

    assert result is True
    statement, parameters = calls[0]
    assert "INSERT INTO provider_operations" in statement
    assert "ON CONFLICT DO NOTHING" in statement
    assert parameters == (
        "key-001", "sandbox", "TX-001", "fingerprint-001"
    )


def test_reserve_provider_operation_returns_false_for_duplicate(monkeypatch):
    install_fake_connection(monkeypatch, row=None)

    assert database.reserve_provider_operation(
        "key-001", "sandbox", "TX-001", "fingerprint-001"
    ) is False


@pytest.mark.parametrize(
    "values",
    [
        ("", "sandbox", "TX-001", "fingerprint"),
        ("key", "", "TX-001", "fingerprint"),
        ("key", "sandbox", "", "fingerprint"),
        ("key", "sandbox", "TX-001", ""),
    ],
)
def test_reserve_provider_operation_requires_all_identifiers(
    values, monkeypatch
):
    with pytest.raises(ValueError):
        database.reserve_provider_operation(*values)


def test_get_provider_operation_returns_none_when_missing(monkeypatch):
    install_fake_connection(monkeypatch, row=None)

    assert database.get_provider_operation("key-001") is None


def test_get_provider_operation_formats_timestamps(monkeypatch):
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    record = {
        "idempotency_key": "key-001",
        "provider": "sandbox",
        "transaction_id": "TX-001",
        "request_fingerprint": "fingerprint-001",
        "status": "PENDING",
        "provider_reference": None,
        "result": {},
        "created_at": now,
        "updated_at": now,
    }
    install_fake_connection(monkeypatch, row=record)

    result = database.get_provider_operation("key-001")

    assert result["status"] == "PENDING"
    assert result["created_at"] == now.isoformat()
    assert result["updated_at"] == now.isoformat()


def test_reconciliation_transition_only_updates_pending_record(monkeypatch):
    calls = install_fake_connection(
        monkeypatch,
        row={"idempotency_key": "key-001"},
    )

    result = database.update_provider_operation_status(
        "key-001",
        "RECONCILIATION_REQUIRED",
        {"reason": "simulated timeout"},
    )

    assert result is True
    statement, parameters = calls[0]
    assert "UPDATE provider_operations" in statement
    assert "status = ANY(%s)" in statement
    assert parameters[0] == "RECONCILIATION_REQUIRED"
    assert parameters[3] == "key-001"
    assert parameters[4] == ["PENDING"]


@pytest.mark.parametrize("status", ["SUCCEEDED", "FAILED"])
def test_final_outcomes_require_authoritative_confirmation(status, monkeypatch):
    with pytest.raises(ValueError, match="authoritative=True"):
        database.update_provider_operation_status(
            "key-001", status, {"status": status}
        )


@pytest.mark.parametrize(
    "status",
    ["SUCCEEDED", "FAILED", "RECONCILIATION_REQUIRED"],
)
def test_allowed_status_update_uses_atomic_conditional_update(
    status, monkeypatch
):
    calls = install_fake_connection(
        monkeypatch,
        row={"idempotency_key": "key-001"},
    )

    result = database.update_provider_operation_status(
        "key-001",
        status,
        {"provider_status": status},
        provider_reference="provider-ref-001",
        authoritative=status in {"SUCCEEDED", "FAILED"},
    )

    assert result is True
    statement, parameters = calls[0]
    assert "WHERE idempotency_key = %s" in statement
    assert "AND status = ANY(%s)" in statement
    assert parameters[0] == status
    assert parameters[2] == "provider-ref-001"


def test_final_outcome_can_be_marked_from_reconciliation_state(monkeypatch):
    calls = install_fake_connection(
        monkeypatch,
        row={"idempotency_key": "key-001"},
    )

    database.update_provider_operation_status(
        "key-001",
        "SUCCEEDED",
        {"provider_status": "confirmed"},
        authoritative=True,
    )

    assert calls[0][1][4] == ["PENDING", "RECONCILIATION_REQUIRED"]


def test_status_update_returns_false_when_record_is_not_eligible(monkeypatch):
    install_fake_connection(monkeypatch, row=None)

    assert database.update_provider_operation_status(
        "key-001",
        "FAILED",
        {"provider_status": "failed"},
        authoritative=True,
    ) is False


def test_database_errors_propagate_for_fail_closed_behavior(monkeypatch):
    install_fake_connection(
        monkeypatch,
        error=RuntimeError("database unavailable"),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        database.reserve_provider_operation(
            "key-001", "sandbox", "TX-001", "fingerprint-001"
        )


@pytest.mark.parametrize(
    "status,result",
    [
        ("UNKNOWN", {}),
        ("SUCCEEDED", []),
        ("FAILED", {}),
    ],
)
def test_invalid_status_update_is_rejected(status, result, monkeypatch):
    with pytest.raises(ValueError):
        database.update_provider_operation_status(
            "key-001",
            status,
            result,
            authoritative=False,
        )


@pytest.mark.parametrize(
    ("existing_fingerprint", "new_fingerprint", "expected"),
    [
        ("fp-1", "fp-1", "CHECK_PROVIDER_STATUS"),
        ("fp-1", "fp-2", "CONFLICT"),
    ],
)
def test_reserve_or_inspect_classifies_existing_operation(
    monkeypatch, existing_fingerprint, new_fingerprint, expected
):
    record = {
        "idempotency_key": "key-1",
        "provider": "sandbox",
        "transaction_id": "TX-1",
        "request_fingerprint": existing_fingerprint,
        "status": "PENDING",
        "provider_reference": None,
        "result": {},
        "created_at": None,
        "updated_at": None,
    }

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, parameters=None):
            self.insert_result = self if not hasattr(self, "inserted") else None
            self.inserted = True
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return [record]

    connection = FakeConnection()
    calls = {"count": 0}

    def fake_connection():
        return connection

    original_execute = connection.execute

    def execute(statement, parameters=None):
        calls["count"] += 1
        if calls["count"] == 1:
            connection.inserted = True
            return connection
        return connection

    connection.execute = execute
    monkeypatch.setattr(database, "get_database_connection", fake_connection)
    result = database.reserve_or_inspect_provider_operation(
        "key-1", "sandbox", "TX-1", new_fingerprint
    )
    assert result["decision"] == expected
    if expected == "CHECK_PROVIDER_STATUS":
        assert result["operation"]["status"] == "PENDING"
    else:
        assert result["operation"] is None


def test_reserve_or_inspect_returns_reserved_for_new_operation(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {"idempotency_key": "key-new"}

    monkeypatch.setattr(
        database, "get_database_connection", lambda: FakeConnection()
    )
    result = database.reserve_or_inspect_provider_operation(
        "key-new", "sandbox", "TX-new", "fp-new"
    )
    assert result == {"decision": "RESERVED", "operation": None}


def test_reserve_or_inspect_returns_not_found(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    monkeypatch.setattr(
        database, "get_database_connection", lambda: FakeConnection()
    )
    result = database.reserve_or_inspect_provider_operation(
        "key-missing", "sandbox", "TX-missing", "fp-missing"
    )
    assert result == {"decision": "NOT_FOUND", "operation": None}


def test_reserve_or_inspect_rejects_multiple_conflicting_records(monkeypatch):
    matching = {
        "idempotency_key": "key-1",
        "provider": "sandbox",
        "transaction_id": "TX-1",
        "request_fingerprint": "fp-1",
        "status": "PENDING",
        "provider_reference": None,
        "result": {},
        "created_at": None,
        "updated_at": None,
    }
    conflicting = {
        **matching,
        "idempotency_key": "another-key",
        "transaction_id": "TX-2",
    }

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return [matching, conflicting]

    monkeypatch.setattr(
        database, "get_database_connection", lambda: FakeConnection()
    )
    result = database.reserve_or_inspect_provider_operation(
        "key-1", "sandbox", "TX-1", "fp-1"
    )
    assert result == {"decision": "CONFLICT", "operation": None}


@pytest.mark.parametrize(
    "existing_status",
    [
        "PENDING",
        "RECONCILIATION_REQUIRED",
        "SUCCEEDED",
        "FAILED",
    ],
)
def test_existing_provider_operation_replay_preserves_recovery_state(
    monkeypatch, existing_status
):
    record = {
        "idempotency_key": "recovery-key-1",
        "provider": "sandbox",
        "transaction_id": "RECOVERY-TX-1",
        "request_fingerprint": "recovery-fingerprint-1",
        "status": existing_status,
        "provider_reference": None,
        "result": {"status": existing_status},
        "created_at": None,
        "updated_at": None,
    }

    class FakeConnection:
        def __init__(self):
            self.execute_count = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, parameters=None):
            self.execute_count += 1
            return self

        def fetchone(self):
            # Simulate ON CONFLICT DO NOTHING: no new reservation.
            return None

        def fetchall(self):
            return [record]

    connection = FakeConnection()
    monkeypatch.setattr(
        database, "get_database_connection", lambda: connection
    )

    result = database.reserve_or_inspect_provider_operation(
        "recovery-key-1",
        "sandbox",
        "RECOVERY-TX-1",
        "recovery-fingerprint-1",
    )

    expected_decision = {
        "PENDING": "CHECK_PROVIDER_STATUS",
        "RECONCILIATION_REQUIRED": "RECONCILE",
        "SUCCEEDED": "REPLAY",
        "FAILED": "REPLAY",
    }[existing_status]
    assert result["decision"] == expected_decision
    assert result["operation"]["status"] == existing_status
    assert result["operation"]["result"] == {"status": existing_status}
    assert connection.execute_count == 2

def test_reserve_or_inspect_rejects_unknown_existing_status(monkeypatch):
    record = {
        "idempotency_key": "unknown-status-key",
        "provider": "sandbox",
        "transaction_id": "UNKNOWN-STATUS-TX",
        "request_fingerprint": "unknown-status-fingerprint",
        "status": "UNEXPECTED_STATUS",
        "provider_reference": None,
        "result": {},
        "created_at": None,
        "updated_at": None,
    }

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return [record]

    monkeypatch.setattr(
        database, "get_database_connection", lambda: FakeConnection()
    )

    result = database.reserve_or_inspect_provider_operation(
        "unknown-status-key",
        "sandbox",
        "UNKNOWN-STATUS-TX",
        "unknown-status-fingerprint",
    )

    assert result == {"decision": "CONFLICT", "operation": None}
