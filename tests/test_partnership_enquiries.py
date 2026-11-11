import pytest
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)

VALID_ENQUIRY = {
    "cf-turnstile-response": "test-turnstile-token",
    "full_name": "Test Partner",
    "business_email": "partner@example.org",
    "organisation": "Example Financial Group",
    "position": "Partnership Director",
    "phone": "+2348000000000",
    "country": "Nigeria",
    "partnership_type": "Strategic partnership",
    "purpose": "We would like to explore a strategic partnership.",
}


@pytest.fixture(autouse=True)
def configure_partnership_rate_limit(monkeypatch):
    monkeypatch.setenv(
        "PARTNERSHIP_RATE_LIMIT_SECRET",
        "test-partnership-rate-limit-secret",
    )
    monkeypatch.setattr(
        main.database,
        "consume_partnership_rate_limit",
        lambda identifier_hash: True,
    )


def test_partnership_enquiry_is_public_and_stored(monkeypatch):
    monkeypatch.delenv("TRUSTNG_API_KEY", raising=False)

    async def accept_turnstile(token):
        assert token == "test-turnstile-token"
        return True

    monkeypatch.setattr(main, "verify_turnstile_token", accept_turnstile)
    saved = {}

    def fake_save(**kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(
        main.database,
        "create_partnership_enquiry",
        fake_save,
    )

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 201
    assert response.json()["success"] is True
    assert response.json()["reference"].startswith("DJ-")
    assert saved["business_email"] == "partner@example.org"
    assert saved["organisation"] == "Example Financial Group"


def test_partnership_enquiry_uses_hmac_identifier_for_rate_limit(monkeypatch):
    import hashlib
    import hmac

    captured = {}

    async def accept_turnstile(token):
        return True

    def allow_rate_limit(identifier_hash):
        captured["identifier_hash"] = identifier_hash
        return True

    monkeypatch.setattr(main, "verify_turnstile_token", accept_turnstile)
    monkeypatch.setattr(
        main.database,
        "consume_partnership_rate_limit",
        allow_rate_limit,
    )
    monkeypatch.setattr(
        main.database,
        "create_partnership_enquiry",
        lambda **kwargs: None,
    )

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    expected = hmac.new(
        b"test-partnership-rate-limit-secret",
        b"partner@example.org",
        hashlib.sha256,
    ).hexdigest()

    assert response.status_code == 201
    assert captured["identifier_hash"] == expected
    assert captured["identifier_hash"] != "partner@example.org"


def test_partnership_enquiry_rejects_rate_limited_email(monkeypatch):
    async def accept_turnstile(token):
        return True

    monkeypatch.setattr(main, "verify_turnstile_token", accept_turnstile)
    monkeypatch.setattr(
        main.database,
        "consume_partnership_rate_limit",
        lambda identifier_hash: False,
    )

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 429
    assert "too many enquiries" in response.json()["detail"].lower()


def test_partnership_enquiry_fails_closed_when_rate_limit_secret_is_missing(
    monkeypatch,
):
    async def accept_turnstile(token):
        return True

    monkeypatch.setattr(main, "verify_turnstile_token", accept_turnstile)
    monkeypatch.delenv("PARTNERSHIP_RATE_LIMIT_SECRET", raising=False)

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 503


def test_partnership_enquiry_fails_closed_when_rate_limit_database_fails(
    monkeypatch,
):
    async def accept_turnstile(token):
        return True

    def fail_rate_limit(identifier_hash):
        raise RuntimeError("simulated rate-limit database failure")

    monkeypatch.setattr(main, "verify_turnstile_token", accept_turnstile)
    monkeypatch.setattr(
        main.database,
        "consume_partnership_rate_limit",
        fail_rate_limit,
    )

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 503
    assert "simulated rate-limit database failure" not in response.text


def test_partnership_enquiry_rejects_oversized_declared_body():
    body = b" " * (16 * 1024 + 1)

    response = client.post(
        "/v1/partnership-enquiries",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_partnership_enquiry_rejects_oversized_chunked_body_without_content_length():
    body = b'{"purpose":"' + b"x" * (16 * 1024) + b'"}'

    request = client.build_request(
        "POST",
        "/v1/partnership-enquiries",
        content=iter([body]),
        headers={"Content-Type": "application/json"},
    )

    assert "content-length" not in request.headers

    response = client.send(request)

    assert response.status_code == 413


def test_partnership_enquiry_rejects_malformed_json():
    response = client.post(
        "/v1/partnership-enquiries",
        content=b'{"full_name":',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_partnership_enquiry_rejects_non_object_json():
    response = client.post(
        "/v1/partnership-enquiries",
        json=["not", "an", "object"],
    )

    assert response.status_code == 400


def test_partnership_enquiry_rejects_missing_required_field():
    payload = {**VALID_ENQUIRY, "organisation": ""}

    response = client.post("/v1/partnership-enquiries", json=payload)

    assert response.status_code == 422


def test_partnership_enquiry_rejects_invalid_email():
    payload = {**VALID_ENQUIRY, "business_email": "not-an-email"}

    response = client.post("/v1/partnership-enquiries", json=payload)

    assert response.status_code == 422


def test_other_partnership_requires_explanation():
    payload = {
        **VALID_ENQUIRY,
        "partnership_type": "Other",
        "other_interest": "",
    }

    response = client.post("/v1/partnership-enquiries", json=payload)

    assert response.status_code == 422


def test_partnership_enquiry_rejects_unknown_partnership_type():
    payload = {**VALID_ENQUIRY, "partnership_type": "Send money"}

    response = client.post("/v1/partnership-enquiries", json=payload)

    assert response.status_code == 422


def test_partnership_enquiry_does_not_claim_success_when_database_fails(
    monkeypatch,
):
    import psycopg

    async def accept_turnstile(token):
        return True

    monkeypatch.setattr(main, "verify_turnstile_token", accept_turnstile)

    def fail_save(**kwargs):
        raise psycopg.OperationalError("simulated database failure")

    monkeypatch.setattr(
        main.database,
        "create_partnership_enquiry",
        fail_save,
    )

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 503
    assert "simulated database failure" not in response.text


def test_partnership_enquiry_rejects_honeypot_submission():
    payload = {**VALID_ENQUIRY, "website": "spam"}

    response = client.post("/v1/partnership-enquiries", json=payload)

    assert response.status_code == 400


def test_partnership_enquiry_is_documented_as_public():
    schema = main.app.openapi()
    operation = schema["paths"]["/v1/partnership-enquiries"]["post"]

    assert operation["security"] == []


def test_admin_partnership_enquiries_requires_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-partnership-secret")

    response = client.get("/v1/admin/partnership-enquiries")

    assert response.status_code == 401


def test_admin_partnership_enquiries_returns_records_with_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-partnership-secret")
    expected = [{
        "reference": "DJ-TEST123456",
        "full_name": "Test Partner",
        "business_email": "partner@example.org",
        "organisation": "Example Financial Group",
        "position": None,
        "phone": None,
        "country": "Nigeria",
        "partnership_type": "Strategic partnership",
        "other_interest": None,
        "purpose": "Discuss a partnership.",
        "created_at": "2026-11-10T12:00:00+00:00",
    }]
    monkeypatch.setattr(
        main.database,
        "list_recent_partnership_enquiries",
        lambda limit=50: expected,
    )

    response = client.get(
        "/v1/admin/partnership-enquiries",
        headers={"X-API-Key": "test-partnership-secret"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"] == expected


def test_admin_partnership_enquiries_rejects_invalid_limit(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "test-partnership-secret")

    response = client.get(
        "/v1/admin/partnership-enquiries?limit=101",
        headers={"X-API-Key": "test-partnership-secret"},
    )

    assert response.status_code == 400


def test_partnership_enquiry_rejects_missing_turnstile_token(monkeypatch):
    payload = {**VALID_ENQUIRY}
    payload.pop("cf-turnstile-response")

    response = client.post("/v1/partnership-enquiries", json=payload)

    assert response.status_code == 400
    assert "security verification" in response.json()["detail"].lower()


def test_partnership_enquiry_rejects_invalid_turnstile_token(monkeypatch):
    async def reject_turnstile(token):
        return False

    monkeypatch.setattr(main, "verify_turnstile_token", reject_turnstile)

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 400
    assert "verification failed" in response.json()["detail"].lower()


def test_partnership_enquiry_fails_closed_when_turnstile_is_unavailable(
    monkeypatch,
):
    async def unavailable_turnstile(token):
        raise RuntimeError("verification unavailable")

    monkeypatch.setattr(main, "verify_turnstile_token", unavailable_turnstile)

    response = client.post("/v1/partnership-enquiries", json=VALID_ENQUIRY)

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"].lower()


def test_turnstile_verifier_posts_secret_and_token(monkeypatch):
    import asyncio

    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("TURNSTILE_EXPECTED_HOSTNAME", "dijuang.com")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "action": "partnership_enquiry",
                "hostname": "dijuang.com",
            }

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def post(self, url, data):
            captured["url"] = url
            captured["data"] = data
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(main.verify_turnstile_token("sample-token"))

    assert result is True
    assert captured["url"] == (
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    assert captured["data"]["secret"] == "test-secret"
    assert captured["data"]["response"] == "sample-token"
    assert captured["data"]["idempotency_key"]
    import uuid
    uuid.UUID(captured["data"]["idempotency_key"])
    assert captured["timeout"] == 5.0



@pytest.mark.parametrize(
    "siteverify_result",
    [
        {
            "success": True,
            "action": "another_action",
            "hostname": "dijuang.com",
        },
        {
            "success": True,
            "action": "partnership_enquiry",
            "hostname": "attacker.example",
        },
    ],
)
def test_turnstile_verifier_rejects_wrong_action_or_hostname(
    monkeypatch, siteverify_result
):
    import asyncio

    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("TURNSTILE_EXPECTED_HOSTNAME", "dijuang.com")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return siteverify_result

    class FakeAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def post(self, url, data):
            return FakeResponse()

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    assert asyncio.run(main.verify_turnstile_token("sample-token")) is False


def test_turnstile_verifier_fails_when_expected_hostname_is_missing(monkeypatch):
    import asyncio

    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.delenv("TURNSTILE_EXPECTED_HOSTNAME", raising=False)

    with pytest.raises(RuntimeError, match="not configured"):
        asyncio.run(main.verify_turnstile_token("sample-token"))

def test_turnstile_verifier_fails_when_secret_is_missing(monkeypatch):
    import asyncio

    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="not configured"):
        asyncio.run(main.verify_turnstile_token("sample-token"))


def test_turnstile_verifier_fails_closed_on_http_error(monkeypatch):
    import asyncio

    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("TURNSTILE_EXPECTED_HOSTNAME", "dijuang.com")

    class FakeAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            return False

        async def post(self, url, data):
            raise main.httpx.ConnectError("simulated outage")

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(main.verify_turnstile_token("sample-token"))
