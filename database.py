
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

        # Persist authorization consumption across restarts and instances.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS consumed_authorizations (
                authorization_id TEXT PRIMARY KEY,
                consumed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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





        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_transaction_executions_status_claimed_at
            ON transaction_executions (status, claimed_at)
            """
        )

        # Provider-operation records are separate from simulated executions.
        # They reserve an idempotency key before a future provider request.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_operations (
                idempotency_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN (
                        'PENDING',
                        'SUCCEEDED',
                        'FAILED',
                        'RECONCILIATION_REQUIRED'
                    )
                ),
                provider_reference TEXT,
                result JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (provider, transaction_id)
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_operations_status_updated
            ON provider_operations (status, updated_at)
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


def consume_authorization(authorization_id):
    """
    Atomically consume an authorization ID.

    Returns True for the first claim and False if already consumed.
    Database errors propagate so callers can fail closed.
    """
    if not isinstance(authorization_id, str) or not authorization_id.strip():
        raise ValueError("Authorization ID is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO consumed_authorizations (authorization_id)
            VALUES (%s)
            ON CONFLICT (authorization_id) DO NOTHING
            RETURNING authorization_id
            """,
            (authorization_id,),
        ).fetchone()

    return row is not None


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


def list_pending_transaction_executions(
    older_than_minutes=5,
    limit=50,
):
    """
    List execution claims that remain PENDING beyond the grace period.

    These are reconciliation candidates, not proof of successful or failed
    payments. A provider's authoritative status must be checked separately.
    """
    if not isinstance(older_than_minutes, int) or older_than_minutes < 0:
        raise ValueError("older_than_minutes must be a non-negative integer")
    if not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                te.transaction_id,
                te.status,
                te.claimed_at,
                te.executed_at,
                pt.result->>'status' AS transaction_status,
                pt.result->>'message' AS transaction_message
            FROM transaction_executions AS te
            LEFT JOIN processed_transactions AS pt
                ON pt.transaction_id = te.transaction_id
            WHERE te.status = 'PENDING'
              AND te.claimed_at <=
                  NOW() - (%s * INTERVAL '1 minute')
            ORDER BY te.claimed_at ASC
            LIMIT %s
            """,
            (older_than_minutes, limit),
        ).fetchall()

    candidates = []
    for row in rows:
        candidates.append({
            "transaction_id": row["transaction_id"],
            "execution_status": row["status"],
            "claimed_at": (
                row["claimed_at"].isoformat()
                if row["claimed_at"] is not None
                else None
            ),
            "executed_at": (
                row["executed_at"].isoformat()
                if row["executed_at"] is not None
                else None
            ),
            "transaction_status": row["transaction_status"],
            "transaction_message": row["transaction_message"],
            "resolution": "REQUIRES_PROVIDER_STATUS_CHECK",
        })

    return candidates


def reserve_provider_operation(
    idempotency_key,
    provider,
    transaction_id,
    request_fingerprint,
):
    """
    Atomically reserve a provider operation.

    Returns True only when a new operation is inserted. A duplicate key or
    duplicate transaction for the same provider returns False. Database
    errors propagate so callers can fail closed.
    """
    values = {
        "idempotency_key": idempotency_key,
        "provider": provider,
        "transaction_id": transaction_id,
        "request_fingerprint": request_fingerprint,
    }
    for name, value in values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO provider_operations (
                idempotency_key,
                provider,
                transaction_id,
                request_fingerprint,
                status
            )
            VALUES (%s, %s, %s, %s, 'PENDING')
            ON CONFLICT DO NOTHING
            RETURNING idempotency_key
            """,
            (
                idempotency_key,
                provider,
                transaction_id,
                request_fingerprint,
            ),
        ).fetchone()

    return row is not None



def reserve_or_inspect_provider_operation(
    idempotency_key,
    provider,
    transaction_id,
    request_fingerprint,
):
    """
    Reserve a new operation or classify an existing reservation.

    Returns RESERVED for a new operation; CHECK_PROVIDER_STATUS for an
    existing PENDING operation; RECONCILE for RECONCILIATION_REQUIRED;
    REPLAY for a final SUCCEEDED or FAILED result; or CONFLICT/NOT_FOUND.
    This function never submits a provider request.
    """
    values = {
        "idempotency_key": idempotency_key,
        "provider": provider,
        "transaction_id": transaction_id,
        "request_fingerprint": request_fingerprint,
    }
    for name, value in values.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required.")

    with get_database_connection() as connection:
        inserted = connection.execute(
            """
            INSERT INTO provider_operations (
                idempotency_key,
                provider,
                transaction_id,
                request_fingerprint,
                status
            )
            VALUES (%s, %s, %s, %s, 'PENDING')
            ON CONFLICT DO NOTHING
            RETURNING idempotency_key
            """,
            (
                idempotency_key,
                provider,
                transaction_id,
                request_fingerprint,
            ),
        ).fetchone()

        if inserted is not None:
            return {"decision": "RESERVED", "operation": None}

        rows = connection.execute(
            """
            SELECT
                idempotency_key,
                provider,
                transaction_id,
                request_fingerprint,
                status,
                provider_reference,
                result,
                created_at,
                updated_at
            FROM provider_operations
            WHERE idempotency_key = %s
               OR (provider = %s AND transaction_id = %s)
            """,
            (idempotency_key, provider, transaction_id),
        ).fetchall()

    if not rows:
        return {"decision": "NOT_FOUND", "operation": None}

    # More than one matching row means the unique constraints identify
    # conflicting records. Never accept a replay in that situation.
    if len(rows) != 1:
        return {"decision": "CONFLICT", "operation": None}

    record = dict(rows[0])
    if not (
        record["idempotency_key"] == idempotency_key
        and record["provider"] == provider
        and record["transaction_id"] == transaction_id
        and record["request_fingerprint"] == request_fingerprint
    ):
        return {"decision": "CONFLICT", "operation": None}

    for field in ("created_at", "updated_at"):
        value = record.get(field)
        if value is not None:
            record[field] = value.isoformat()

    recovery_decisions = {
        "PENDING": "CHECK_PROVIDER_STATUS",
        "RECONCILIATION_REQUIRED": "RECONCILE",
        "SUCCEEDED": "REPLAY",
        "FAILED": "REPLAY",
    }
    decision = recovery_decisions.get(record["status"])
    if decision is None:
        return {"decision": "CONFLICT", "operation": None}

    return {"decision": decision, "operation": record}


def get_provider_operation(idempotency_key):
    """Retrieve a provider-operation record by idempotency key."""
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT
                idempotency_key,
                provider,
                transaction_id,
                request_fingerprint,
                status,
                provider_reference,
                result,
                created_at,
                updated_at
            FROM provider_operations
            WHERE idempotency_key = %s
            """,
            (idempotency_key,),
        ).fetchone()

    if row is None:
        return None

    record = dict(row)
    for field in ("created_at", "updated_at"):
        if record[field] is not None:
            record[field] = record[field].isoformat()

    return record


def update_provider_operation_status(
    idempotency_key,
    status,
    result,
    provider_reference=None,
    *,
    authoritative=False,
):
    """
    Safely advance a provider operation.

    PENDING may become RECONCILIATION_REQUIRED without a final provider
    decision. SUCCEEDED and FAILED require authoritative=True and may only
    be written from PENDING or RECONCILIATION_REQUIRED.

    Final states cannot be overwritten. Returns True when updated, False
    when no eligible record was updated. Database errors propagate.
    """
    allowed_statuses = {
        "SUCCEEDED",
        "FAILED",
        "RECONCILIATION_REQUIRED",
    }
    if status not in allowed_statuses:
        raise ValueError("Unsupported provider-operation status.")

    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("idempotency_key is required.")

    if not isinstance(result, dict):
        raise ValueError("result must be a dictionary.")

    if status in {"SUCCEEDED", "FAILED"} and authoritative is not True:
        raise ValueError(
            "SUCCEEDED and FAILED require authoritative=True."
        )

    if provider_reference is not None and not isinstance(
        provider_reference, str
    ):
        raise ValueError("provider_reference must be a string or None.")

    from psycopg.types.json import Jsonb

    if status == "RECONCILIATION_REQUIRED":
        eligible_statuses = ("PENDING",)
    else:
        eligible_statuses = ("PENDING", "RECONCILIATION_REQUIRED")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            UPDATE provider_operations
            SET status = %s,
                result = %s,
                provider_reference = COALESCE(%s, provider_reference),
                updated_at = NOW()
            WHERE idempotency_key = %s
              AND status = ANY(%s)
            RETURNING idempotency_key
            """,
            (
                status,
                Jsonb(result),
                provider_reference,
                idempotency_key,
                list(eligible_statuses),
            ),
        ).fetchone()

    return row is not None
