
import os
import threading
from datetime import datetime, timezone

import database


PROCESSED_TRANSACTIONS = {}
TRANSACTION_LOCK = threading.RLock()


def database_mode_enabled():
    return bool(os.environ.get("DATABASE_URL"))


def create_transaction_fingerprint(transaction):
    return (
        transaction.transaction_id,
        transaction.sender,
        transaction.receiver,
        transaction.asset.upper(),
        transaction.amount,
        transaction.channel.upper(),
        transaction.country.upper(),
        transaction.device_id,
    )


def check_transaction(transaction_id):
    if not transaction_id:
        return None

    if database_mode_enabled():
        return database.get_processed_transaction(transaction_id)

    with TRANSACTION_LOCK:
        return PROCESSED_TRANSACTIONS.get(transaction_id)


def check_transaction_integrity(transaction):
    transaction_id = transaction.transaction_id

    if not transaction_id:
        return {
            "status": "INVALID",
            "reason": "Transaction ID is missing",
        }

    existing = check_transaction(transaction_id)

    if existing is None:
        return None

    current_fingerprint = create_transaction_fingerprint(transaction)

    if existing.get("fingerprint") == current_fingerprint:
        return {
            "status": "REPLAY",
            "reason": "Transaction ID has already been reserved or processed",
            "transaction_id": transaction_id,
        }

    return {
        "status": "ID_REUSE",
        "reason": (
            "Transaction ID has already been used "
            "with different transaction data"
        ),
        "transaction_id": transaction_id,
    }


def reserve_transaction(transaction):
    """Atomically reserve a transaction ID before evaluation."""

    transaction_id = transaction.transaction_id

    if not transaction_id:
        return {
            "status": "INVALID",
            "reason": "Transaction ID is missing",
        }

    fingerprint = create_transaction_fingerprint(transaction)
    processing_result = {
        "status": "PROCESSING",
        "message": "Transaction evaluation is in progress",
        "transaction_id": transaction_id,
    }

    if database_mode_enabled():
        saved = database.save_processed_transaction(
            transaction_id,
            fingerprint,
            processing_result,
        )

        if saved:
            return None

        return check_transaction_integrity(transaction)

    with TRANSACTION_LOCK:
        existing = PROCESSED_TRANSACTIONS.get(transaction_id)

        if existing is not None:
            if existing.get("fingerprint") == fingerprint:
                return {
                    "status": "REPLAY",
                    "reason": "Transaction ID has already been reserved or processed",
                    "transaction_id": transaction_id,
                }

            return {
                "status": "ID_REUSE",
                "reason": (
                    "Transaction ID has already been used "
                    "with different transaction data"
                ),
                "transaction_id": transaction_id,
            }

        PROCESSED_TRANSACTIONS[transaction_id] = {
            "stored_at": datetime.now(timezone.utc).isoformat(),
            "fingerprint": fingerprint,
            "result": processing_result,
        }

    return None


def store_transaction(transaction, result):
    """Save the final result for a transaction."""

    transaction_id = transaction.transaction_id

    if not transaction_id:
        raise ValueError("Transaction ID is required.")

    fingerprint = create_transaction_fingerprint(transaction)

    if database_mode_enabled():
        existing = database.get_processed_transaction(transaction_id)

        if existing is None:
            saved = database.save_processed_transaction(
                transaction_id,
                fingerprint,
                result,
            )

            if not saved:
                raise RuntimeError(
                    "Transaction ID already exists; result was not overwritten."
                )

            return

        if existing.get("fingerprint") != fingerprint:
            raise RuntimeError(
                "Transaction fingerprint mismatch; result not updated."
            )

        existing_result = existing.get("result", {})

        if existing_result.get("status") != "PROCESSING":
            raise RuntimeError(
                "Transaction already has a final result; it cannot be overwritten."
            )

        updated = database.update_processed_transaction_result(
            transaction_id,
            result,
        )

        if not updated:
            raise RuntimeError(
                "Could not update the reserved transaction result."
            )

        return

    with TRANSACTION_LOCK:
        existing = PROCESSED_TRANSACTIONS.get(transaction_id)

        if existing is None:
            PROCESSED_TRANSACTIONS[transaction_id] = {
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "fingerprint": fingerprint,
                "result": result,
            }
            return

        if existing.get("fingerprint") != fingerprint:
            raise RuntimeError(
                "Transaction fingerprint mismatch; result not updated."
            )

        if existing.get("result", {}).get("status") != "PROCESSING":
            raise RuntimeError(
                "Transaction already has a final result; it cannot be overwritten."
            )

        existing["result"] = result


def clear_transaction(transaction_id):
    if database_mode_enabled():
        raise RuntimeError(
            "Clearing transactions is disabled in database mode."
        )

    with TRANSACTION_LOCK:
        PROCESSED_TRANSACTIONS.pop(transaction_id, None)


def get_processed_transaction_count():
    if database_mode_enabled():
        return database.get_processed_transaction_count()

    with TRANSACTION_LOCK:
        return len(PROCESSED_TRANSACTIONS)


def calculate_trust(transaction, beneficiary_profile):
    trust_factors = []
    trust_score = 0

    verification_level = beneficiary_profile.get(
        "verification_level",
        "UNKNOWN"
    )
