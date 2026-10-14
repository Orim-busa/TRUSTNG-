import os
from datetime import datetime, timezone

import database


PROCESSED_TRANSACTIONS = {}


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

    stored_fingerprint = existing.get("fingerprint")
    current_fingerprint = create_transaction_fingerprint(transaction)

    if stored_fingerprint == current_fingerprint:
        return {
            "status": "REPLAY",
            "reason": "Transaction has already been processed",
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


def store_transaction(transaction, result):
    transaction_id = transaction.transaction_id

    if not transaction_id:
        return

    fingerprint = create_transaction_fingerprint(transaction)

    if database_mode_enabled():
        saved = database.save_processed_transaction(
            transaction_id,
            fingerprint,
            result,
        )

        if not saved:
            raise RuntimeError(
                "Transaction ID already exists in the database; "
                "the evaluation result was not overwritten."
            )
        return

    PROCESSED_TRANSACTIONS[transaction_id] = {
        "stored_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint,
        "result": result,
    }


def clear_transaction(transaction_id):
    if database_mode_enabled():
        raise RuntimeError(
            "Clearing transactions is disabled in database mode."
        )

    PROCESSED_TRANSACTIONS.pop(transaction_id, None)


def get_processed_transaction_count():
    if database_mode_enabled():
        return database.get_processed_transaction_count()

    return len(PROCESSED_TRANSACTIONS)


def calculate_trust(transaction, beneficiary_profile):
    trust_factors = []

    trust_score = 0

    # 1. Beneficiary identity
    verification_level = beneficiary_profile.get(
        "verification_level",
        "UNKNOWN"
    )