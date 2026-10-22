"""Advisory-only Account Trust Check with sandbox OTP."""
import hashlib
import os
import secrets
import time
from threading import Lock

OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
MAX_OTP_SESSIONS = 1000
OTP_START_WINDOW_SECONDS = 900
OTP_START_MAX_REQUESTS = 3
MAX_OTP_RATE_LIMIT_KEYS = 5000

_sessions = {}
_otp_start_attempts = {}
_lock = Lock()


class OTPStartRateLimitError(RuntimeError):
    pass


def start_sandbox_otp(phone_number):
    if os.environ.get("TRUSTNG_OTP_MODE", "sandbox").lower() != "sandbox":
        raise RuntimeError("An authorized OTP provider is not configured.")

    phone_hash = hashlib.sha256(phone_number.strip().encode()).hexdigest()
    now = time.time()

    with _lock:
        expired = [
            key for key, value in _sessions.items()
            if now >= value["expires"]
        ]
        for key in expired:
            _sessions.pop(key, None)

        stale_hashes = [
            key for key, timestamps in _otp_start_attempts.items()
            if not timestamps
            or now - timestamps[-1] >= OTP_START_WINDOW_SECONDS
        ]
        for key in stale_hashes:
            _otp_start_attempts.pop(key, None)

        if len(_sessions) >= MAX_OTP_SESSIONS:
            raise RuntimeError(
                "Sandbox OTP session capacity reached; try again later."
            )

        attempts = [
            timestamp
            for timestamp in _otp_start_attempts.get(phone_hash, [])
            if now - timestamp < OTP_START_WINDOW_SECONDS
        ]

        if len(attempts) >= OTP_START_MAX_REQUESTS:
            raise OTPStartRateLimitError(
                "Too many sandbox OTP requests for this phone number; "
                "try again after the rate-limit window expires."
            )

        if (
            phone_hash not in _otp_start_attempts
            and len(_otp_start_attempts) >= MAX_OTP_RATE_LIMIT_KEYS
        ):
            raise RuntimeError(
                "Sandbox OTP rate-limit capacity reached; try again later."
            )

        verification_id = secrets.token_urlsafe(24)
        code = f"{secrets.randbelow(1_000_000):06d}"
        _sessions[verification_id] = {
            "phone_hash": phone_hash,
            "code_hash": hashlib.sha256(code.encode()).hexdigest(),
            "expires": now + OTP_TTL_SECONDS,
            "attempts": 0,
            "verified": False,
        }

        attempts.append(now)
        _otp_start_attempts[phone_hash] = attempts

    return {
        "verification_id": verification_id,
        "status": "SANDBOX_CODE_ISSUED",
        "mode": "SANDBOX",
        "message": "No SMS was sent. This is a sandbox-only code.",
        "sandbox_code": code,
        "expires_in_seconds": OTP_TTL_SECONDS,
    }


def verify_sandbox_otp(verification_id, code):
    with _lock:
        session = _sessions.get(verification_id)
        if not session or session["verified"]:
            return False
        if time.time() >= session["expires"]:
            _sessions.pop(verification_id, None)
            return False
        if session["attempts"] >= OTP_MAX_ATTEMPTS:
            _sessions.pop(verification_id, None)
            return False
        session["attempts"] += 1
        valid = secrets.compare_digest(
            session["code_hash"], hashlib.sha256(code.encode()).hexdigest()
        )
        if valid:
            session["verified"] = True
            return True
        if session["attempts"] >= OTP_MAX_ATTEMPTS:
            _sessions.pop(verification_id, None)
        return False


def assess_account_trust(country, account_identifier, phone_verified=False):
    country = country.strip().upper()
    account = account_identifier.strip()
    if len(country) != 2 or not country.isalpha():
        raise ValueError("Country must be a two-letter country code.")
    if not account.isdigit() or not 5 <= len(account) <= 64:
        raise ValueError("Account identifier must contain 5–64 digits.")

    account_reference = secrets.token_hex(6)
    return {
        "country": country,
        "account_reference": account_reference,
        "account_age_status": "UNAVAILABLE",
        "account_age_days": None,
        "phone_verification": "SANDBOX_VERIFIED" if phone_verified else "NOT_VERIFIED",
        "risk_level": "UNKNOWN",
        "recommendation": "CAUTION_REVIEW",
        "reasons": [
            "No authorized bank-data provider is connected; account age is unavailable.",
            "An account number alone cannot establish ownership or trustworthiness.",
            (
                "Sandbox phone verification does not establish bank-account ownership."
                if phone_verified else "Phone ownership has not been verified."
            ),
        ],
        "provider_status": "NOT_CONNECTED",
        "advisory_only": True,
        "transfer_authorized": False,
        "transfer_executed": False,
    }


from pydantic import BaseModel, Field


class AccountTrustOTPStartRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)


class AccountTrustOTPVerifyRequest(BaseModel):
    verification_id: str = Field(min_length=20, max_length=100)
    code: str = Field(pattern=r"^[0-9]{6}$")


class AccountTrustCheckRequest(BaseModel):
    country: str = Field(default="NG", min_length=2, max_length=2)
    account_identifier: str = Field(min_length=5, max_length=64)
    phone_number: str = Field(min_length=7, max_length=20)
    verification_id: str | None = Field(default=None, max_length=100)


def consume_verified_sandbox_otp(verification_id, phone_number):
    phone_hash = hashlib.sha256(phone_number.strip().encode()).hexdigest()
    with _lock:
        session = _sessions.get(verification_id)
        if not session or not session["verified"]:
            return False
        if time.time() >= session["expires"]:
            _sessions.pop(verification_id, None)
            return False
        if not secrets.compare_digest(session["phone_hash"], phone_hash):
            return False
        _sessions.pop(verification_id, None)
        return True
