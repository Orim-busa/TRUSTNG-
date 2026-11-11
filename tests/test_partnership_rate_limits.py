import pytest

import database


class FakeCursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, counts):
        self.counts = counts
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement, parameters=None):
        self.statements.append((statement, parameters))

        if "COUNT(*) FILTER" in statement:
            return FakeCursor(self.counts)

        return FakeCursor()


def install_fake_connection(monkeypatch, counts):
    connection = FakeConnection(counts)
    monkeypatch.setattr(
        database,
        "get_database_connection",
        lambda: connection,
    )
    return connection


def test_partnership_rate_limit_accepts_request_below_limits(monkeypatch):
    connection = install_fake_connection(
        monkeypatch,
        {
            "short_window_count": 1,
            "hourly_window_count": 3,
        },
    )

    result = database.consume_partnership_rate_limit("a" * 64)

    assert result is True

    statements = [statement for statement, _ in connection.statements]
    assert "pg_advisory_xact_lock" in statements[0]
    assert "COUNT(*) FILTER" in statements[1]
    assert "INSERT INTO partnership_rate_limit_events" in statements[2]
    assert "DELETE FROM partnership_rate_limit_events" in statements[3]


@pytest.mark.parametrize(
    "counts",
    [
        {"short_window_count": 2, "hourly_window_count": 2},
        {"short_window_count": 1, "hourly_window_count": 5},
        {"short_window_count": 2, "hourly_window_count": 5},
    ],
)
def test_partnership_rate_limit_rejects_exhausted_window(
    monkeypatch, counts
):
    connection = install_fake_connection(monkeypatch, counts)

    result = database.consume_partnership_rate_limit("b" * 64)

    assert result is False
    statements = [statement for statement, _ in connection.statements]
    assert "pg_advisory_xact_lock" in statements[0]
    assert "COUNT(*) FILTER" in statements[1]
    assert not any(
        "INSERT INTO partnership_rate_limit_events" in statement
        for statement in statements
    )


@pytest.mark.parametrize(
    "identifier_hash",
    [
        "",
        "not-a-hash",
        "A" * 64,
        "a" * 63,
        "a" * 65,
        None,
    ],
)
def test_partnership_rate_limit_rejects_invalid_identifier(
    monkeypatch, identifier_hash
):
    def unexpected_connection():
        raise AssertionError("Database must not be accessed for invalid input.")

    monkeypatch.setattr(
        database,
        "get_database_connection",
        unexpected_connection,
    )

    with pytest.raises(ValueError):
        database.consume_partnership_rate_limit(identifier_hash)


def test_partnership_rate_limit_database_errors_propagate(monkeypatch):
    def failing_connection():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        database,
        "get_database_connection",
        failing_connection,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        database.consume_partnership_rate_limit("c" * 64)
