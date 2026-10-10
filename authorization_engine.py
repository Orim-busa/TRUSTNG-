from datetime import datetime
import uuid


def create_authorization(
    transaction_id,
    sender,
    receiver,
    asset,
    amount,
    channel,
    country,
    device_id,
    decision,
    risk_level,
    trust_level,
    restrictions
):
    """
    Creates an authorization record bound to the exact
    transaction details.

    The authorization is not only tied to a transaction ID.
    It is also tied to the sender, receiver, asset, amount,
    channel, country, and device.

    This prevents an authorization from being reused against
    a modified transaction.
    """

    authorization_id = str(uuid.uuid4())

    if decision == "RESTRICT":
        status = "DENIED"
        required_level = "BLOCKED"

    elif decision == "REVIEW":
        status = "PENDING"
        required_level = "STEP_UP"

    else:
        status = "AUTHORIZED"
        required_level = "STANDARD"

    return {
        "authorization_id": authorization_id,

        "transaction_id": transaction_id,

        "sender": sender,
        "receiver": receiver,

        "asset": asset,
        "amount": amount,

        "channel": channel,
        "country": country,
        "device_id": device_id,

        "status": status,
        "required_level": required_level,

        "risk_level": risk_level,
        "trust_level": trust_level,

        "restrictions": restrictions,

        "created_at": datetime.utcnow().isoformat()
    }