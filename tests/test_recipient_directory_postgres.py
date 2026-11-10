"""Opt-in PostgreSQL integration test for email recipient verification."""

import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from dotenv import dotenv_values

import database


def test_email_recipient_verification_and_payment_request_postgres(monkeypatch):
    if os.getenv("TRUSTNG_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set TRUSTNG_RUN_POSTGRES_INTEGRATION=1 to opt in.")

    env_file = dotenv_values(Path.cwd() / ".env")

    test_url = (
        os.environ.get("TRUSTNG_TEST_DATABASE_URL")
        or env_file.get("TRUSTNG_TEST_DATABASE_URL")
    )
    if not test_url:
        pytest.fail("TRUSTNG_TEST_DATABASE_URL is not configured.")

    production_urls = {
        value
        for value in (
            os.environ.get("DATABASE_URL"),
            env_file.get("DATABASE_URL"),
        )
        if value
    }
    if not production_urls:
        pytest.fail(
            "Refusing integration writes: production DATABASE_URL "
            "must be configured so the test database can be distinguished."
        )

    test_host = urlparse(test_url).hostname
    if not test_host:
        pytest.fail("Refusing integration writes: test URL has no valid hostname.")

    for production_url in production_urls:
        production_host = urlparse(production_url).hostname
        if (
            not production_host
            or test_host.lower() == production_host.lower()
        ):
            pytest.fail(
                "Refusing integration writes: test database hostname matches "
                "or cannot be distinguished from a configured production URL."
            )

    # All database helper calls below use the dedicated Neon test branch.
    monkeypatch.setenv("DATABASE_URL", test_url)

    # Use a temporary test-only pepper; never depend on a real production secret.
    monkeypatch.setenv(
        "TRUSTNG_OTP_PEPPER",
        "postgres-integration-test-pepper-not-a-production-secret",
    )

    required_tables = (
        "recipient_email_aliases",
        "recipient_email_verification_challenges",
        "email_payment_requests",
    )

    with database.get_database_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                to_regclass('public.recipient_email_aliases') AS recipients,
                to_regclass('public.recipient_email_verification_challenges') AS challenges,
                to_regclass('public.email_payment_requests') AS payment_requests
            """
        ).fetchone()

    if not rows or any(
        rows[column] is None
        for column in ("recipients", "challenges", "payment_requests")
    ):
        pytest.fail(
            "The Neon test branch must already contain all three email feature "
            "tables. This test will not create or migrate tables."
        )

    suffix = uuid4().hex
    email = f"postgres-integration-{suffix}@example.test"
    recipient_id = f"postgres-recipient-{suffix}"
    request_id = f"postgres-email-request-{suffix}"

    try:
        registration = database.register_recipient_email(
            email=email,
            recipient_id=recipient_id,
            display_name="PostgreSQL Integration Test",
            phone_number="+2348012345678",
            source="SANDBOX",
        )

        assert registration["email"] == email
        assert registration["email_ownership_status"] == "UNVERIFIED"
        assert registration["phone_ownership_status"] == "UNVERIFIED"
        assert registration["contact_verification_status"] == "UNVERIFIED"

        # Payment requests must not be accepted before both contacts are verified.
        with pytest.raises(ValueError):
            database.create_email_payment_request(
                request_id=request_id,
                sender_id=f"sender-{suffix}",
                recipient_id=recipient_id,
                recipient_email=email,
                asset="NGN",
                amount="100.00",
                channel="EMAIL",
                country="NG",
                risk_assessment={"decision": "REVIEW"},
                device_id=f"device-{suffix}",
            )

        challenge = database.start_recipient_email_verification(email)
        email_code = challenge["email_verification_code"]
        phone_code = challenge["phone_verification_code"]

        assert len(email_code) == 6 and email_code.isdigit()
        assert len(phone_code) == 6 and phone_code.isdigit()
        assert email_code != phone_code

        # Supply a wrong email code but the correct phone code.
        wrong_email_code = (
            "999999" if email_code != "999999" else "888888"
        )

        with pytest.raises(ValueError, match="Email verification code is incorrect"):
            database.confirm_recipient_email_verification(
                email,
                wrong_email_code,
                phone_code,
            )

        # Confirm that only the failed email-code counter increased.
        with database.get_database_connection() as connection:
            attempts = connection.execute(
                """
                SELECT attempts, phone_attempts
                FROM recipient_email_verification_challenges
                WHERE normalized_email = %s
                """,
                (email,),
            ).fetchone()

        assert attempts["attempts"] == 1
        assert attempts["phone_attempts"] == 0

        verification = database.confirm_recipient_email_verification(
            email,
            email_code,
            phone_code,
        )

        assert verification["contact_verification_status"] == "FULLY_VERIFIED"
        assert verification["email_ownership_status"] == "VERIFIED"
        assert verification["phone_ownership_status"] == "VERIFIED"
        assert verification["identity_verified"] is False
        assert verification["payment_authorized"] is False
        assert verification["funds_moved"] is False

        recipient = database.get_recipient_by_email(email)
        assert recipient["contact_verification_status"] == "FULLY_VERIFIED"
        assert recipient["identity_verified"] is False
        assert recipient["payment_authorized"] is False
        assert recipient["funds_moved"] is False

        request = database.create_email_payment_request(
            request_id=request_id,
            sender_id=f"sender-{suffix}",
            recipient_id=recipient_id,
            recipient_email=email,
            asset="NGN",
            amount="100.00",
            channel="EMAIL",
            country="NG",
            risk_assessment={"decision": "REVIEW", "score": 30},
            device_id=f"device-{suffix}",
        )

        assert request["request_id"] == request_id
        assert request["recipient_id"] == recipient_id
        assert request["status"] == "SANDBOX_RISK_ASSESSED"
        assert request["payment_authorized"] is False
        assert request["funds_moved"] is False
        assert request["created"] is True

    finally:
        # Delete only rows created by this test, from the verified test branch.
        with database.get_database_connection() as connection:
            connection.execute(
                """
                DELETE FROM email_payment_requests
                WHERE request_id = %s
                """,
                (request_id,),
            )
            connection.execute(
                """
                DELETE FROM recipient_email_verification_challenges
                WHERE normalized_email = %s
                """,
                (email,),
            )
            connection.execute(
                """
                DELETE FROM recipient_email_aliases
                WHERE normalized_email = %s
                  AND recipient_id = %s
                """,
                (email, recipient_id),
            )

def test_recipient_postgres_dual_otp_lockout_and_cooldown(monkeypatch):
    if os.getenv("TRUSTNG_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set TRUSTNG_RUN_POSTGRES_INTEGRATION=1 to opt in.")

    env_file = dotenv_values(Path.cwd() / ".env")
    test_url = (
        os.environ.get("TRUSTNG_TEST_DATABASE_URL")
        or env_file.get("TRUSTNG_TEST_DATABASE_URL")
    )
    if not test_url:
        pytest.fail("TRUSTNG_TEST_DATABASE_URL is not configured.")

    production_urls = {
        value for value in (
            os.environ.get("DATABASE_URL"),
            env_file.get("DATABASE_URL"),
        ) if value
    }
    if not production_urls:
        pytest.fail("Refusing integration writes: production DATABASE_URL is not configured.")

    test_host = urlparse(test_url).hostname
    if not test_host:
        pytest.fail("Refusing integration writes: test URL has no valid hostname.")

    for production_url in production_urls:
        production_host = urlparse(production_url).hostname
        if not production_host or test_host.lower() == production_host.lower():
            pytest.fail("Refusing integration writes: test database hostname matches production.")

    monkeypatch.setenv("DATABASE_URL", test_url)
    monkeypatch.setenv(
        "TRUSTNG_OTP_PEPPER",
        "postgres-integration-test-pepper-not-a-production-secret",
    )

    with database.get_database_connection() as connection:
        tables = connection.execute(
            """
            SELECT
                to_regclass('public.recipient_email_aliases') AS recipients,
                to_regclass('public.recipient_email_verification_challenges') AS challenges
            """
        ).fetchone()

    if not tables or tables["recipients"] is None or tables["challenges"] is None:
        pytest.fail("The test database must already contain recipient verification tables.")

    suffix = uuid4().hex
    email = f"postgres-lockout-{suffix}@example.test"
    recipient_id = f"postgres-lockout-recipient-{suffix}"

    try:
        database.register_recipient_email(
            email=email,
            recipient_id=recipient_id,
            display_name="PostgreSQL OTP Lockout Test",
            phone_number="+2348012345678",
            source="SANDBOX",
        )

        first = database.start_recipient_email_verification(email)

        with pytest.raises(ValueError, match="already active"):
            database.start_recipient_email_verification(email)

        wrong_email = next(
            code for code in ("000000", "111111", "222222")
            if code not in {
                first["email_verification_code"],
                first["phone_verification_code"],
            }
        )

        for _ in range(5):
            with pytest.raises(ValueError, match="Email verification code is incorrect"):
                database.confirm_recipient_email_verification(
                    email, wrong_email, first["phone_verification_code"]
                )

        with database.get_database_connection() as connection:
            counters = connection.execute(
                """
                SELECT attempts, phone_attempts
                FROM recipient_email_verification_challenges
                WHERE normalized_email = %s
                """,
                (email,),
            ).fetchone()

        assert counters["attempts"] == 5
        assert counters["phone_attempts"] == 0

        with pytest.raises(ValueError, match="Too many attempts"):
            database.confirm_recipient_email_verification(
                email,
                first["email_verification_code"],
                first["phone_verification_code"],
            )

        # Age only this test-created challenge to exercise the 60-second rule.
        with database.get_database_connection() as connection:
            updated = connection.execute(
                """
                UPDATE recipient_email_verification_challenges
                SET created_at = NOW() - INTERVAL '61 seconds'
                WHERE normalized_email = %s
                """,
                (email,),
            )
            assert updated.rowcount == 1

        second = database.start_recipient_email_verification(email)
        wrong_phone = next(
            code for code in ("000000", "111111", "222222")
            if code not in {
                second["email_verification_code"],
                second["phone_verification_code"],
            }
        )

        for _ in range(5):
            with pytest.raises(ValueError, match="Phone verification code is incorrect"):
                database.confirm_recipient_email_verification(
                    email, second["email_verification_code"], wrong_phone
                )

        with database.get_database_connection() as connection:
            counters = connection.execute(
                """
                SELECT attempts, phone_attempts
                FROM recipient_email_verification_challenges
                WHERE normalized_email = %s
                """,
                (email,),
            ).fetchone()

        assert counters["attempts"] == 0
        assert counters["phone_attempts"] == 5

        with pytest.raises(ValueError, match="Too many attempts"):
            database.confirm_recipient_email_verification(
                email,
                second["email_verification_code"],
                second["phone_verification_code"],
            )

    finally:
        with database.get_database_connection() as connection:
            connection.execute(
                """
                DELETE FROM recipient_email_verification_challenges
                WHERE normalized_email = %s
                """,
                (email,),
            )
            connection.execute(
                """
                DELETE FROM recipient_email_aliases
                WHERE normalized_email = %s AND recipient_id = %s
                """,
                (email, recipient_id),
            )
