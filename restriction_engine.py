from datetime import datetime, timedelta
import uuid


def create_restriction(
    account_reference,
    restrictions,
    reason,
    risk_level,
    policy,
    policy_version,
    duration_minutes=60
):
    restriction_id = str(uuid.uuid4())

    created_at = datetime.utcnow()
    expires_at = created_at + timedelta(minutes=duration_minutes)

    return {
        "restriction_id": restriction_id,
        "account_reference": account_reference,
        "restrictions": restrictions,
        "reason": reason,
        "risk_level": risk_level,
        "policy": policy,
        "policy_version": policy_version,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "status": "ACTIVE"
    }