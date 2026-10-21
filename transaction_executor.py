
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

    # 1. Require a valid execution check.
    if not execution_check:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Execution check is missing",
        }

    if not isinstance(execution_check, dict):
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Execution check is invalid",
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
        "executed": False,
        "status": "SIMULATED_EXECUTION",
        "simulation": True,
        "funds_moved": False,
        "message": (
            "Simulation only. No real payment provider was called "
            "and no funds were moved."
        ),
        "transaction_id": transaction_id,
        "sender": transaction.sender,
        "receiver": transaction.receiver,
        "asset": transaction.asset,
        "amount": transaction.amount,
        "simulated_at": datetime.now(timezone.utc).isoformat(),
    }

    # 6. Record simulation status without marking a payment executed.
    if database_enabled:
        try:
            recorded = database.mark_transaction_execution_simulated(
                transaction_id
            )
        except Exception:
            recorded = False

        if not recorded:
            return {
                "executed": False,
                "status": "BLOCKED",
                "simulation": True,
                "funds_moved": False,
                "reason": (
                    "Simulation status could not be confirmed. "
                    "The transaction remains claimed and must not be "
                    "retried automatically."
                ),
            }

    # 7. Return the simulation result only after its status is recorded.
    return result
