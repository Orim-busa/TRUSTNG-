
import os
from datetime import datetime, timezone

import database


# Local duplicate protection when PostgreSQL is not configured.
EXECUTED_TRANSACTIONS = set()


def execute_transaction(transaction, execution_check):
    """
    Simulate transaction execution only after the Execution Gate
    approves it.

    PostgreSQL provides persistent duplicate protection when
    DATABASE_URL is configured.

    This function does not move real funds.
    """

    # 1. Require an execution check.
    if not execution_check:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Execution check is missing",
        }

    # 2. Require explicit approval from the Execution Gate.
    if execution_check.get("execution_allowed") is not True:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Transaction did not pass the Execution Gate",
        }

    # 3. Require a transaction ID.
    transaction_id = transaction.transaction_id

    if not transaction_id:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Transaction ID is missing",
        }

    # 4. Claim the transaction ID to prevent duplicate execution.
    database_enabled = bool(os.environ.get("DATABASE_URL"))

    if database_enabled:
        try:
            claimed = database.claim_transaction_execution(
                transaction_id
            )
        except Exception:
            return {
                "executed": False,
                "status": "BLOCKED",
                "reason": (
                    "Persistent duplicate protection is unavailable"
                ),
            }

        if not claimed:
            return {
                "executed": False,
                "status": "DUPLICATE",
                "reason": "Transaction has already been claimed",
            }

    else:
        # Local testing mode without PostgreSQL.
        if transaction_id in EXECUTED_TRANSACTIONS:
            return {
                "executed": False,
                "status": "DUPLICATE",
                "reason": "Transaction has already been executed",
            }

        EXECUTED_TRANSACTIONS.add(transaction_id)

    # 5. Prepare the simulated execution result.
    result = {
        "executed": True,
        "status": "EXECUTED",
        "transaction_id": transaction_id,
        "sender": transaction.sender,
        "receiver": transaction.receiver,
        "asset": transaction.asset,
        "amount": transaction.amount,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    # 6. Confirm completion in PostgreSQL before reporting success.
    if database_enabled:
        try:
            completed = database.complete_transaction_execution(
                transaction_id
            )
        except Exception:
            return {
                "executed": False,
                "status": "BLOCKED",
                "reason": "Transaction could not be completed because execution status could not be confirmed",
            }

        if not completed:
            return {
                "executed": False,
                "status": "BLOCKED",
                "reason": "Transaction could not be completed because execution status could not be confirmed",
            }

    # 7. Return success only after completion is confirmed.
    return result
