from datetime import datetime


# Stores completed evaluations by transaction ID.
#
# IMPORTANT:
# This is currently an in-memory store.
# It will reset whenever the TrustNG process restarts.
#
# A production version should use a durable,
# strongly protected datastore.
PROCESSED_TRANSACTIONS = {}


def create_transaction_fingerprint(transaction):
    """
    Create a fingerprint from the important transaction fields.

    The fingerprint allows TrustNG to detect when the same
    transaction ID is reused with different transaction data.
    """

    return (
        transaction.transaction_id,
        transaction.sender,
        transaction.receiver,
        transaction.asset.upper(),
        transaction.amount,
        transaction.channel.upper(),
        transaction.country.upper(),
        transaction.device_id
    )


def check_transaction(transaction_id):
    """
    Check whether a transaction has already been processed.

    Returns:
        None if the transaction is new.

        The previous evaluation record if the transaction
        has already been processed.
    """

    if not transaction_id:
        return None

    return PROCESSED_TRANSACTIONS.get(
        transaction_id
    )


def check_transaction_integrity(transaction):
    """
    Check whether a transaction ID has already been processed.

    Returns:

        None
        if the transaction is new.

        {
            "status": "REPLAY",
            ...
        }
        if the exact same transaction was already processed.

        {
            "status": "ID_REUSE",
            ...
        }
        if the transaction ID is being reused with
        different transaction data.

        {
            "status": "INVALID",
            ...
        }
        if the transaction ID is missing.
    """

    transaction_id = transaction.transaction_id

    # Transaction ID must exist.
    if not transaction_id:
        return {
            "status": "INVALID",
            "reason": "Transaction ID is missing"
        }

    existing = PROCESSED_TRANSACTIONS.get(
        transaction_id
    )

    # New transaction.
    if existing is None:
        return None

    stored_fingerprint = existing.get(
        "fingerprint"
    )

    current_fingerprint = create_transaction_fingerprint(
        transaction
    )

    # Same ID + same transaction data.
    if stored_fingerprint == current_fingerprint:
        return {
            "status": "REPLAY",
            "reason": (
                "Transaction has already been processed"
            ),
            "transaction_id": transaction_id
        }

    # Same ID + different transaction data.
    return {
        "status": "ID_REUSE",
        "reason": (
            "Transaction ID has already been used "
            "with different transaction data"
        ),
        "transaction_id": transaction_id
    }


def store_transaction(transaction, result):
    """
    Store the final TrustNG evaluation result together
    with the exact transaction fingerprint.
    """

    transaction_id = transaction.transaction_id

    if not transaction_id:
        return

    PROCESSED_TRANSACTIONS[
        transaction_id
    ] = {
        "stored_at": datetime.utcnow().isoformat(),

        "fingerprint": create_transaction_fingerprint(
            transaction
        ),

        "result": result
    }


def clear_transaction(transaction_id):
    """
    Remove a transaction from the idempotency store.

    This is mainly useful for controlled testing
    and administration.
    """

    if transaction_id in PROCESSED_TRANSACTIONS:
        del PROCESSED_TRANSACTIONS[
            transaction_id
        ]


def get_processed_transaction_count():
    """
    Return the number of transactions currently
    stored in the idempotency store.
    """

    return len(
        PROCESSED_TRANSACTIONS
    )