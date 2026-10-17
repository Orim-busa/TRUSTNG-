
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def get_database_connection():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set it in the environment before using PostgreSQL."
        )

    return psycopg.connect(
        database_url,
        connect_timeout=10,
        row_factory=dict_row,
    )


def initialize_database():
    """Create the required database tables if necessary."""

    with get_database_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_transactions (
                transaction_id TEXT PRIMARY KEY,
                fingerprint JSONB NOT NULL,
                result JSONB NOT NULL,
                stored_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transaction_executions (
                transaction_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                executed_at TIMESTAMPTZ
            )
            """
        )

        # Safely migrate databases created with the older schema.
        connection.execute(
            """
            ALTER TABLE transaction_executions
            ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ
            """
        )

        connection.execute(
            """
            UPDATE transaction_executions
            SET claimed_at = COALESCE(claimed_at, executed_at, NOW())
            WHERE claimed_at IS NULL
            """
        )

        connection.execute(
            """
            ALTER TABLE transaction_executions
            ALTER COLUMN claimed_at SET DEFAULT NOW()
            """
        )

        connection.execute(
            """
            ALTER TABLE transaction_executions
            ALTER COLUMN claimed_at SET NOT NULL
            """
        )

        connection.execute(
            """
            ALTER TABLE transaction_executions
            ALTER COLUMN executed_at DROP NOT NULL
            """
        )

        connection.execute(
            """
            ALTER TABLE transaction_executions
            ALTER COLUMN executed_at DROP DEFAULT
            """
        )


def check_database_connection():
    """Verify that PostgreSQL accepts a connection."""

    with get_database_connection() as connection:
        row = connection.execute(
            "SELECT 1 AS connection_ok"
        ).fetchone()

    return row["connection_ok"] == 1


def get_processed_transaction(transaction_id):
    """Retrieve a previously stored transaction."""

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT transaction_id, fingerprint, result, stored_at
            FROM processed_transactions
            WHERE transaction_id = %s
            """,
            (transaction_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "stored_at": row["stored_at"].isoformat(),
        "fingerprint": tuple(row["fingerprint"]),
        "result": row["result"],
    }


def save_processed_transaction(transaction_id, fingerprint, result):
    """
    Insert a transaction without overwriting an existing ID.

    Returns True if inserted, or False if that ID already exists.
    """

    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO processed_transactions
                (transaction_id, fingerprint, result)
            VALUES (%s, %s, %s)
            ON CONFLICT (transaction_id) DO NOTHING
            RETURNING transaction_id
            """,
            (
                transaction_id,
                Jsonb(list(fingerprint)),
                Jsonb(result),
            ),
        ).fetchone()

    return row is not None


def update_processed_transaction_result(transaction_id, result):
    """
    Atomically finalize a reserved transaction only while it is PROCESSING.

    Returns True if the reservation was finalized, otherwise False.
    """
    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            UPDATE processed_transactions
            SET result = %s
            WHERE transaction_id = %s
              AND result->>'status' = 'PROCESSING'
            RETURNING transaction_id
            """,
            (
                Jsonb(result),
                transaction_id,
            ),
        ).fetchone()

    return row is not None

def get_processed_transaction_count():
    """Return the number of stored transaction records."""

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS transaction_count
            FROM processed_transactions
            """
        ).fetchone()

    return row["transaction_count"]


def claim_transaction_execution(transaction_id):
    """
    Atomically claim a transaction ID for simulated execution.

    New claims start as PENDING.
    A duplicate claim returns False.
    """

    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO transaction_executions
                (transaction_id, status)
            VALUES (%s, 'PENDING')
            ON CONFLICT (transaction_id) DO NOTHING
            RETURNING transaction_id
            """,
            (transaction_id,),
        ).fetchone()

    return row is not None


def complete_transaction_execution(transaction_id):
    """
    Mark a claimed transaction as EXECUTED.

    Only a transaction currently marked PENDING can be completed.
    Returns True if its status was updated, otherwise False.
    """

    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            UPDATE transaction_executions
            SET status = 'EXECUTED',
                executed_at = NOW()
            WHERE transaction_id = %s
              AND status = 'PENDING'
            RETURNING transaction_id
            """,
            (transaction_id,),
        ).fetchone()

    return row is not None


def get_transaction_execution(transaction_id):
    """Retrieve a previously recorded execution."""

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT transaction_id, status, executed_at
            FROM transaction_executions
            WHERE transaction_id = %s
            """,
            (transaction_id,),
        ).fetchone()

    if row is None:
        return None

    executed_at = row["executed_at"]

    return {
        "transaction_id": row["transaction_id"],
        "status": row["status"],
        "executed_at": (
            executed_at.isoformat()
            if executed_at is not None
            else None
        ),
    }
