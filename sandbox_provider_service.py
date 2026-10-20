"""Database-backed orchestration for the in-memory sandbox provider.

This module is sandbox-only. It never contacts a real payment provider.
Database state is authoritative for replay and recovery decisions.
"""

import database
from provider_adapter import SandboxPaymentAdapter


def _uncertain(reason, operation=None):
    return {
        "decision": "RECONCILE",
        "status": "RECONCILIATION_REQUIRED",
        "sandbox": True,
        "outcome_uncertain": True,
        "reason": reason,
        "operation": operation,
    }


def _persist_sandbox_result(prepared, result):
    """Validate and persist a simulated outcome without weakening transitions."""
    expected = {
        "provider": prepared["provider"],
        "sandbox": True,
        "transaction_id": prepared["request"]["transaction_id"],
        "idempotency_key": prepared["idempotency_key"],
        "fingerprint": prepared["fingerprint"],
    }

    if not isinstance(result, dict) or any(
        result.get(field) != value for field, value in expected.items()
    ):
        try:
            database.update_provider_operation_status(
                prepared["idempotency_key"],
                "RECONCILIATION_REQUIRED",
                {
                    "reason": (
                        "Sandbox adapter returned a result that did not "
                        "match the reserved operation."
                    )
                },
            )
        except Exception:
            pass

        return _uncertain(
            "The sandbox result failed operation-identity validation. "
            "Do not retry blindly."
        )

    status = result.get("status")

    if status == "SIMULATED_SUCCESS":
        target_status = "SUCCEEDED"
        authoritative = True
    elif status == "RECONCILIATION_REQUIRED":
        target_status = "RECONCILIATION_REQUIRED"
        authoritative = False
    else:
        return {
            "decision": "CONFLICT",
            "status": status or "INVALID_RESULT",
            "sandbox": True,
            "outcome_uncertain": bool(result.get("outcome_uncertain", True)),
            "result": result,
        }

    try:
        updated = database.update_provider_operation_status(
            prepared["idempotency_key"],
            target_status,
            result,
            authoritative=authoritative,
        )
    except Exception:
        return _uncertain(
            "The sandbox result could not be durably recorded. "
            "Do not retry blindly."
        )

    if not updated:
        # A concurrent worker may have completed the operation. Inspect
        # durable state instead of overwriting it or claiming success.
        try:
            current = database.get_provider_operation(
                prepared["idempotency_key"]
            )
        except Exception:
            current = None

        if current and current.get("status") in {"SUCCEEDED", "FAILED"}:
            return {
                "decision": "REPLAY",
                "status": current["status"],
                "sandbox": True,
                "outcome_uncertain": False,
                "operation": current,
                "result": current.get("result"),
            }

        return _uncertain(
            "The database did not confirm the expected status transition.",
            current,
        )

    if target_status == "RECONCILIATION_REQUIRED":
        return _uncertain(
            result.get("message", "Outcome requires reconciliation."),
            {"status": target_status, "result": result},
        )

    # Verify the durable record before reporting completion.
    try:
        current = database.get_provider_operation(
            prepared["idempotency_key"]
        )
    except Exception:
        return _uncertain(
            "The saved sandbox result could not be read back and verified. "
            "Do not retry blindly."
        )

    expected_record = {
        "idempotency_key": prepared["idempotency_key"],
        "provider": prepared["provider"],
        "transaction_id": prepared["request"]["transaction_id"],
        "request_fingerprint": prepared["fingerprint"],
        "status": "SUCCEEDED",
        "result": result,
    }

    if not isinstance(current, dict) or any(
        current.get(field) != value
        for field, value in expected_record.items()
    ):
        return _uncertain(
            "The saved sandbox result did not match the expected operation. "
            "Do not retry blindly.",
            current,
        )

    return {
        "decision": "COMPLETED",
        "status": "SIMULATED_SUCCESS",
        "sandbox": True,
        "outcome_uncertain": False,
        "operation_status": "SUCCEEDED",
        "result": result,
    }


def run_sandbox_provider_operation(
    transaction,
    *,
    adapter=None,
    simulate_uncertain_outcome=False,
):
    """Reserve, simulate, persist, or safely recover a sandbox operation."""
    adapter = adapter if adapter is not None else SandboxPaymentAdapter()

    # Prepare and validate before touching the database.
    prepared = adapter.prepare(transaction)

    try:
        reservation = database.reserve_or_inspect_provider_operation(
            prepared["idempotency_key"],
            prepared["provider"],
            prepared["request"]["transaction_id"],
            prepared["fingerprint"],
        )
    except Exception:
        return {
            "decision": "DATABASE_UNAVAILABLE",
            "status": "BLOCKED",
            "sandbox": True,
            "outcome_uncertain": True,
            "reason": "The operation could not be reserved or inspected.",
        }

    decision = reservation.get("decision")
    operation = reservation.get("operation")

    if decision == "CONFLICT":
        return {
            "decision": "CONFLICT",
            "status": "IDEMPOTENCY_CONFLICT",
            "sandbox": True,
            "outcome_uncertain": False,
        }

    if decision == "NOT_FOUND":
        return {
            "decision": "NOT_FOUND",
            "status": "BLOCKED",
            "sandbox": True,
            "outcome_uncertain": True,
        }

    if decision == "REPLAY":
        result = (operation or {}).get("result")
        return {
            "decision": "REPLAY",
            "status": (operation or {}).get("status", "CONFLICT"),
            "sandbox": True,
            "outcome_uncertain": False,
            "operation": operation,
            "result": result,
        }

    if decision == "RECONCILE":
        return _uncertain(
            "This operation already requires reconciliation.",
            operation,
        )

    if decision == "CHECK_PROVIDER_STATUS":
        # Never submit again for a pre-existing PENDING reservation.
        try:
            result = adapter.inspect(transaction)
        except Exception:
            result = {"status": "NOT_FOUND"}

        if result.get("status") == "IDEMPOTENCY_CONFLICT":
            return {
                "decision": "CONFLICT",
                "status": "IDEMPOTENCY_CONFLICT",
                "sandbox": True,
                "outcome_uncertain": False,
            }

        if result.get("status") not in {
            "SIMULATED_SUCCESS",
            "RECONCILIATION_REQUIRED",
        }:
            try:
                database.update_provider_operation_status(
                    prepared["idempotency_key"],
                    "RECONCILIATION_REQUIRED",
                    {
                        "reason": (
                            "A pending operation has no recoverable "
                            "sandbox result."
                        )
                    },
                )
            except Exception:
                pass

            return _uncertain(
                "No recoverable sandbox result exists. "
                "No resubmission was attempted.",
                operation,
            )

        return _persist_sandbox_result(prepared, result)

    if decision != "RESERVED":
        return {
            "decision": "BLOCKED",
            "status": "UNKNOWN_RESERVATION_DECISION",
            "sandbox": True,
            "outcome_uncertain": True,
        }

    # Only a newly created reservation reaches submit().
    try:
        result = adapter.submit(
            transaction,
            simulate_uncertain_outcome=simulate_uncertain_outcome,
        )
    except Exception:
        try:
            database.update_provider_operation_status(
                prepared["idempotency_key"],
                "RECONCILIATION_REQUIRED",
                {"reason": "Sandbox submission raised an exception."},
            )
        except Exception:
            pass

        return _uncertain(
            "Sandbox submission could not be safely confirmed."
        )

    if result.get("status") == "IDEMPOTENCY_CONFLICT":
        return {
            "decision": "CONFLICT",
            "status": "IDEMPOTENCY_CONFLICT",
            "sandbox": True,
            "outcome_uncertain": False,
        }

    return _persist_sandbox_result(prepared, result)
