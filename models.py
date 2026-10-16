from pydantic import BaseModel, Field
from typing import Optional, List, Literal


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

class ResearchCandidateReview(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    notes: str = Field(min_length=1, max_length=4000)
    evidence_status: Literal[
        "not_verified",
        "partially_verified",
        "independently_verified",
        "rejected",
    ]
    trustng_relevance: int = Field(ge=1, le=5)
    lesson_for_africa: str = Field(min_length=1, max_length=4000)
