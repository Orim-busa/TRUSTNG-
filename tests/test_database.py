import database


def test_initialize_database_creates_required_tables(monkeypatch):
    executed_statements = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            executed_statements.append(statement)

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    database.initialize_database()

    assert len(executed_statements) > 2

    assert "CREATE TABLE IF NOT EXISTS processed_transactions" in (
        executed_statements[0]
    )

    assert "transaction_id TEXT PRIMARY KEY" in executed_statements[0]
    assert "fingerprint JSONB NOT NULL" in executed_statements[0]
    assert "result JSONB NOT NULL" in executed_statements[0]

    assert "CREATE TABLE IF NOT EXISTS transaction_executions" in (
        executed_statements[1]
    )

    assert "transaction_id TEXT PRIMARY KEY" in executed_statements[1]
    assert "status TEXT NOT NULL" in executed_statements[1]
    assert "claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()" in (
        executed_statements[1]
    )
    assert "executed_at TIMESTAMPTZ" in executed_statements[1]
    assert any(
        "ADD COLUMN IF NOT EXISTS claimed_at" in statement
        for statement in executed_statements
    )
    assert any(
        "ALTER COLUMN executed_at DROP NOT NULL" in statement
        for statement in executed_statements
    )
    assert not any(
        "SET executed_at = NULL" in statement
        for statement in executed_statements
    )


def test_check_database_connection_returns_true(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {"connection_ok": 1}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.check_database_connection() is True


def test_check_database_connection_returns_false(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {"connection_ok": 0}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.check_database_connection() is False


def test_get_processed_transaction_returns_none_when_missing(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.get_processed_transaction("TX-001") is None


def test_get_processed_transaction_returns_stored_record(monkeypatch):
    from datetime import datetime, timezone

    stored_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {
                "transaction_id": "TX-001",
                "fingerprint": ["sender", "receiver", 100],
                "result": {"status": "ALLOWED"},
                "stored_at": stored_at,
            }

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    result = database.get_processed_transaction("TX-001")

    assert result["stored_at"] == stored_at.isoformat()
    assert result["fingerprint"] == ("sender", "receiver", 100)
    assert result["result"] == {"status": "ALLOWED"}


def test_save_processed_transaction_returns_true_when_inserted(monkeypatch):
    from unittest.mock import Mock

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            assert "ON CONFLICT (transaction_id) DO NOTHING" in statement
            assert parameters[0] == "TX-001"
            return self

        def fetchone(self):
            return {"transaction_id": "TX-001"}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    result = database.save_processed_transaction(
        "TX-001",
        ("sender", "receiver", 100),
        {"status": "ALLOWED"},
    )

    assert result is True


def test_save_processed_transaction_returns_false_for_duplicate(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    result = database.save_processed_transaction(
        "TX-001",
        ("sender", "receiver", 100),
        {"status": "ALLOWED"},
    )

    assert result is False


def test_get_processed_transaction_count(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {"transaction_count": 5}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.get_processed_transaction_count() == 5


def test_claim_transaction_execution_returns_true_when_claimed(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            assert "ON CONFLICT (transaction_id) DO NOTHING" in statement
            assert "'PENDING'" in statement
            assert "RETURNING transaction_id" in statement
            return self

        def fetchone(self):
            return {"transaction_id": "TX-001"}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.claim_transaction_execution("TX-001") is True


def test_claim_transaction_execution_returns_false_for_duplicate(
    monkeypatch,
):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.claim_transaction_execution("TX-001") is False


def test_claim_transaction_execution_rejects_missing_id():
    import pytest

    with pytest.raises(ValueError, match="Transaction ID is required"):
        database.claim_transaction_execution("")


def test_get_transaction_execution_returns_none_when_missing(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.get_transaction_execution("TX-001") is None


def test_get_transaction_execution_returns_stored_record(monkeypatch):
    from datetime import datetime, timezone

    executed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {
                "transaction_id": "TX-001",
                "status": "EXECUTED",
                "executed_at": executed_at,
            }

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    result = database.get_transaction_execution("TX-001")

    assert result == {
        "transaction_id": "TX-001",
        "status": "EXECUTED",
        "executed_at": executed_at.isoformat(),
    }

def test_complete_transaction_execution_updates_only_pending_records(
    monkeypatch,
):
    statements = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            statements.append((statement, parameters))
            return self

        def fetchone(self):
            return {"transaction_id": "TX-001"}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.complete_transaction_execution("TX-001") is True

    assert len(statements) == 1

    statement, parameters = statements[0]

    assert "SET status = 'EXECUTED'" in statement
    assert "executed_at = NOW()" in statement
    assert "status = 'PENDING'" in statement
    assert "RETURNING transaction_id" in statement
    assert parameters == ("TX-001",)


def test_complete_transaction_execution_returns_false_if_not_pending(
    monkeypatch,
):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.complete_transaction_execution("TX-001") is False


def test_complete_transaction_execution_rejects_missing_id():
    import pytest

    with pytest.raises(ValueError, match="Transaction ID is required"):
        database.complete_transaction_execution("")


def test_get_transaction_execution_handles_pending_record(
    monkeypatch,
):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            return self

        def fetchone(self):
            return {
                "transaction_id": "TX-PENDING",
                "status": "PENDING",
                "executed_at": None,
            }

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    result = database.get_transaction_execution("TX-PENDING")

    assert result == {
        "transaction_id": "TX-PENDING",
        "status": "PENDING",
        "executed_at": None,
    }


def test_update_processed_transaction_result_only_updates_processing(monkeypatch):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            assert "result->>'status' = 'PROCESSING'" in statement
            assert parameters[1] == "TX-001"
            assert parameters[0].obj == {"status": "ALLOWED"}
            return self

        def fetchone(self):
            return {"transaction_id": "TX-001"}

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.update_processed_transaction_result(
        "TX-001",
        {"status": "ALLOWED"},
    ) is True


def test_update_processed_transaction_result_returns_false_if_not_processing(
    monkeypatch,
):
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            assert "result->>'status' = 'PROCESSING'" in statement
            return self

        def fetchone(self):
            return None

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    assert database.update_processed_transaction_result(
        "TX-001",
        {"status": "BLOCKED"},
    ) is False


def test_list_pending_transaction_executions_returns_candidates(monkeypatch):
    from datetime import datetime, timezone

    claimed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def execute(self, statement, parameters=None):
            captured["statement"] = statement
            captured["parameters"] = parameters
            return self

        def fetchall(self):
            return [{
                "transaction_id": "TX-UNCERTAIN-001",
                "status": "PENDING",
                "claimed_at": claimed_at,
                "executed_at": None,
                "transaction_status": "RECONCILIATION_REQUIRED",
                "transaction_message": "Check provider status",
            }]

    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: FakeConnection(),
    )

    result = database.list_pending_transaction_executions(
        older_than_minutes=5,
        limit=20,
    )

    assert len(result) == 1
    assert result[0]["transaction_id"] == "TX-UNCERTAIN-001"
    assert result[0]["execution_status"] == "PENDING"
    assert result[0]["executed_at"] is None
    assert result[0]["resolution"] == "REQUIRES_PROVIDER_STATUS_CHECK"
    assert "NOW()" in captured["statement"]
    assert captured["parameters"] == (5, 20)


def test_list_pending_transaction_executions_validates_arguments():
    import pytest

    with pytest.raises(ValueError):
        database.list_pending_transaction_executions(
            older_than_minutes=-1,
        )

    with pytest.raises(ValueError):
        database.list_pending_transaction_executions(limit=201)
