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

    # A success status cannot override an explicit or missing uncertainty
    # signal. Fail closed and require reconciliation instead.
    if (
        status == "SIMULATED_SUCCESS"
        and result.get("outcome_uncertain") is not False
    ):
        try:
            database.update_provider_operation_status(
                prepared["idempotency_key"],
                "RECONCILIATION_REQUIRED",
                {
                    "reason": (
                        "The sandbox reported success without explicitly "
                        "confirming a certain outcome."
                    ),
                    "result": result,
                },
            )
        except Exception:
            pass

        return _uncertain(
            "The sandbox result reports success but does not confirm "
            "that the outcome is certain. Do not retry blindly."
        )

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
        # durable state and validate its identity before accepting a replay.
        try:
            current = database.get_provider_operation(
                prepared["idempotency_key"]
            )
        except Exception:
            current = None

        expected_operation = {
            "idempotency_key": prepared["idempotency_key"],
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": prepared["fingerprint"],
        }
        expected_result = {
            "provider": prepared["provider"],
            "sandbox": True,
            "transaction_id": prepared["request"]["transaction_id"],
            "idempotency_key": prepared["idempotency_key"],
            "fingerprint": prepared["fingerprint"],
        }

        current_result = (
            current.get("result") if isinstance(current, dict) else None
        )
        current_status = (
            current.get("status") if isinstance(current, dict) else None
        )

        valid_final_record = (
            isinstance(current, dict)
            and current_status in {"SUCCEEDED", "FAILED"}
            and all(
                current.get(field) == value
                for field, value in expected_operation.items()
            )
            and isinstance(current_result, dict)
            and all(
                current_result.get(field) == value
                for field, value in expected_result.items()
            )
            and (
                (
                    current_status == "SUCCEEDED"
                    and current_result.get("status") == "SIMULATED_SUCCESS"
                    and current_result.get("outcome_uncertain") is False
                )
                or (
                    current_status == "FAILED"
                    and current_result.get("status") == "FAILED"
                )
            )
        )

        if valid_final_record:
            return {
                "decision": "REPLAY",
                "status": current_status,
                "sandbox": True,
                "outcome_uncertain": False,
                "operation": current,
                "result": current_result,
            }

        return _uncertain(
            "The database did not confirm a matching final operation "
            "and result. Do not retry blindly.",
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
        # A final database status is not sufficient by itself: verify that
        # the stored operation and result belong to this exact sandbox request.
        expected_operation = {
            "idempotency_key": prepared["idempotency_key"],
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": prepared["fingerprint"],
        }
        expected_result = {
            "provider": prepared["provider"],
            "sandbox": True,
            "transaction_id": prepared["request"]["transaction_id"],
            "idempotency_key": prepared["idempotency_key"],
            "fingerprint": prepared["fingerprint"],
        }

        result = operation.get("result") if isinstance(operation, dict) else None
        operation_status = (
            operation.get("status") if isinstance(operation, dict) else None
        )

        if (
            not isinstance(operation, dict)
            or operation_status not in {"SUCCEEDED", "FAILED"}
            or any(
                operation.get(field) != value
                for field, value in expected_operation.items()
            )
            or not isinstance(result, dict)
            or any(
                result.get(field) != value
                for field, value in expected_result.items()
            )
            or (
                operation_status == "SUCCEEDED"
                and result.get("status") != "SIMULATED_SUCCESS"
            )
            or (
                operation_status == "SUCCEEDED"
                and result.get("outcome_uncertain") is not False
            )
            or (
                operation_status == "FAILED"
                and result.get("status") != "FAILED"
            )
        ):
            return _uncertain(
                "The stored final operation or result failed replay "
                "identity/status validation. Do not retry blindly.",
                operation,
            )

        return {
            "decision": "REPLAY",
            "status": operation_status,
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
        # Validate the reservation before trusting any recovered provider
        # result. A malformed or mismatched database response must fail closed.
        expected_operation = {
            "idempotency_key": prepared["idempotency_key"],
            "provider": prepared["provider"],
            "transaction_id": prepared["request"]["transaction_id"],
            "request_fingerprint": prepared["fingerprint"],
        }
        if (
            not isinstance(operation, dict)
            or operation.get("status") != "PENDING"
            or any(
                operation.get(field) != value
                for field, value in expected_operation.items()
            )
        ):
            return _uncertain(
                "The pending reservation failed identity/status validation. "
                "No provider inspection or resubmission was attempted.",
                operation,
            )

        # Never submit again for a pre-existing PENDING reservation.
        try:
            result = adapter.inspect(transaction)
        except Exception:
            result = {"status": "NOT_FOUND"}

        # A provider adapter is not guaranteed to return a valid dictionary.
        # Treat malformed recovery data as unavailable and fail closed.
        if not isinstance(result, dict):
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

    if not isinstance(result, dict):
        try:
            database.update_provider_operation_status(
                prepared["idempotency_key"],
                "RECONCILIATION_REQUIRED",
                {
                    "reason": (
                        "Sandbox adapter returned an invalid result type."
                    )
                },
            )
        except Exception:
            pass

        return _uncertain(
            "Sandbox adapter returned an invalid result. "
            "Do not retry this operation automatically."
        )

    if result.get("status") == "IDEMPOTENCY_CONFLICT":
        return {
            "decision": "CONFLICT",
            "status": "IDEMPOTENCY_CONFLICT",
            "sandbox": True,
            "outcome_uncertain": False,
        }

    return _persist_sandbox_result(prepared, result)
