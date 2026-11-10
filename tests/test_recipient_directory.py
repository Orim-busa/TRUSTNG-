from fastapi.testclient import TestClient
import pytest

import main
import recipient_directory
from recipient_directory import EmailPaymentRequest, EmailTransactionRequest


@pytest.fixture(autouse=True)
def disable_database_for_sandbox_tests(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)



def test_lookup_requires_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    client = TestClient(main.app)

    response = client.post(
        "/v1/recipients/lookup",
        json={"email": "demo.recipient002@trustng.test"},
    )

    assert response.status_code == 401


def test_lookup_returns_sandbox_recipient_without_authorizing_payment(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    client = TestClient(main.app)

    response = client.post(
        "/v1/recipients/lookup",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "  DEMO.RECIPIENT002@TRUSTNG.TEST "},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recipient_id"] == "user_002"
    assert body["verification_level"] == "VERIFIED"
    assert body["directory"] == "SANDBOX"
    assert body["identity_verified"] is False
    assert body["payment_authorized"] is False
    assert body["funds_moved"] is False


def test_unknown_email_is_not_found(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    client = TestClient(main.app)

    response = client.post(
        "/v1/recipients/lookup",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "nobody@example.test"},
    )

    assert response.status_code == 404


def test_invalid_email_is_rejected(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    client = TestClient(main.app)

    response = client.post(
        "/v1/recipients/lookup",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "not-an-email"},
    )

    assert response.status_code == 400


def test_transaction_by_email_rejects_unverified_contacts(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    client = TestClient(main.app)

    response = client.post(
        "/v1/transactions/check-by-email",
        headers={"X-API-Key": "recipient-test-key"},
        json={
            "transaction_id": "recipient-unverified-test",
            "sender": "sender_001",
            "recipient_email": "demo.recipient002@trustng.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )

    assert response.status_code == 409
    assert "both" in response.json()["detail"].lower()


def test_transaction_by_email_accepts_fully_verified_contacts_without_authorizing_payment(
    monkeypatch,
):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setattr(
        recipient_directory,
        "lookup_recipient",
        lambda email: {
            "recipient_id": "user_verified",
            "display_name": "Verified Contact",
            "verification_level": "UNKNOWN",
            "email_ownership_status": "VERIFIED",
            "phone_ownership_status": "VERIFIED",
            "contact_verification_status": "FULLY_VERIFIED",
            "directory": "SANDBOX",
            "identity_verified": False,
            "payment_authorized": False,
            "funds_moved": False,
        },
    )
    monkeypatch.setattr(
        main,
        "evaluate",
        lambda transaction: {
            "decision": "REVIEW",
            "risk_level": "LOW",
            "action": "HOLD_FOR_REVIEW",
        },
    )

    client = TestClient(main.app)
    response = client.post(
        "/v1/transactions/check-by-email",
        headers={"X-API-Key": "recipient-test-key"},
        json={
            "transaction_id": "recipient-verified-test",
            "sender": "sender_001",
            "recipient_email": "verified@example.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )

    assert response.status_code == 200
    recipient = response.json()["recipient"]
    assert recipient["contact_verification_status"] == "FULLY_VERIFIED"
    assert recipient["email_ownership_status"] == "VERIFIED"
    assert recipient["phone_ownership_status"] == "VERIFIED"
    assert recipient["identity_verified"] is False
    assert recipient["confirmation_limits"]["payment_authorized"] is False
    assert response.json()["payment_authorized"] is False
    assert response.json()["funds_moved"] is False


from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import database


class FakeOtpCursor:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class FakeOtpConnection:
    def __init__(self, challenge):
        self.challenge = challenge
        self.email_status = "UNVERIFIED"
        self.phone_status = "UNVERIFIED"

    def execute(self, query, params=None):
        if "SELECT code_hash, phone_code_hash" in query:
            return FakeOtpCursor(self.challenge)

        if "UPDATE recipient_email_aliases" in query:
            self.email_status = "VERIFIED"
            self.phone_status = "VERIFIED"
            return FakeOtpCursor(rowcount=1)

        if "attempts = attempts +" in query:
            self.challenge["attempts"] += params[0]
            self.challenge["phone_attempts"] += params[1]
            return FakeOtpCursor(rowcount=1)

        if "SET consumed_at = NOW()" in query:
            self.challenge["consumed_at"] = datetime.now(timezone.utc)
            return FakeOtpCursor(rowcount=1)

        raise AssertionError(f"Unexpected SQL in OTP test: {query}")


def install_fake_otp_database(monkeypatch, challenge):
    connection = FakeOtpConnection(challenge)

    @contextmanager
    def fake_connection():
        yield connection

    monkeypatch.setattr(database, "get_database_connection", fake_connection)
    return connection


def make_otp_challenge(email_code="123456", phone_code="654321"):
    return {
        "code_hash": database._hash_recipient_otp(email_code),
        "phone_code_hash": database._hash_recipient_otp(phone_code),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "attempts": 0,
        "phone_attempts": 0,
        "consumed_at": None,
    }


def test_recipient_otp_hash_requires_private_pepper(monkeypatch):
    monkeypatch.delenv("TRUSTNG_OTP_PEPPER", raising=False)

    with pytest.raises(RuntimeError, match="TRUSTNG_OTP_PEPPER"):
        database._hash_recipient_otp("123456")


def test_recipient_otp_hash_is_keyed_and_deterministic(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)
    first = database._hash_recipient_otp("123456")
    second = database._hash_recipient_otp("123456")

    assert first == second

    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "b" * 64)
    assert database._hash_recipient_otp("123456") != first


def test_recipient_otp_codes_cannot_be_swapped(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)
    challenge = make_otp_challenge()
    connection = install_fake_otp_database(monkeypatch, challenge)

    with pytest.raises(ValueError, match="Both verification codes are incorrect"):
        database.confirm_recipient_email_verification(
            "person@example.test", "654321", "123456"
        )

    assert challenge["attempts"] == 1
    assert challenge["phone_attempts"] == 1
    assert connection.email_status == "UNVERIFIED"
    assert connection.phone_status == "UNVERIFIED"


def test_recipient_otp_attempts_are_independent(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)
    challenge = make_otp_challenge()
    install_fake_otp_database(monkeypatch, challenge)

    with pytest.raises(ValueError, match="Phone verification code is incorrect"):
        database.confirm_recipient_email_verification(
            "person@example.test", "123456", "000000"
        )

    assert challenge["attempts"] == 0
    assert challenge["phone_attempts"] == 1


@pytest.mark.parametrize(
    ("counter", "email_code", "phone_code", "expected_error"),
    [
        ("attempts", "000000", "654321", "Email verification code is incorrect"),
        ("phone_attempts", "123456", "000000", "Phone verification code is incorrect"),
    ],
)
def test_fifth_incorrect_recipient_otp_locks_challenge(
    monkeypatch, counter, email_code, phone_code, expected_error
):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)
    challenge = make_otp_challenge()
    challenge[counter] = 4
    connection = install_fake_otp_database(monkeypatch, challenge)

    with pytest.raises(ValueError, match=expected_error):
        database.confirm_recipient_email_verification(
            "person@example.test", email_code, phone_code
        )

    assert challenge[counter] == 5

    with pytest.raises(ValueError, match="Too many attempts"):
        database.confirm_recipient_email_verification(
            "person@example.test", "123456", "654321"
        )

    assert challenge[counter] == 5
    assert connection.email_status == "UNVERIFIED"
    assert connection.phone_status == "UNVERIFIED"


def test_recipient_requires_both_codes_and_consumes_successful_challenge(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)
    challenge = make_otp_challenge()
    connection = install_fake_otp_database(monkeypatch, challenge)

    result = database.confirm_recipient_email_verification(
        "person@example.test", "123456", "654321"
    )

    assert result["contact_verification_status"] == "FULLY_VERIFIED"
    assert result["email_ownership_status"] == "VERIFIED"
    assert result["phone_ownership_status"] == "VERIFIED"
    assert result["identity_verified"] is False
    assert result["payment_authorized"] is False
    assert result["funds_moved"] is False
    assert connection.email_status == "VERIFIED"
    assert connection.phone_status == "VERIFIED"
    assert challenge["consumed_at"] is not None

    with pytest.raises(ValueError, match="already been used"):
        database.confirm_recipient_email_verification(
            "person@example.test", "123456", "654321"
        )


def test_expired_recipient_otp_challenge_is_consumed(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)
    challenge = make_otp_challenge()
    challenge["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    install_fake_otp_database(monkeypatch, challenge)

    with pytest.raises(ValueError, match="expired"):
        database.confirm_recipient_email_verification(
            "person@example.test", "123456", "654321"
        )

    assert challenge["consumed_at"] is not None


def test_production_recipient_verification_does_not_expose_sandbox_codes(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.delenv("TRUSTNG_ENV", raising=False)
    monkeypatch.delenv("TRUSTNG_PHONE_DELIVERY_MODE", raising=False)

    def must_not_start_challenge(email):
        raise AssertionError("Production must reject before creating an OTP challenge.")

    monkeypatch.setattr(
        main.database,
        "start_recipient_email_verification",
        must_not_start_challenge,
    )

    response = TestClient(main.app).post(
        "/v1/recipients/verification/start",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "person@example.test"},
    )

    assert response.status_code == 503
    assert "Sandbox OTP exposure is disabled" in response.json()["detail"]


def test_sandbox_recipient_verification_can_return_test_codes(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TRUSTNG_ENV", "sandbox")
    monkeypatch.setenv("TRUSTNG_PHONE_DELIVERY_MODE", "sandbox")
    monkeypatch.setattr(main.email_delivery, "smtp_mode_enabled", lambda: False)
    monkeypatch.setattr(
        main.database,
        "start_recipient_email_verification",
        lambda email: {
            "email": email,
            "email_verification_code": "123456",
            "phone_verification_code": "654321",
            "masked_phone": "+234******12",
            "expires_in_seconds": 600,
            "idempotency_key": "stable-test-key",
            "email_delivery_mode": "SMTP_OR_SANDBOX",
            "phone_delivery_mode": "SANDBOX_ONLY",
        },
    )

    response = TestClient(main.app).post(
        "/v1/recipients/verification/start",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "person@example.test"},
    )

    assert response.status_code == 200
    assert response.json()["email_verification_code"] == "123456"
    assert response.json()["phone_verification_code"] == "654321"
    assert response.json()["phone_delivery_mode"] == "SANDBOX_ONLY"



def test_complete_dual_otp_recipient_api_journey(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TRUSTNG_ENV", "sandbox")
    monkeypatch.setenv("TRUSTNG_PHONE_DELIVERY_MODE", "sandbox")
    monkeypatch.setattr(main.email_delivery, "smtp_mode_enabled", lambda: False)

    state = {
        "registered": False,
        "verified": False,
        "email": "journey@example.test",
        "email_code": "123456",
        "phone_code": "654321",
    }

    def fake_register(email, recipient_id, display_name, phone_number, source):
        assert not state["registered"]
        state["registered"] = True
        return {
            "email": email.strip().lower(),
            "recipient_id": recipient_id,
            "display_name": display_name,
            "masked_phone": "+234******12",
            "email_ownership_status": "UNVERIFIED",
            "phone_ownership_status": "UNVERIFIED",
            "contact_verification_status": "UNVERIFIED",
            "source": source,
        }

    def fake_start(email):
        assert state["registered"]
        assert not state["verified"]
        return {
            "email": email.strip().lower(),
            "email_verification_code": state["email_code"],
            "phone_verification_code": state["phone_code"],
            "masked_phone": "+234******12",
            "expires_in_seconds": 600,
            "idempotency_key": "stable-test-key",
            "email_delivery_mode": "SANDBOX",
            "phone_delivery_mode": "SANDBOX_ONLY",
        }

    def fake_confirm(email, email_code, phone_code):
        assert state["registered"]
        if email_code != state["email_code"]:
            raise ValueError("Email verification code is incorrect.")
        if phone_code != state["phone_code"]:
            raise ValueError("Phone verification code is incorrect.")

        state["verified"] = True
        return {
            "email": email.strip().lower(),
            "email_ownership_status": "VERIFIED",
            "phone_ownership_status": "VERIFIED",
            "contact_verification_status": "FULLY_VERIFIED",
            "identity_verified": False,
            "payment_authorized": False,
            "funds_moved": False,
        }

    def fake_lookup(email):
        if not state["registered"]:
            return None
        return {
            "recipient_id": "journey-recipient",
            "display_name": "Journey Test Recipient",
            "directory": "SANDBOX",
            "verification_level": "CONTACT_VERIFIED" if state["verified"] else "UNVERIFIED",
            "email_ownership_status": "VERIFIED" if state["verified"] else "UNVERIFIED",
            "phone_ownership_status": "VERIFIED" if state["verified"] else "UNVERIFIED",
            "contact_verification_status": "FULLY_VERIFIED" if state["verified"] else "UNVERIFIED",
            "identity_verified": False,
            "payment_authorized": False,
            "funds_moved": False,
        }

    monkeypatch.setattr(main.database, "register_recipient_email", fake_register)
    monkeypatch.setattr(main.database, "start_recipient_email_verification", fake_start)
    monkeypatch.setattr(main.database, "confirm_recipient_email_verification", fake_confirm)
    monkeypatch.setattr(recipient_directory, "lookup_recipient", fake_lookup)
    monkeypatch.setattr(
        main,
        "evaluate",
        lambda transaction: {
            "decision": "REVIEW",
            "risk_level": "LOW",
            "action": "HOLD_FOR_REVIEW",
        },
    )

    client = TestClient(main.app)
    headers = {"X-API-Key": "recipient-test-key"}

    registration = client.post(
        "/v1/recipients/register",
        headers=headers,
        json={
            "email": state["email"],
            "recipient_id": "journey-recipient",
            "display_name": "Journey Test Recipient",
            "phone_number": "+2348012345612",
            "source": "SANDBOX",
        },
    )
    assert registration.status_code == 200
    assert registration.json()["contact_verification_status"] == "UNVERIFIED"
    assert registration.json()["payment_authorized"] is False

    start = client.post(
        "/v1/recipients/verification/start",
        headers=headers,
        json={"email": state["email"]},
    )
    assert start.status_code == 200
    codes = start.json()
    assert codes["email_verification_code"] != codes["phone_verification_code"]
    assert codes["phone_delivery_mode"] == "SANDBOX_ONLY"

    rejected = client.post(
        "/v1/recipients/verification/confirm",
        headers=headers,
        json={
            "email": state["email"],
            "email_code": codes["email_verification_code"],
            "phone_code": "000000",
        },
    )
    assert rejected.status_code == 400
    assert state["verified"] is False

    confirmed = client.post(
        "/v1/recipients/verification/confirm",
        headers=headers,
        json={
            "email": state["email"],
            "email_code": codes["email_verification_code"],
            "phone_code": codes["phone_verification_code"],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["contact_verification_status"] == "FULLY_VERIFIED"

    transaction = client.post(
        "/v1/transactions/check-by-email",
        headers=headers,
        json={
            "transaction_id": "recipient-journey-test",
            "sender": "sender_001",
            "recipient_email": state["email"],
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )
    assert transaction.status_code == 200
    body = transaction.json()
    assert body["recipient"]["contact_verification_status"] == "FULLY_VERIFIED"
    assert body["recipient"]["identity_verified"] is False
    assert body["payment_authorized"] is False
    assert body["funds_moved"] is False
    assert body["mode"] == "SANDBOX_RISK_ASSESSMENT_ONLY"


def test_production_dual_otp_sends_both_codes_without_exposing_them(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TRUSTNG_ENV", "production")
    monkeypatch.setenv("TRUSTNG_PHONE_DELIVERY_MODE", "sendozi")

    calls = []

    monkeypatch.setattr(main.email_delivery, "smtp_mode_enabled", lambda: True)

    def fake_start(email):
        return {
            "email": email,
            "email_verification_code": "123456",
            "phone_verification_code": "654321",
            "phone_number": "+2348012345612",
            "masked_phone": "+234******12",
            "expires_in_seconds": 600,
            "idempotency_key": "stable-test-key",
        }

    def fake_email(email, code):
        calls.append(("email", email, code))

    def fake_sms(phone, code, idempotency_key):
        calls.append(("sms", phone, code, idempotency_key))
        return {"accepted": True, "mode": "SENDOZI_LIVE"}

    monkeypatch.setattr(
        main.database, "start_recipient_email_verification", fake_start
    )
    monkeypatch.setattr(
        main.email_delivery, "send_verification_email", fake_email
    )
    monkeypatch.setattr(
        main.sms_delivery, "send_verification_sms", fake_sms
    )

    response = TestClient(main.app).post(
        "/v1/recipients/verification/start",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "person@example.test"},
    )

    assert response.status_code == 200
    body = response.json()

    assert calls == [
        ("email", "person@example.test", "123456"),
        ("sms", "+2348012345612", "654321", "stable-test-key"),
    ]
    assert body["email_sent"] is True
    assert body["phone_sms_accepted"] is True
    assert body["phone_delivery_mode"] == "SENDOZI_LIVE"
    assert "123456" not in response.text
    assert "654321" not in response.text
    assert "+2348012345612" not in response.text
    assert "phone_number" not in body


def test_production_dual_otp_invalidates_challenge_when_sms_fails(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TRUSTNG_ENV", "production")
    monkeypatch.setenv("TRUSTNG_PHONE_DELIVERY_MODE", "sendozi")

    calls = []

    monkeypatch.setattr(main.email_delivery, "smtp_mode_enabled", lambda: True)
    monkeypatch.setattr(
        main.database,
        "start_recipient_email_verification",
        lambda email: {
            "email": email,
            "email_verification_code": "123456",
            "phone_verification_code": "654321",
            "phone_number": "+2348012345612",
            "masked_phone": "+234******12",
            "expires_in_seconds": 600,
            "idempotency_key": "stable-test-key",
        },
    )
    monkeypatch.setattr(
        main.email_delivery,
        "send_verification_email",
        lambda email, code: calls.append(("email", email, code)),
    )

    def fail_sms(phone, code, idempotency_key):
        calls.append(("sms", phone, code, idempotency_key))
        raise RuntimeError("Simulated SMS provider failure")

    monkeypatch.setattr(main.sms_delivery, "send_verification_sms", fail_sms)
    monkeypatch.setattr(
        main.database,
        "invalidate_recipient_email_verification",
        lambda email: calls.append(("invalidate", email)),
    )

    response = TestClient(main.app).post(
        "/v1/recipients/verification/start",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "person@example.test"},
    )

    assert response.status_code == 503
    assert calls == [
        ("email", "person@example.test", "123456"),
        ("sms", "+2348012345612", "654321", "stable-test-key"),
        ("invalidate", "person@example.test"),
    ]
    assert "123456" not in response.text
    assert "654321" not in response.text



def test_payment_request_by_email_requires_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    response = TestClient(main.app).post(
        "/v1/payment-requests/by-email",
        json={
            "request_id": "email-request-auth",
            "sender": "sender_001",
            "recipient_email": "verified@example.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )

    assert response.status_code == 401


def test_payment_request_by_email_requires_database(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = TestClient(main.app).post(
        "/v1/payment-requests/by-email",
        headers={"X-API-Key": "recipient-test-key"},
        json={
            "request_id": "email-request-no-db",
            "sender": "sender_001",
            "recipient_email": "verified@example.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )

    assert response.status_code == 503


def test_payment_request_by_email_rejects_unverified_recipient(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    monkeypatch.setattr(
        recipient_directory,
        "lookup_recipient",
        lambda email: {
            "recipient_id": "user_unverified",
            "display_name": "Unverified Contact",
            "contact_verification_status": "UNVERIFIED",
        },
    )

    def should_not_save(**kwargs):
        raise AssertionError("Unverified recipient must not be saved.")

    monkeypatch.setattr(database, "create_email_payment_request", should_not_save)

    response = TestClient(main.app).post(
        "/v1/payment-requests/by-email",
        headers={"X-API-Key": "recipient-test-key"},
        json={
            "request_id": "email-request-unverified",
            "sender": "sender_001",
            "recipient_email": "unverified@example.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )

    assert response.status_code == 409


def test_payment_request_by_email_creates_sandbox_request(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    monkeypatch.setattr(
        recipient_directory,
        "lookup_recipient",
        lambda email: {
            "recipient_id": "user_verified",
            "display_name": "Verified Contact",
            "contact_verification_status": "FULLY_VERIFIED",
            "email_ownership_status": "VERIFIED",
            "phone_ownership_status": "VERIFIED",
        },
    )

    monkeypatch.setattr(
        main,
        "evaluate",
        lambda transaction: {
            "decision": "REVIEW",
            "risk_level": "LOW",
            "action": "HOLD_FOR_REVIEW",
        },
    )

    saved_requests = []

    def fake_save(**kwargs):
        saved_requests.append(kwargs)
        return {
            "request_id": kwargs["request_id"],
            "recipient_id": kwargs["recipient_id"],
            "status": "SANDBOX_RISK_ASSESSED",
            "risk_assessment": kwargs["risk_assessment"],
            "payment_authorized": False,
            "funds_moved": False,
            "created": True,
            "created_at": "2026-10-30T12:00:00+00:00",
        }

    monkeypatch.setattr(database, "create_email_payment_request", fake_save)

    response = TestClient(main.app).post(
        "/v1/payment-requests/by-email",
        headers={"X-API-Key": "recipient-test-key"},
        json={
            "request_id": "email-request-success",
            "sender": "sender_001",
            "recipient_email": "verified@example.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
            "device_id": "device_001",
            "sender_country": "ng",
            "receiver_country": "gh",
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert body["request"]["request_id"] == "email-request-success"
    assert body["request"]["status"] == "SANDBOX_RISK_ASSESSED"
    assert body["request"]["created"] is True
    assert body["recipient"]["recipient_id"] == "user_verified"
    assert body["recipient"]["email_ownership_status"] == "VERIFIED"
    assert body["recipient"]["phone_ownership_status"] == "VERIFIED"
    assert body["payment_authorized"] is False
    assert body["funds_moved"] is False
    assert body["mode"] == "SANDBOX_REQUEST_ONLY"
    assert len(saved_requests) == 1
    assert saved_requests[0]["recipient_email"] == "verified@example.test"
    assert saved_requests[0]["device_id"] == "device_001"
    assert saved_requests[0]["sender_country"] == "NG"
    assert saved_requests[0]["receiver_country"] == "GH"


def test_payment_request_by_email_duplicate_conflict_returns_409(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    monkeypatch.setattr(
        recipient_directory,
        "lookup_recipient",
        lambda email: {
            "recipient_id": "user_verified",
            "display_name": "Verified Contact",
            "contact_verification_status": "FULLY_VERIFIED",
        },
    )
    monkeypatch.setattr(
        main,
        "evaluate",
        lambda transaction: {"decision": "REVIEW"},
    )

    def duplicate_request(**kwargs):
        raise ValueError("This request ID has already been used with different payment details.")

    monkeypatch.setattr(database, "create_email_payment_request", duplicate_request)

    response = TestClient(main.app).post(
        "/v1/payment-requests/by-email",
        headers={"X-API-Key": "recipient-test-key"},
        json={
            "request_id": "email-request-duplicate",
            "sender": "sender_001",
            "recipient_email": "verified@example.test",
            "asset": "NGN",
            "amount": 1000,
            "channel": "API",
            "country": "NG",
        },
    )

    assert response.status_code == 409
    assert "already been used" in response.json()["detail"]

@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            recipient_directory.RecipientEmailVerificationStartRequest,
            {
                "email": "person@example.test",
                "phone_number": "+2348012345678",
            },
        ),
        (
            recipient_directory.RecipientEmailVerificationConfirmRequest,
            {
                "email": "person@example.test",
                "email_code": "123456",
                "phone_code": "654321",
                "phone_number": "+2348012345678",
            },
        ),
    ],
)
def test_verification_requests_reject_customer_supplied_phone(model, payload):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        model.model_validate(payload)



@pytest.mark.parametrize(
    "model_class,id_field,id_value",
    [
        (EmailTransactionRequest, "transaction_id", "corridor-tx-001"),
        (EmailPaymentRequest, "request_id", "corridor-request-001"),
    ],
)
def test_email_request_normalizes_corridor_countries(
    model_class, id_field, id_value
):
    data = {
        id_field: id_value,
        "sender": "sender_001",
        "recipient_email": "recipient@example.test",
        "asset": "NGN",
        "amount": 1000,
        "channel": "API",
        "country": "NG",
        "sender_country": " ng ",
        "receiver_country": " gh ",
    }

    request = model_class(**data)

    assert request.sender_country == "NG"
    assert request.receiver_country == "GH"


@pytest.mark.parametrize(
    "model_class,id_field,id_value",
    [
        (EmailTransactionRequest, "transaction_id", "corridor-tx-002"),
        (EmailPaymentRequest, "request_id", "corridor-request-002"),
    ],
)
def test_email_request_rejects_only_one_corridor_country(
    model_class, id_field, id_value
):
    data = {
        id_field: id_value,
        "sender": "sender_001",
        "recipient_email": "recipient@example.test",
        "asset": "NGN",
        "amount": 1000,
        "channel": "API",
        "country": "NG",
        "sender_country": "NG",
    }

    with pytest.raises(ValueError):
        model_class(**data)


@pytest.mark.parametrize(
    "model_class,id_field,id_value",
    [
        (EmailTransactionRequest, "transaction_id", "corridor-tx-003"),
        (EmailPaymentRequest, "request_id", "corridor-request-003"),
    ],
)
def test_email_request_rejects_non_alphabetic_corridor_country(
    model_class, id_field, id_value
):
    data = {
        id_field: id_value,
        "sender": "sender_001",
        "recipient_email": "recipient@example.test",
        "asset": "NGN",
        "amount": 1000,
        "channel": "API",
        "country": "NG",
        "sender_country": "N1",
        "receiver_country": "GH",
    }

    with pytest.raises(ValueError):
        model_class(**data)


@pytest.mark.parametrize(
    "model_class,id_field,id_value",
    [
        (EmailTransactionRequest, "transaction_id", "legacy-tx-001"),
        (EmailPaymentRequest, "request_id", "legacy-request-001"),
    ],
)
def test_email_request_allows_legacy_without_corridor_countries(
    model_class, id_field, id_value
):
    data = {
        id_field: id_value,
        "sender": "sender_001",
        "recipient_email": "recipient@example.test",
        "asset": "NGN",
        "amount": 1000,
        "channel": "API",
        "country": "NG",
    }

    request = model_class(**data)

    assert request.sender_country is None
    assert request.receiver_country is None
def test_production_dual_otp_invalidates_challenge_when_email_fails(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "recipient-test-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    monkeypatch.setenv("TRUSTNG_ENV", "production")
    monkeypatch.setenv("TRUSTNG_PHONE_DELIVERY_MODE", "sendozi")

    calls = []

    monkeypatch.setattr(main.email_delivery, "smtp_mode_enabled", lambda: True)

    monkeypatch.setattr(
        main.database,
        "start_recipient_email_verification",
        lambda email: {
            "email": email,
            "email_verification_code": "123456",
            "phone_verification_code": "654321",
            "phone_number": "+2348012345612",
            "masked_phone": "+234******12",
            "expires_in_seconds": 600,
            "idempotency_key": "stable-test-key",
        },
    )

    def fail_email(email, code):
        calls.append(("email", email, code))
        raise RuntimeError("Simulated SMTP failure")

    monkeypatch.setattr(
        main.email_delivery,
        "send_verification_email",
        fail_email,
    )

    def unexpected_sms(*args):
        calls.append(("sms_attempted",))
        raise AssertionError("SMS must not be attempted after email failure.")

    monkeypatch.setattr(
        main.sms_delivery,
        "send_verification_sms",
        unexpected_sms,
    )

    monkeypatch.setattr(
        main.database,
        "invalidate_recipient_email_verification",
        lambda email: calls.append(("invalidate", email)),
    )

    response = TestClient(main.app).post(
        "/v1/recipients/verification/start",
        headers={"X-API-Key": "recipient-test-key"},
        json={"email": "person@example.test"},
    )

    assert response.status_code == 503
    assert calls == [
        ("email", "person@example.test", "123456"),
        ("invalidate", "person@example.test"),
    ]
    assert "123456" not in response.text
    assert "654321" not in response.text



@pytest.mark.parametrize(
    "model_class,id_field,id_value",
    [
        (EmailTransactionRequest, "transaction_id", "iso-tx-001"),
        (EmailPaymentRequest, "request_id", "iso-request-001"),
    ],
)
@pytest.mark.parametrize("invalid_code", ["ZZ", "XX", "123", "N1"])
def test_email_request_rejects_invalid_iso_corridor_codes(
    model_class, id_field, id_value, invalid_code
):
    data = {
        id_field: id_value,
        "sender": "sender_001",
        "recipient_email": "recipient@example.test",
        "asset": "NGN",
        "amount": 1000,
        "channel": "API",
        "country": "NG",
        "sender_country": invalid_code,
        "receiver_country": "GH",
    }

    with pytest.raises(ValueError, match="ISO 3166-1"):
        model_class(**data)


@pytest.mark.parametrize("country_code", ["NG", "GH", "GB", "US", "KE"])
def test_email_request_accepts_valid_iso_corridor_codes(country_code):
    request = EmailPaymentRequest(
        request_id=f"iso-valid-{country_code}",
        sender="sender_001",
        recipient_email="recipient@example.test",
        asset="NGN",
        amount=1000,
        channel="API",
        country="NG",
        sender_country=country_code,
        receiver_country="GH",
    )

    assert request.sender_country == country_code
    assert request.receiver_country == "GH"
def test_consumed_recipient_challenge_can_be_replaced_after_cooldown(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_PEPPER", "a" * 64)

    class FakeConnection:
        def execute(self, query, params=None):
            if "SELECT normalized_email, phone_number" in query:
                return FakeOtpCursor({
                    "normalized_email": "person@example.test",
                    "phone_number": "+2348012345678",
                    "email_ownership_status": "UNVERIFIED",
                    "phone_ownership_status": "UNVERIFIED",
                })

            if "INSERT INTO recipient_email_verification_challenges" in query:
                assert "consumed_at IS NOT NULL" in query
                assert "INTERVAL '60 seconds'" in query
                return FakeOtpCursor({
                    "normalized_email": "person@example.test",
                    "created_at": datetime.now(timezone.utc),
                })

            raise AssertionError(f"Unexpected SQL: {query}")

    @contextmanager
    def fake_connection():
        yield FakeConnection()

    monkeypatch.setattr(database, "get_database_connection", fake_connection)

    result = database.start_recipient_email_verification(
        "person@example.test"
    )

    assert result["email"] == "person@example.test"
    assert len(result["email_verification_code"]) == 6
    assert len(result["phone_verification_code"]) == 6
    assert result["email_verification_code"] != result["phone_verification_code"]
