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
