import json

import pytest

import sms_delivery


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def configure_sandbox(monkeypatch):
    monkeypatch.setenv("SENDOZI_API_KEY", "sk_test_test-api-key")
    monkeypatch.setenv("SENDOZI_TRANSACTIONAL_SENDER", "TrustNG")
    monkeypatch.setenv("TRUSTNG_ENV", "sandbox")


def test_sendozi_accepts_sms_and_sends_idempotency_key(monkeypatch):
    configure_sandbox(monkeypatch)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({
            "success": True,
            "data": {"message_id": "test-message-id"},
        })

    monkeypatch.setattr(sms_delivery, "urlopen", fake_urlopen)

    result = sms_delivery.send_verification_sms(
        "+2348012345612", "654321", "stable-key"
    )

    assert result["accepted"] is True
    assert result["mode"] == "SENDOZI_SANDBOX"
    assert result["message_id"] == "test-message-id"
    assert captured["url"] == sms_delivery.SENDOZI_URL
    assert captured["timeout"] == 20
    assert captured["headers"]["authorization"] == "Bearer sk_test_test-api-key"
    assert captured["headers"]["idempotency-key"] == "stable-key"
    assert captured["body"]["sender"] == "TrustNG"
    assert captured["body"]["recipient"] == "+2348012345612"
    assert captured["body"]["route"] == "transactional"
    assert "654321" in captured["body"]["message"]


def test_sendozi_rejects_provider_failure(monkeypatch):
    configure_sandbox(monkeypatch)
    monkeypatch.setattr(
        sms_delivery,
        "urlopen",
        lambda *args, **kwargs: FakeResponse({"success": False}),
    )

    with pytest.raises(RuntimeError, match="did not accept"):
        sms_delivery.send_verification_sms(
            "+2348012345612", "654321", "stable-key"
        )


def test_sendozi_requires_credentials(monkeypatch):
    monkeypatch.delenv("SENDOZI_API_KEY", raising=False)
    monkeypatch.delenv("SENDOZI_TRANSACTIONAL_SENDER", raising=False)

    with pytest.raises(RuntimeError, match="credentials"):
        sms_delivery.send_verification_sms(
            "+2348012345612", "654321", "stable-key"
        )


def test_sendozi_production_requires_live_key(monkeypatch):
    monkeypatch.setenv("SENDOZI_API_KEY", "sk_test_test-api-key")
    monkeypatch.setenv("SENDOZI_TRANSACTIONAL_SENDER", "TrustNG")
    monkeypatch.setenv("TRUSTNG_ENV", "production")

    with pytest.raises(RuntimeError, match="live API key"):
        sms_delivery.send_verification_sms(
            "+2348012345612", "654321", "stable-key"
        )


def test_sendozi_rejects_missing_idempotency_key(monkeypatch):
    configure_sandbox(monkeypatch)

    with pytest.raises(RuntimeError, match="idempotency key"):
        sms_delivery.send_verification_sms(
            "+2348012345612", "654321", ""
        )


def test_sendozi_hides_network_error_details(monkeypatch):
    configure_sandbox(monkeypatch)

    def fail_request(*args, **kwargs):
        raise RuntimeError("private provider response")

    monkeypatch.setattr(sms_delivery, "urlopen", fail_request)

    with pytest.raises(RuntimeError, match="Sendozi SMS request failed") as error:
        sms_delivery.send_verification_sms(
            "+2348012345612", "654321", "stable-key"
        )

    assert "private provider response" not in str(error.value)
