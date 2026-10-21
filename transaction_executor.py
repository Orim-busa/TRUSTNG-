
import os
import threading
from datetime import datetime, timezone

import database


# Local duplicate protection when PostgreSQL is not configured.
EXECUTED_TRANSACTIONS = set()
EXECUTED_TRANSACTIONS_LOCK = threading.Lock()


def execute_transaction(transaction, execution_check):
    """
    Simulate transaction execution only after the Execution Gate
    approves it.

    PostgreSQL provides persistent duplicate protection when
    DATABASE_URL is configured.

    This function does not move real funds.
    """

    # 1. Validate the gate type before inspecting its contents.
    # Exact built-in dict validation prevents unexpected subclasses or
    # custom objects from raising errors during truthiness or .get().
    if execution_check is None:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Execution check is missing",
        }

    if type(execution_check) is not dict:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Execution check is invalid",
        }

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

    # 3. Validate and capture transaction data before claiming its ID.
    try:
        transaction_id = transaction.transaction_id
        if not transaction_id:
            return {
                "executed": False,
                "status": "BLOCKED",
                "reason": "Transaction ID is missing",
            }

        sender = transaction.sender
        receiver = transaction.receiver
        asset = transaction.asset
        amount = transaction.amount

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
            "sender": sender,
            "receiver": receiver,
            "asset": asset,
            "amount": amount,
            "simulated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Transaction data could not be validated",
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
        # Keep checking and claiming atomic across threads.
        with EXECUTED_TRANSACTIONS_LOCK:
            if transaction_id in EXECUTED_TRANSACTIONS:
                return {
                    "executed": False,
                    "status": "DUPLICATE",
                    "reason": "Transaction has already been executed",
                }

            EXECUTED_TRANSACTIONS.add(transaction_id)

    # 5. Record simulation status without marking a payment executed.
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
