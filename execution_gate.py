from datetime import datetime, timedelta, timezone


AUTHORIZATION_EXPIRY_MINUTES = 5

USED_AUTHORIZATIONS = set()


def validate_execution(
    transaction,
    authorization,
    restriction=None
):
    """
    Final security gate before a transaction can be executed.

    The gate verifies:

    1. Authorization exists.
    2. Authorization belongs to this transaction.
    3. Sender matches.
    4. Receiver matches.
    5. Asset matches.
    6. Amount matches.
    7. Channel matches.
    8. Country matches.
    9. Device matches.
    10. Authorization status is valid.
    11. Authorization has not expired.
    12. Authorization has not already been used.
    13. No active restriction blocks execution.

    This layer does not move money.
    It only determines whether execution is permitted.
    """

    failures = []

    # ---------------------------------------------------------
    # 1. Authorization must exist
    # ---------------------------------------------------------

    if not authorization:
        return {
            "execution_allowed": False,
            "status": "BLOCKED",
            "reasons": [
                "Authorization record is missing"
            ]
        }

    # ---------------------------------------------------------
    # 2. Transaction identity binding
    # ---------------------------------------------------------

    if authorization.get("transaction_id") != transaction.transaction_id:
        failures.append(
            "Authorization does not belong to this transaction"
        )

    # ---------------------------------------------------------
    # 3. Sender binding
    # ---------------------------------------------------------

    if authorization.get("sender") != transaction.sender:
        failures.append(
            "Authorization sender does not match transaction sender"
        )

    # ---------------------------------------------------------
    # 4. Receiver binding
    # ---------------------------------------------------------

    if authorization.get("receiver") != transaction.receiver:
        failures.append(
            "Authorization receiver does not match transaction receiver"
        )

    # ---------------------------------------------------------
    # 5. Asset binding
    # ---------------------------------------------------------

    if (
        authorization.get("asset", "").upper()
        != transaction.asset.upper()
    ):
        failures.append(
            "Authorization asset does not match transaction asset"
        )

    # ---------------------------------------------------------
    # 6. Amount binding
    # ---------------------------------------------------------

    if authorization.get("amount") != transaction.amount:
        failures.append(
            "Authorization amount does not match transaction amount"
        )

    # ---------------------------------------------------------
    # 7. Channel binding
    # ---------------------------------------------------------

    if (
        authorization.get("channel", "").upper()
        != transaction.channel.upper()
    ):
        failures.append(
            "Authorization channel does not match transaction channel"
        )

    # ---------------------------------------------------------
    # 8. Country binding
    # ---------------------------------------------------------

    if (
        authorization.get("country", "").upper()
        != transaction.country.upper()
    ):
        failures.append(
            "Authorization country does not match transaction country"
        )

    # ---------------------------------------------------------
    # 9. Device binding
    # ---------------------------------------------------------

    if authorization.get("device_id") != transaction.device_id:
        failures.append(
            "Authorization device does not match transaction device"
        )

    # ---------------------------------------------------------
    # 10. Authorization status
    # ---------------------------------------------------------

    if authorization.get("status") != "AUTHORIZED":
        failures.append(
            "Transaction is not authorized for execution"
        )

    # ---------------------------------------------------------
    # 11. Active restriction
    # ---------------------------------------------------------

    if restriction is not None:

        if restriction.get("status") == "ACTIVE":
            failures.append(
                "Transaction is subject to an active restriction"
            )

    # ---------------------------------------------------------
    # 12. Authorization expiry
    # ---------------------------------------------------------

    created_at = authorization.get("created_at")

    if created_at:

        try:
            created_time = datetime.fromisoformat(
                created_at
            )

            expires_at = (
                created_time
                + timedelta(
                    minutes=AUTHORIZATION_EXPIRY_MINUTES
                )
            )

            if (
                    expires_at.replace(tzinfo=timezone.utc)
                    if expires_at.tzinfo is None
                    else expires_at
                ) < datetime.now(timezone.utc):
                failures.append(
                    "Authorization has expired"
                )

        except ValueError:
            failures.append(
                "Authorization timestamp is invalid"
            )

    else:
        failures.append(
            "Authorization timestamp is missing"
        )

    # ---------------------------------------------------------
    # 13. Authorization ID
    # ---------------------------------------------------------

    authorization_id = authorization.get(
        "authorization_id"
    )

    if not authorization_id:

        failures.append(
            "Authorization ID is missing"
        )

    elif authorization_id in USED_AUTHORIZATIONS:

        failures.append(
            "Authorization has already been used"
        )

    # ---------------------------------------------------------
    # 14. Final decision
    # ---------------------------------------------------------

    if failures:

        return {
            "execution_allowed": False,
            "status": "BLOCKED",
            "reasons": failures
        }

    # ---------------------------------------------------------
    # 15. Consume authorization
    # ---------------------------------------------------------

    USED_AUTHORIZATIONS.add(
        authorization_id
    )

    return {
        "execution_allowed": True,
        "status": "READY_FOR_EXECUTION",
        "reasons": []
    }