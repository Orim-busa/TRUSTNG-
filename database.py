import hashlib
from decimal import Decimal, InvalidOperation

import re
import hmac
import os

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from country_codes import normalize_corridor_countries


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


        # Email registration is not proof of ownership.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipient_email_aliases (
                normalized_email TEXT PRIMARY KEY,
                recipient_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                phone_number TEXT,
                email_ownership_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
                    CHECK (email_ownership_status IN ('UNVERIFIED', 'VERIFIED')),
                phone_ownership_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
                    CHECK (phone_ownership_status IN ('UNVERIFIED', 'VERIFIED')),
                source TEXT NOT NULL DEFAULT 'SANDBOX',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            ALTER TABLE recipient_email_aliases
            ADD COLUMN IF NOT EXISTS phone_number TEXT
            """
        )
        connection.execute(
            """
            ALTER TABLE recipient_email_aliases
            ADD COLUMN IF NOT EXISTS phone_ownership_status TEXT
            NOT NULL DEFAULT 'UNVERIFIED'
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recipient_email_aliases_recipient
            ON recipient_email_aliases (recipient_id)
            """
        )


        # One active verification challenge per registered email.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipient_email_verification_challenges (
                normalized_email TEXT PRIMARY KEY
                    REFERENCES recipient_email_aliases(normalized_email)
                    ON DELETE CASCADE,
                code_hash TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                consumed_at TIMESTAMPTZ
            )
            """
        )

        connection.execute(
            """
            ALTER TABLE recipient_email_verification_challenges
            ADD COLUMN IF NOT EXISTS phone_code_hash TEXT
            """
        )
        connection.execute(
            """
            ALTER TABLE recipient_email_verification_challenges
            ADD COLUMN IF NOT EXISTS phone_attempts INTEGER NOT NULL DEFAULT 0
            """
        )


        # Email-linked requests record risk assessment only; they never move funds.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS email_payment_requests (
                request_id TEXT PRIMARY KEY,
                request_fingerprint TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                asset TEXT NOT NULL,
                amount NUMERIC(24, 8) NOT NULL CHECK (amount > 0),
                channel TEXT NOT NULL,
                country TEXT NOT NULL,
                device_fingerprint TEXT NOT NULL DEFAULT '',
                risk_assessment JSONB NOT NULL,
                status TEXT NOT NULL DEFAULT 'SANDBOX_RISK_ASSESSED'
                    CHECK (status = 'SANDBOX_RISK_ASSESSED'),
                payment_authorized BOOLEAN NOT NULL DEFAULT FALSE
                    CHECK (payment_authorized = FALSE),
                funds_moved BOOLEAN NOT NULL DEFAULT FALSE
                    CHECK (funds_moved = FALSE),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            ALTER TABLE email_payment_requests
            ADD COLUMN IF NOT EXISTS sender_country TEXT
            """
        )
        connection.execute(
            """
            ALTER TABLE email_payment_requests
            ADD COLUMN IF NOT EXISTS receiver_country TEXT
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_payment_requests_recipient
            ON email_payment_requests (recipient_id, created_at DESC)
            """
        )


        # DIJUANG partnership enquiries are stored separately from transaction data.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS partnership_enquiries (
                submission_id TEXT PRIMARY KEY,
                reference TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                business_email TEXT NOT NULL,
                organisation TEXT NOT NULL,
                position TEXT,
                phone TEXT,
                country TEXT,
                partnership_type TEXT NOT NULL,
                other_interest TEXT,
                purpose TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_partnership_enquiries_created
            ON partnership_enquiries (created_at DESC)
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS partnership_rate_limit_events (
                event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                identifier_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_partnership_rate_limit_identifier_created
            ON partnership_rate_limit_events (
                identifier_hash, created_at DESC
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
                idx_partnership_rate_limit_created
            ON partnership_rate_limit_events (created_at)
            """
        )


def create_email_payment_request(
    request_id,
    sender_id,
    recipient_id,
    recipient_email,
    asset,
    amount,
    channel,
    country,
    risk_assessment,
    device_id=None,
    sender_country=None,
    receiver_country=None,
):
    """Persist an email-linked sandbox request after recipient verification."""
    normalized_email = recipient_email.strip().lower()
    normalized_asset = asset.strip().upper()
    normalized_country = country.strip().upper()

    normalized_sender_country, normalized_receiver_country = (
        normalize_corridor_countries(sender_country, receiver_country)
    )

    try:
        amount_decimal = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Amount must be a valid decimal number.")

    if not amount_decimal.is_finite() or amount_decimal <= 0:
        raise ValueError("Amount must be a finite positive number.")

    normalized_decimal = amount_decimal.normalize()
    if (
        max(0, -normalized_decimal.as_tuple().exponent) > 8
        or normalized_decimal.adjusted() > 15
    ):
        raise ValueError("Amount exceeds the supported precision.")

    normalized_amount = format(normalized_decimal, "f")
    normalized_device = str(device_id or "")
    normalized_device_fingerprint = (
        hashlib.sha256(normalized_device.encode("utf-8")).hexdigest()
        if normalized_device
        else ""
    )

    fingerprint_parts = [
        str(sender_id),
        str(recipient_id),
        normalized_email,
        normalized_asset,
        normalized_amount,
        str(channel),
        normalized_country,
        normalized_device_fingerprint,
    ]

    if normalized_sender_country is not None:
        fingerprint_parts.extend(
            (normalized_sender_country, normalized_receiver_country)
        )

    fingerprint_source = "\x1f".join(fingerprint_parts)
    fingerprint = hashlib.sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()

    with get_database_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO email_payment_requests (
                request_id, request_fingerprint, sender_id, recipient_id,
                recipient_email, asset, amount, channel, country,
                sender_country, receiver_country,
                device_fingerprint, risk_assessment
            )
            SELECT %s, %s, %s, aliases.recipient_id,
                   aliases.normalized_email, %s, %s, %s, %s, %s, %s, %s, %s
            FROM recipient_email_aliases AS aliases
            WHERE aliases.normalized_email = %s
              AND aliases.recipient_id = %s
              AND aliases.email_ownership_status = 'VERIFIED'
              AND aliases.phone_ownership_status = 'VERIFIED'
            ON CONFLICT (request_id) DO NOTHING
            RETURNING request_id, recipient_id, status, risk_assessment,
                      payment_authorized, funds_moved, created_at
            """,
            (
                request_id,
                fingerprint,
                sender_id,
                normalized_asset,
                amount_decimal,
                channel,
                normalized_country,
                normalized_sender_country,
                normalized_receiver_country,
                normalized_device_fingerprint,
                Jsonb(risk_assessment),
                normalized_email,
                recipient_id,
            ),
        ).fetchone()

        created = row is not None

        if row is None:
            row = connection.execute(
                """
                SELECT requests.request_id,
                       requests.request_fingerprint,
                       requests.recipient_id,
                       requests.status,
                       requests.risk_assessment,
                       requests.payment_authorized,
                       requests.funds_moved,
                       requests.created_at
                FROM email_payment_requests AS requests
                JOIN recipient_email_aliases AS aliases
                  ON aliases.normalized_email = requests.recipient_email
                WHERE requests.request_id = %s
                  AND aliases.recipient_id = requests.recipient_id
                  AND aliases.email_ownership_status = 'VERIFIED'
                  AND aliases.phone_ownership_status = 'VERIFIED'
                """,
                (request_id,),
            ).fetchone()

            if row is None:
                raise ValueError(
                    "Recipient is no longer fully verified, or the request could not be created."
                )

            if row["request_fingerprint"] != fingerprint:
                raise ValueError(
                    "This request ID has already been used with different payment details."
                )

    return {
        "request_id": row["request_id"],
        "recipient_id": row["recipient_id"],
        "status": row["status"],
        "risk_assessment": row["risk_assessment"],
        "payment_authorized": row["payment_authorized"],
        "funds_moved": row["funds_moved"],
        "created": created,
        "created_at": row["created_at"].isoformat(),
    }


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

def list_recent_processed_transactions(limit=50):
    """Return recent stored transaction results for server-side sanitization.

    Fingerprints are deliberately excluded from this query.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT transaction_id, result, stored_at
            FROM processed_transactions
            ORDER BY stored_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "transaction_id": row["transaction_id"],
            "result": row["result"],
            "stored_at": row["stored_at"].isoformat(),
        }
        for row in rows
    ]




def get_transaction_corridor_summary(limit=5000):
    """Return aggregated, redacted country-pair transaction intelligence."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("limit must be between 1 and 10000")

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                fingerprint->>8 AS origin_country,
                fingerprint->>9 AS destination_country,
                COUNT(*) AS transaction_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(
                        result->'previous_result'->'decision'->>'risk_level',
                        result->'decision'->>'risk_level',
                        result->>'risk_level',
                        'UNKNOWN'
                    ) = 'LOW'
                ) AS low_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(
                        result->'previous_result'->'decision'->>'risk_level',
                        result->'decision'->>'risk_level',
                        result->>'risk_level',
                        'UNKNOWN'
                    ) = 'MEDIUM'
                ) AS medium_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(
                        result->'previous_result'->'decision'->>'risk_level',
                        result->'decision'->>'risk_level',
                        result->>'risk_level',
                        'UNKNOWN'
                    ) = 'HIGH'
                ) AS high_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(
                        result->'previous_result'->'decision'->>'risk_level',
                        result->'decision'->>'risk_level',
                        result->>'risk_level',
                        'UNKNOWN'
                    ) NOT IN ('LOW', 'MEDIUM', 'HIGH')
                ) AS unknown_count
            FROM processed_transactions
            WHERE jsonb_typeof(fingerprint) = 'array'
              AND fingerprint->>8 ~ '^[A-Z]{2}$'
              AND fingerprint->>9 ~ '^[A-Z]{2}$'
              AND fingerprint->>8 <> fingerprint->>9
              AND COALESCE(result->>'status', '') <> 'PROCESSING'
            GROUP BY fingerprint->>8, fingerprint->>9
            ORDER BY COUNT(*) DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "origin_country": row["origin_country"],
            "destination_country": row["destination_country"],
            "transaction_count": int(row["transaction_count"]),
            "risk": {
                "low": int(row["low_count"]),
                "medium": int(row["medium_count"]),
                "high": int(row["high_count"]),
                "unknown": int(row["unknown_count"]),
            },
        }
        for row in rows
    ]


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


def mark_transaction_execution_simulated(transaction_id):
    """Record a simulation without marking a payment as executed."""
    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            UPDATE transaction_executions
            SET status = 'SIMULATED',
                executed_at = NULL
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



def register_recipient_email(email, recipient_id, display_name, phone_number, source="SANDBOX"):
    """Register an email alias without claiming ownership is verified."""
    normalized = email.strip().casefold()
    recipient_id = recipient_id.strip()
    display_name = display_name.strip()
    phone_number = re.sub(r"[\s().-]", "", phone_number.strip())

    if not re.fullmatch(r"\+?[0-9]{7,15}", phone_number):
        raise ValueError("Enter a valid assigned phone number in international format.")
    if len(normalized) > 254 or not re.fullmatch(
        r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized
    ):
        raise ValueError("Enter a valid email address.")
    if not recipient_id or len(recipient_id) > 200:
        raise ValueError("A valid recipient ID is required.")
    if not display_name or len(display_name) > 120:
        raise ValueError("A display name of 1–120 characters is required.")
    if source not in {"SANDBOX", "INSTITUTION"}:
        raise ValueError("Unsupported recipient source.")

    with get_database_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO recipient_email_aliases
                (normalized_email, recipient_id, display_name, phone_number,
                 email_ownership_status, phone_ownership_status, source)
            VALUES (%s, %s, %s, %s, 'UNVERIFIED', 'UNVERIFIED', %s)
            ON CONFLICT (normalized_email) DO NOTHING
            RETURNING normalized_email, recipient_id, display_name,
                      phone_number, email_ownership_status,
                      phone_ownership_status, source
            """,
            (normalized, recipient_id, display_name, phone_number, source),
        ).fetchone()

    if row is None:
        raise ValueError("That email address is already registered.")

    return {
        "email": row["normalized_email"],
        "recipient_id": row["recipient_id"],
        "display_name": row["display_name"],
        "masked_phone": (
            row["phone_number"][:3]
            + "*" * max(0, len(row["phone_number"]) - 5)
            + row["phone_number"][-2:]
            if len(row["phone_number"]) > 5
            else "*" * len(row["phone_number"])
        ),
        "phone_ownership_status": row["phone_ownership_status"],
        "email_ownership_status": row["email_ownership_status"],
        "contact_verification_status": "UNVERIFIED",
        "source": row["source"],
    }



def get_recipient_by_email(email):
    """Return recipient ownership statuses without exposing the stored phone."""
    normalized = email.strip().casefold()

    with get_database_connection() as connection:
        row = connection.execute(
            """
            SELECT normalized_email, recipient_id, display_name,
                   email_ownership_status, phone_ownership_status, source
            FROM recipient_email_aliases
            WHERE normalized_email = %s
            """,
            (normalized,),
        ).fetchone()

    if row is None:
        return None

    fully_verified = (
        row["email_ownership_status"] == "VERIFIED"
        and row["phone_ownership_status"] == "VERIFIED"
    )

    return {
        "email": row["normalized_email"],
        "recipient_id": row["recipient_id"],
        "display_name": row["display_name"],
        "email_ownership_status": row["email_ownership_status"],
        "phone_ownership_status": row["phone_ownership_status"],
        "contact_verification_status": (
            "FULLY_VERIFIED" if fully_verified else "UNVERIFIED"
        ),
        "identity_verified": False,
        "payment_authorized": False,
        "funds_moved": False,
        "source": row["source"],
    }


def _hash_recipient_otp(code):
    """Hash a recipient OTP with a dedicated server-side secret."""
    import hashlib
    import hmac

    pepper = os.environ.get("TRUSTNG_OTP_PEPPER", "")
    if len(pepper) < 32:
        raise RuntimeError(
            "TRUSTNG_OTP_PEPPER must be configured with at least 32 characters."
        )

    return hmac.new(
        pepper.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def start_recipient_email_verification(email):
    """Create two different, independently keyed contact verification codes."""
    import secrets

    normalized = email.strip().casefold()
    email_code = f"{secrets.randbelow(1_000_000):06d}"
    phone_code = f"{secrets.randbelow(1_000_000):06d}"

    while phone_code == email_code:
        phone_code = f"{secrets.randbelow(1_000_000):06d}"

    email_hash = _hash_recipient_otp(email_code)
    phone_hash = _hash_recipient_otp(phone_code)

    with get_database_connection() as connection:
        recipient = connection.execute(
            """
            SELECT normalized_email, phone_number,
                   email_ownership_status, phone_ownership_status
            FROM recipient_email_aliases
            WHERE normalized_email = %s
            FOR UPDATE
            """,
            (normalized,),
        ).fetchone()

        if recipient is None:
            raise ValueError("Recipient email is not registered.")
        if not recipient["phone_number"]:
            raise ValueError("Recipient has no assigned phone number.")
        if (
            recipient["email_ownership_status"] == "VERIFIED"
            and recipient["phone_ownership_status"] == "VERIFIED"
        ):
            raise ValueError("Recipient contact details are already fully verified.")

        challenge = connection.execute(
            """
            INSERT INTO recipient_email_verification_challenges
                (normalized_email, code_hash, phone_code_hash,
                 expires_at, attempts, phone_attempts, created_at, consumed_at)
            VALUES (
                %s, %s, %s, NOW() + INTERVAL '10 minutes',
                0, 0, NOW(), NULL
            )
            ON CONFLICT (normalized_email) DO UPDATE
            SET code_hash = EXCLUDED.code_hash,
                phone_code_hash = EXCLUDED.phone_code_hash,
                expires_at = EXCLUDED.expires_at,
                attempts = 0,
                phone_attempts = 0,
                created_at = NOW(),
                consumed_at = NULL
            WHERE recipient_email_verification_challenges.created_at
                      < NOW() - INTERVAL '60 seconds'
              AND (
                    recipient_email_verification_challenges.consumed_at IS NOT NULL
                    OR recipient_email_verification_challenges.attempts >= 5
                    OR recipient_email_verification_challenges.phone_attempts >= 5
                    OR recipient_email_verification_challenges.expires_at <= NOW()
                  )
            RETURNING normalized_email, created_at
            """,
            (normalized, email_hash, phone_hash),
        ).fetchone()

        if challenge is None:
            raise ValueError(
                "A verification challenge is already active. "
                "Wait for it to expire or reach its attempt limit before requesting new codes."
            )

    phone = recipient["phone_number"]
    masked_phone = (
        phone[:3] + "*" * max(0, len(phone) - 5) + phone[-2:]
        if len(phone) > 5 else "*" * len(phone)
    )

    created_at = challenge["created_at"]
    idempotency_key = hashlib.sha256(f"{normalized}:{created_at.isoformat()}".encode("utf-8")).hexdigest()

    return {
        "email": normalized,
        "email_verification_code": email_code,
        "phone_verification_code": phone_code,
        "phone_number": phone,
        "idempotency_key": idempotency_key,
        "masked_phone": masked_phone,
        "expires_in_seconds": 600,
        "email_delivery_mode": "SMTP_OR_SANDBOX",
        "phone_delivery_mode": "SANDBOX_ONLY",
    }


def invalidate_recipient_email_verification(email):
    """Consume an active challenge when its email delivery fails."""
    normalized = email.strip().casefold()

    with get_database_connection() as connection:
        connection.execute(
            """
            UPDATE recipient_email_verification_challenges
            SET consumed_at = NOW()
            WHERE normalized_email = %s
              AND consumed_at IS NULL
            """,
            (normalized,),
        )


def confirm_recipient_email_verification(email, email_code, phone_code):
    """Verify both independent OTPs before confirming contact ownership."""
    from datetime import datetime, timezone

    normalized = email.strip().casefold()
    supplied_email_hash = _hash_recipient_otp(email_code.strip())
    supplied_phone_hash = _hash_recipient_otp(phone_code.strip())

    error = None
    result = None

    with get_database_connection() as connection:
        challenge = connection.execute(
            """
            SELECT code_hash, phone_code_hash, expires_at,
                   attempts, phone_attempts, consumed_at
            FROM recipient_email_verification_challenges
            WHERE normalized_email = %s
            FOR UPDATE
            """,
            (normalized,),
        ).fetchone()

        if challenge is None:
            error = "No verification challenge exists. Request new codes."
        elif challenge["consumed_at"] is not None:
            error = "These verification codes have already been used."
        elif challenge["expires_at"] <= datetime.now(timezone.utc):
            connection.execute(
                """
                UPDATE recipient_email_verification_challenges
                SET consumed_at = NOW()
                WHERE normalized_email = %s
                """,
                (normalized,),
            )
            error = "Verification codes have expired. Request new codes."
        elif challenge["attempts"] >= 5 or challenge["phone_attempts"] >= 5:
            error = "Too many attempts. Request new codes after the challenge limit."
        else:
            email_valid = hmac.compare_digest(
                challenge["code_hash"], supplied_email_hash
            )
            phone_valid = (
                challenge["phone_code_hash"] is not None
                and hmac.compare_digest(
                    challenge["phone_code_hash"], supplied_phone_hash
                )
            )

            if not email_valid or not phone_valid:
                connection.execute(
                    """
                    UPDATE recipient_email_verification_challenges
                    SET attempts = attempts + %s,
                        phone_attempts = phone_attempts + %s
                    WHERE normalized_email = %s
                    """,
                    (
                        0 if email_valid else 1,
                        0 if phone_valid else 1,
                        normalized,
                    ),
                )
                if not email_valid and not phone_valid:
                    error = "Both verification codes are incorrect."
                elif not email_valid:
                    error = "Email verification code is incorrect."
                else:
                    error = "Phone verification code is incorrect."
            else:
                updated = connection.execute(
                    """
                    UPDATE recipient_email_aliases
                    SET email_ownership_status = 'VERIFIED',
                        phone_ownership_status = 'VERIFIED',
                        updated_at = NOW()
                    WHERE normalized_email = %s
                    """,
                    (normalized,),
                )

                if updated.rowcount != 1:
                    error = "Recipient registration is no longer available."
                else:
                    connection.execute(
                        """
                        UPDATE recipient_email_verification_challenges
                        SET consumed_at = NOW()
                        WHERE normalized_email = %s
                        """,
                        (normalized,),
                    )
                    result = {
                        "email": normalized,
                        "email_ownership_status": "VERIFIED",
                        "phone_ownership_status": "VERIFIED",
                        "contact_verification_status": "FULLY_VERIFIED",
                        "identity_verified": False,
                        "payment_authorized": False,
                        "funds_moved": False,
                    }

    if error:
        raise ValueError(error)
    if result is None:
        raise ValueError("Contact verification could not be completed.")
    return result



def consume_partnership_rate_limit(identifier_hash):
    """
    Atomically enforce partnership-form sliding-window limits.

    Allows at most 2 submissions in 5 minutes and 5 submissions in 1 hour.
    The caller must supply a SHA-256 HMAC hex digest, never a raw IP address.

    Returns True when accepted and False when either limit is reached.
    Database errors propagate so the API can fail closed.
    """
    if (
        not isinstance(identifier_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", identifier_hash) is None
    ):
        raise ValueError("A valid SHA-256 HMAC identifier is required.")

    with get_database_connection() as connection:
        # Serialize requests for this identifier across application instances.
        connection.execute(
            """
            SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))
            """,
            (identifier_hash,),
        )

        counts = connection.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE created_at >=
                        clock_timestamp() - INTERVAL '5 minutes'
                ) AS short_window_count,
                COUNT(*) FILTER (
                    WHERE created_at >=
                        clock_timestamp() - INTERVAL '1 hour'
                ) AS hourly_window_count
            FROM partnership_rate_limit_events
            WHERE identifier_hash = %s
            """,
            (identifier_hash,),
        ).fetchone()

        if (
            counts["short_window_count"] >= 2
            or counts["hourly_window_count"] >= 5
        ):
            return False

        connection.execute(
            """
            INSERT INTO partnership_rate_limit_events (
                identifier_hash, created_at
            )
            VALUES (%s, clock_timestamp())
            """,
            (identifier_hash,),
        )

        # Bound cleanup work so one submission cannot trigger an unlimited delete.
        connection.execute(
            """
            DELETE FROM partnership_rate_limit_events
            WHERE event_id IN (
                SELECT event_id
                FROM partnership_rate_limit_events
                WHERE created_at < clock_timestamp() - INTERVAL '1 hour'
                ORDER BY created_at
                LIMIT 100
            )
            """
        )

    return True


def create_partnership_enquiry(
    submission_id,
    reference,
    full_name,
    business_email,
    organisation,
    position,
    phone,
    country,
    partnership_type,
    other_interest,
    purpose,
):
    """Save a DIJUANG partnership enquiry without exposing it publicly."""
    with get_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO partnership_enquiries (
                submission_id, reference, full_name, business_email,
                organisation, position, phone, country,
                partnership_type, other_interest, purpose
            )
            VALUES (
                %(submission_id)s, %(reference)s, %(full_name)s,
                %(business_email)s, %(organisation)s, %(position)s,
                %(phone)s, %(country)s, %(partnership_type)s,
                %(other_interest)s, %(purpose)s
            )
            """,
            {
                "submission_id": submission_id,
                "reference": reference,
                "full_name": full_name,
                "business_email": business_email,
                "organisation": organisation,
                "position": position,
                "phone": phone,
                "country": country,
                "partnership_type": partnership_type,
                "other_interest": other_interest,
                "purpose": purpose,
            },
        )


def list_recent_partnership_enquiries(limit=50):
    """Return recent DIJUANG partnership enquiries for authenticated staff."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")

    with get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT reference, full_name, business_email, organisation,
                   position, phone, country, partnership_type,
                   other_interest, purpose, created_at
            FROM partnership_enquiries
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    return [
        {
            **{key: row[key] for key in (
                "reference", "full_name", "business_email", "organisation",
                "position", "phone", "country", "partnership_type",
                "other_interest", "purpose",
            )},
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
