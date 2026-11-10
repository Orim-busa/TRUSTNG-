import pytest
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)

VALID_ENQUIRY = {
    "full_name": "Test Partner",
    "business_email": "partner@example.org",
    "organisation": "Example Financial Group",
    "position": "Partnership Director",
    "phone": "+2348000000000",
    "country": "Nigeria",
    "partnership_type": "Strategic partnership",
    "purpose": "We would like to explore a strategic partnership.",
}


def test_partnership_enquiry_is_public_and_stored(monkeypatch):
    monkeypatch.delenv("TRUSTNG_API_KEY", raising=False)
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
