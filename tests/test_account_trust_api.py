from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
KEY = {"X-API-Key": "account-trust-test-key"}


def test_account_trust_routes_require_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "account-trust-test-key")
    response = client.post(
        "/v1/account-trust/check",
        json={"country": "NG", "account_identifier": "0123456789",
              "phone_number": "+2348012345678"},
    )
    assert response.status_code == 401


def test_account_trust_check_is_advisory(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "account-trust-test-key")
    response = client.post(
        "/v1/account-trust/check",
        headers=KEY,
        json={"country": "NG", "account_identifier": "0123456789",
              "phone_number": "+2348012345678"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["account_age_status"] == "UNAVAILABLE"
    assert result["risk_level"] == "UNKNOWN"
    assert result["transfer_authorized"] is False
    assert "0123456789" not in response.text


def test_sandbox_otp_flow_is_bound_to_phone_and_one_check(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "account-trust-test-key")
    phone = "+2348012345678"
    start = client.post(
        "/v1/account-trust/otp/start",
        headers=KEY,
        json={"phone_number": phone},
    )
    assert start.status_code == 200
    issued = start.json()
    assert issued["mode"] == "SANDBOX"
    assert "No SMS was sent" in issued["message"]

    verify = client.post(
        "/v1/account-trust/otp/verify",
        headers=KEY,
        json={"verification_id": issued["verification_id"],
              "code": issued["sandbox_code"]},
    )
    assert verify.status_code == 200
    assert verify.json()["verified"] is True

    check = client.post(
        "/v1/account-trust/check",
        headers=KEY,
        json={"country": "NG", "account_identifier": "0123456789",
              "phone_number": phone,
              "verification_id": issued["verification_id"]},
    )
    assert check.status_code == 200
    assert check.json()["phone_verification"] == "SANDBOX_VERIFIED"

    replay = client.post(
        "/v1/account-trust/check",
        headers=KEY,
        json={"country": "NG", "account_identifier": "0123456789",
              "phone_number": phone,
              "verification_id": issued["verification_id"]},
    )
    assert replay.status_code == 400


def test_otp_cannot_be_used_with_a_different_phone(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "account-trust-test-key")
    start = client.post(
        "/v1/account-trust/otp/start",
        headers=KEY,
        json={"phone_number": "+2348012345678"},
    ).json()
    verify = client.post(
        "/v1/account-trust/otp/verify",
        headers=KEY,
        json={"verification_id": start["verification_id"],
              "code": start["sandbox_code"]},
    )
    assert verify.status_code == 200

    check = client.post(
        "/v1/account-trust/check",
        headers=KEY,
        json={"country": "NG", "account_identifier": "0123456789",
              "phone_number": "+2348099999999",
              "verification_id": start["verification_id"]},
    )
    assert check.status_code == 400
