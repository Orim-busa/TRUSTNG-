from pydantic import BaseModel
from typing import Optional, List


class Transaction(BaseModel):
    transaction_id: str
    sender: str
    receiver: str
    asset: str
    amount: float
    channel: str
    country: str
    device_id: Optional[str] = None


class RiskSignal(BaseModel):
    type: str
    severity: str
    message: str


class Decision(BaseModel):
    decision: str
    risk_level: str
    reasons: List[str]
    policy: str
    policy_version: str
    action: str
    restrictions: List[str]