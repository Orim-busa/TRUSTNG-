from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_dashboard_summary_requires_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    response = client.get("/v1/dashboard/summary")
    assert response.status_code == 401


def test_dashboard_summary_accepts_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    response = client.get(
        "/v1/dashboard/summary",
        headers={"X-API-Key": "dashboard-test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["system"]["mode"] == "read_only"
    assert "research" in data
    assert "currency_and_economic_indicators" in data


def test_dashboard_research_is_protected(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    response = client.get(
        "/v1/dashboard/research",
        headers={"X-API-Key": "dashboard-test-key"},
    )
    assert response.status_code == 200
    assert "items" in response.json()
    assert response.json()["ranking_is_independent_verification"] is False


def test_dashboard_research_rejects_invalid_limit(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    response = client.get(
        "/v1/dashboard/research?limit=500",
        headers={"X-API-Key": "dashboard-test-key"},
    )
    assert response.status_code == 400


def test_dashboard_proposals_and_benchmarks_are_protected(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")

    for path in (
        "/v1/dashboard/proposals",
        "/v1/dashboard/benchmarks",
    ):
        response = client.get(
            path,
            headers={"X-API-Key": "dashboard-test-key"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)



def test_research_candidate_review_endpoint(monkeypatch):
    import research_collector as rc

    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    monkeypatch.setattr(rc, "DATA_DIR", __import__("pathlib").Path("/tmp/trustng-review-api-test"))
    monkeypatch.setattr(
        rc,
        "CANDIDATES_FILE",
        __import__("pathlib").Path("/tmp/trustng-review-api-test/candidates.json"),
    )
    rc._write_candidates([{
        "candidate_id": "api-review-test",
        "discovered_at": "2026-10-15T00:00:00+00:00",
        "source_name": "Test source",
        "source_feed": "https://example.org/feed",
        "source_region": "international",
        "topic": "security",
        "title": "Review API test",
        "summary": "A test candidate",
        "article_url": "https://example.org/article",
        "published_at_source": "",
        "review_status": "unreviewed",
        "evidence_status": "not_verified",
        "lesson_for_africa": None,
        "trustng_relevance": None,
    }])

    response = client.post(
        "/v1/research/candidates/api-review-test/review",
        headers={"X-API-Key": "dashboard-test-key"},
        json={
            "reviewer": "Test reviewer",
            "notes": "Checked the source and supporting evidence.",
            "evidence_status": "partially_verified",
            "trustng_relevance": 4,
            "lesson_for_africa": "Assess relevance to local payment systems.",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["review_status"] == "reviewed"
    assert result["review"]["reviewer"] == "Test reviewer"
    assert result["review"]["notes"] == "Checked the source and supporting evidence."
    assert result["review"]["decision"] == "partially_verified"
    assert result["review"]["reviewed_at"]


def test_research_candidate_review_requires_api_key(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    response = client.post(
        "/v1/research/candidates/missing/review",
        json={
            "reviewer": "Test reviewer",
            "notes": "Test notes",
            "evidence_status": "not_verified",
            "trustng_relevance": 3,
            "lesson_for_africa": "Test lesson.",
        },
    )
    assert response.status_code == 401


def test_research_candidate_review_rejects_invalid_payload(monkeypatch):
    monkeypatch.setenv("TRUSTNG_API_KEY", "dashboard-test-key")
    response = client.post(
        "/v1/research/candidates/missing/review",
        headers={"X-API-Key": "dashboard-test-key"},
        json={
            "reviewer": "",
            "notes": "Test notes",
            "evidence_status": "unknown",
            "trustng_relevance": 9,
            "lesson_for_africa": "Test lesson.",
        },
    )
    assert response.status_code == 422
