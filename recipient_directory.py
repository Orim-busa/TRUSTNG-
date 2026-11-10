"""Sandbox-only email recipient lookup for TrustNG.

Demo records only. This directory does not verify real-world identity,
prove mailbox ownership, or initiate or authorize payments.
"""
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from beneficiary_profiles import get_beneficiary_profile
from country_codes import normalize_corridor_countries




def validate_corridor_countries(model):
    (
        model.sender_country,
        model.receiver_country,
    ) = normalize_corridor_countries(
        model.sender_country,
        model.receiver_country,
    )
    return model


class EmailTransactionRequest(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=200)
    sender: str = Field(min_length=1, max_length=200)
    recipient_email: str = Field(min_length=3, max_length=254)
    asset: str = Field(min_length=1, max_length=30)
    amount: float = Field(gt=0, allow_inf_nan=False)
    channel: str = Field(min_length=1, max_length=50)
    country: str = Field(min_length=2, max_length=3)
    device_id: str | None = Field(default=None, max_length=200)
    sender_country: str | None = Field(default=None)
    receiver_country: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_corridor(self):
        return validate_corridor_countries(self)


class EmailPaymentRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)
    sender: str = Field(min_length=1, max_length=200)
    recipient_email: str = Field(min_length=3, max_length=254)
    asset: str = Field(min_length=1, max_length=30)
    amount: float = Field(gt=0, allow_inf_nan=False)
    channel: str = Field(min_length=1, max_length=50)
    country: str = Field(min_length=2, max_length=3)
    device_id: str | None = Field(default=None, max_length=200)
    sender_country: str | None = Field(default=None)
    receiver_country: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_corridor(self):
        return validate_corridor_countries(self)


class RecipientRegistrationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    recipient_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    phone_number: str = Field(min_length=7, max_length=20)
    source: str = Field(default="SANDBOX", pattern="^SANDBOX$")




class RecipientEmailVerificationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)


class RecipientEmailVerificationConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    email_code: str = Field(min_length=6, max_length=6, pattern="^[0-9]{6}$")
    phone_code: str = Field(min_length=6, max_length=6, pattern="^[0-9]{6}$")


class RecipientLookupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


_DEMO_RECIPIENTS = {
    "demo.recipient002@trustng.test": {
        "recipient_id": "user_002",
        "display_name": "Demo Recipient 002",
    },
    "demo.recipient003@trustng.test": {
        "recipient_id": "user_003",
        "display_name": "Demo Recipient 003",
    },
}


def lookup_recipient(email: str):
    normalized = email.strip().casefold()

    if (
        len(normalized) > 254
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized)
    ):
        raise ValueError("Enter a valid email address.")

    record = None
    import os

    if os.environ.get("DATABASE_URL"):
        import database
        record = database.get_recipient_by_email(normalized)
        # In database mode, do not silently fall back to demo aliases.
    else:
        demo = _DEMO_RECIPIENTS.get(normalized)
        if demo is not None:
            record = {
                "recipient_id": demo["recipient_id"],
                "display_name": demo["display_name"],
                "email_ownership_status": "UNVERIFIED",
                "phone_ownership_status": "UNVERIFIED",
                "contact_verification_status": "UNVERIFIED",
                "source": "SANDBOX",
            }

    if record is None:
        return None

    profile = get_beneficiary_profile(record["recipient_id"])
    return {
        "recipient_id": record["recipient_id"],
        "display_name": record["display_name"],
        "verification_level": profile.get("verification_level", "UNKNOWN"),
        "email_ownership_status": record.get("email_ownership_status", "UNVERIFIED"),
        "phone_ownership_status": record.get("phone_ownership_status", "UNVERIFIED"),
        "contact_verification_status": record.get(
            "contact_verification_status", "UNVERIFIED"
        ),
        "directory": record.get("source", "SANDBOX"),
        "identity_verified": False,
        "payment_authorized": False,
        "funds_moved": False,
    }
