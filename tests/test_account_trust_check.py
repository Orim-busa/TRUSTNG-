import pytest
import account_trust_check as service


def test_age_unavailable_and_transfer_never_authorized():
    result = service.assess_account_trust("NG", "0123456789")
    assert result["account_age_status"] == "UNAVAILABLE"
    assert result["account_age_days"] is None
    assert result["risk_level"] == "UNKNOWN"
    assert result["recommendation"] == "CAUTION_REVIEW"
    assert result["transfer_authorized"] is False
    assert result["transfer_executed"] is False


def test_account_number_not_returned():
    account = "0123456789"
    result = service.assess_account_trust("NG", account)
    assert account not in str(result)


def test_invalid_account_rejected():
    with pytest.raises(ValueError):
        service.assess_account_trust("NG", "invalid-account")


def test_sandbox_otp_is_single_use(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_MODE", "sandbox")
    started = service.start_sandbox_otp("+2348012345678")
    assert started["mode"] == "SANDBOX"
    assert "No SMS was sent" in started["message"]
    assert service.verify_sandbox_otp(
        started["verification_id"], started["sandbox_code"]
    )
    assert not service.verify_sandbox_otp(
        started["verification_id"], started["sandbox_code"]
    )


def test_wrong_otp_fails(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_MODE", "sandbox")
    started = service.start_sandbox_otp("+2348012345678")
    assert not service.verify_sandbox_otp(
        started["verification_id"], "000000"
    )


def test_phone_verification_does_not_make_account_safe():
    result = service.assess_account_trust("NG", "0123456789", True)
    assert result["phone_verification"] == "SANDBOX_VERIFIED"
    assert result["account_age_status"] == "UNAVAILABLE"
    assert result["risk_level"] == "UNKNOWN"
    assert result["transfer_authorized"] is False

def test_start_otp_cleans_expired_sessions(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_MODE", "sandbox")

    with service._lock:
        original_sessions = service._sessions.copy()
        service._sessions.clear()
        service._sessions["expired-test-session"] = {
            "phone_hash": "expired",
            "code_hash": "expired",
            "expires": 0,
            "attempts": 0,
            "verified": False,
        }

    try:
        started = service.start_sandbox_otp("+2348012345678")
        with service._lock:
            assert "expired-test-session" not in service._sessions
            assert started["verification_id"] in service._sessions
    finally:
        with service._lock:
            service._sessions.clear()
            service._sessions.update(original_sessions)


def test_otp_capacity_preserves_existing_valid_session(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_MODE", "sandbox")
    monkeypatch.setattr(service, "MAX_OTP_SESSIONS", 1)

    with service._lock:
        original_sessions = service._sessions.copy()
        service._sessions.clear()
        service._sessions["valid-test-session"] = {
            "phone_hash": "existing",
            "code_hash": "existing",
            "expires": service.time.time() + service.OTP_TTL_SECONDS,
            "attempts": 0,
            "verified": False,
        }

    try:
        with pytest.raises(RuntimeError, match="capacity reached"):
            service.start_sandbox_otp("+2348012345678")

        with service._lock:
            assert list(service._sessions) == ["valid-test-session"]
    finally:
        with service._lock:
            service._sessions.clear()
            service._sessions.update(original_sessions)




@pytest.fixture(autouse=True)
def isolate_otp_start_rate_limit_state():
    with service._lock:
        original = {
            key: values.copy()
            for key, values in service._otp_start_attempts.items()
        }
        service._otp_start_attempts.clear()

    try:
        yield
    finally:
        with service._lock:
            service._otp_start_attempts.clear()
            service._otp_start_attempts.update(original)


def test_otp_start_rate_limit_and_window_expiry(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_MODE", "sandbox")
    monkeypatch.setattr(service, "OTP_START_MAX_REQUESTS", 2)
    monkeypatch.setattr(service, "OTP_START_WINDOW_SECONDS", 60)

    clock = [1000.0]
    monkeypatch.setattr(service.time, "time", lambda: clock[0])

    with service._lock:
        old_sessions = service._sessions.copy()
        old_attempts = {
            key: values.copy()
            for key, values in service._otp_start_attempts.items()
        }
        service._sessions.clear()
        service._otp_start_attempts.clear()

    try:
        phone = "+2348012345678"
        service.start_sandbox_otp(phone)
        service.start_sandbox_otp(phone)

        with pytest.raises(service.OTPStartRateLimitError):
            service.start_sandbox_otp(phone)

        clock[0] += 61
        assert service.start_sandbox_otp(phone)["mode"] == "SANDBOX"
    finally:
        with service._lock:
            service._sessions.clear()
            service._sessions.update(old_sessions)
            service._otp_start_attempts.clear()
            service._otp_start_attempts.update(old_attempts)


def test_otp_start_rate_limit_stores_only_phone_hash(monkeypatch):
    monkeypatch.setenv("TRUSTNG_OTP_MODE", "sandbox")

    with service._lock:
        old_attempts = {
            key: values.copy()
            for key, values in service._otp_start_attempts.items()
        }
        service._otp_start_attempts.clear()

    try:
        phone = "+2348098765432"
        service.start_sandbox_otp(phone)
        phone_hash = service.hashlib.sha256(phone.encode()).hexdigest()

        with service._lock:
            assert phone_hash in service._otp_start_attempts
            assert phone not in service._otp_start_attempts
    finally:
        with service._lock:
            service._otp_start_attempts.clear()
            service._otp_start_attempts.update(old_attempts)
