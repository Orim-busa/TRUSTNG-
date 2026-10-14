from datetime import datetime, timedelta, timezone
import uuid

from execution_gate import validate_execution
from models import Transaction


def make_transaction():
    return Transaction(
        transaction_id="TEST-TXN-001",
        sender="sender_001",
        receiver="receiver_001",
        asset="NGN",
        amount=5000,
        channel="BANK",
        country="NG",
        device_id="device_001",
    )


def make_authorization(transaction, **overrides):
    authorization = {
        "authorization_id": str(uuid.uuid4()),
        "transaction_id": transaction.transaction_id,
        "sender": transaction.sender,
        "receiver": transaction.receiver,
        "asset": transaction.asset,
        "amount": transaction.amount,
        "channel": transaction.channel,
        "country": transaction.country,
        "device_id": transaction.device_id,
        "status": "AUTHORIZED",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    authorization.update(overrides)
    return authorization


def test_missing_authorization_is_blocked():
    result = validate_execution(make_transaction(), None)

    assert result["execution_allowed"] is False
    assert result["status"] == "BLOCKED"


def test_matching_authorization_is_allowed():
    transaction = make_transaction()
    authorization = make_authorization(transaction)

    result = validate_execution(transaction, authorization)

    assert result["execution_allowed"] is True
    assert result["status"] == "READY_FOR_EXECUTION"


def test_changed_amount_is_blocked():
    transaction = make_transaction()
    authorization = make_authorization(
        transaction,
        amount=999999,
    )

    result = validate_execution(transaction, authorization)

    assert result["execution_allowed"] is False
    assert any("amount" in reason.lower() for reason in result["reasons"])


def test_pending_authorization_is_blocked():
    transaction = make_transaction()
    authorization = make_authorization(
        transaction,
        status="PENDING",
    )

    result = validate_execution(transaction, authorization)

    assert result["execution_allowed"] is False


def test_active_restriction_blocks_execution():
    transaction = make_transaction()
    authorization = make_authorization(transaction)

    result = validate_execution(
        transaction,
        authorization,
        restriction={"status": "ACTIVE"},
    )

    assert result["execution_allowed"] is False
    assert any("restriction" in reason.lower() for reason in result["reasons"])


def test_expired_authorization_is_blocked():
    transaction = make_transaction()
    expired_time = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()
    authorization = make_authorization(
        transaction,
        created_at=expired_time,
    )

    result = validate_execution(transaction, authorization)

    assert result["execution_allowed"] is False
    assert any("expired" in reason.lower() for reason in result["reasons"])


def test_authorization_cannot_be_reused():
    transaction = make_transaction()
    authorization = make_authorization(transaction)

    first_result = validate_execution(transaction, authorization)
    second_result = validate_execution(transaction, authorization)

    assert first_result["execution_allowed"] is True
    assert second_result["execution_allowed"] is False
    assert any("already been used" in reason.lower()
               for reason in second_result["reasons"])
