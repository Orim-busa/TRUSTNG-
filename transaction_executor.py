from datetime import datetime


# Transactions that have already been executed.
EXECUTED_TRANSACTIONS = set()


def execute_transaction(
    transaction,
    execution_check
):
    """
    Executes a transaction only after it has passed
    the Execution Gate.

    This is currently a simulated execution layer.
    It does not move real funds.
    """

    # 1. Execution Gate must approve the transaction
    if not execution_check:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Execution check is missing"
        }

    if execution_check.get("execution_allowed") is not True:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Transaction did not pass the Execution Gate"
        }

    # 2. Transaction must have an ID
    transaction_id = transaction.transaction_id

    if not transaction_id:
        return {
            "executed": False,
            "status": "BLOCKED",
            "reason": "Transaction ID is missing"
        }

    # 3. Prevent duplicate transaction execution
    if transaction_id in EXECUTED_TRANSACTIONS:
        return {
            "executed": False,
            "status": "DUPLICATE",
            "reason": "Transaction has already been executed"
        }

    # 4. Record the execution
    EXECUTED_TRANSACTIONS.add(transaction_id)

    return {
        "executed": True,
        "status": "EXECUTED",
        "transaction_id": transaction_id,
        "sender": transaction.sender,
        "receiver": transaction.receiver,
        "asset": transaction.asset,
        "amount": transaction.amount,
        "executed_at": datetime.utcnow().isoformat()
    }