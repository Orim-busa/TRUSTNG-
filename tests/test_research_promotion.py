import pytest

import continuous_intelligence as ci
import research_collector as rc
import research_promotion as promotion


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rc, "CANDIDATES_FILE", tmp_path / "candidates.json")
    monkeypatch.setattr(ci, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ci, "FINDINGS_FILE", tmp_path / "findings.json")
    monkeypatch.setattr(ci, "PROPOSALS_FILE", tmp_path / "proposals.json")


def add_candidate(evidence_status="independently_verified",
                  review_status="reviewed"):
    candidate = {
        "candidate_id": "candidate-1",
        "discovered_at": "2026-10-14T00:00:00+00:00",
        "source_name": "Trusted research source",
        "source_feed": "https://www.bis.org/research.rss",
        "source_region": "international",
        "topic": "payment security",
        "title": "Payment security research",
        "summary": "Research summary for human evaluation.",
        "article_url": "https://www.bis.org/research/example",
        "published_at_source": "2026-10-10",
        "review_status": review_status,
        "evidence_status": evidence_status,
        "trustng_relevance": 5,
        "lesson_for_africa": "Evaluate against regional payment systems.",
    }
    rc._write_candidates([candidate])
    return candidate


def test_verified_reviewed_candidate_becomes_finding(isolated_stores):
    candidate = add_candidate()

    result = promotion.promote_candidate(candidate["candidate_id"])

    findings = ci.list_findings()
    assert len(findings) == 1
    assert findings[0]["source_url"] == candidate["article_url"]
    assert result["proposal_created"] is False
    assert result["production_changes_authorized"] is False


@pytest.mark.parametrize(
    "evidence_status",
    ["not_verified", "partially_verified", "rejected"],
)
def test_unverified_or_rejected_candidate_is_blocked(
    isolated_stores, evidence_status
):
    candidate = add_candidate(evidence_status=evidence_status)

    with pytest.raises(ValueError):
        promotion.promote_candidate(candidate["candidate_id"])

    assert ci.list_findings() == []


def test_unreviewed_candidate_is_blocked(isolated_stores):
    candidate = add_candidate(review_status="unreviewed")

    with pytest.raises(ValueError):
        promotion.promote_candidate(candidate["candidate_id"])

    assert ci.list_findings() == []


def test_duplicate_source_promotion_is_blocked(isolated_stores):
    candidate = add_candidate()
    promotion.promote_candidate(candidate["candidate_id"])

    with pytest.raises(ValueError, match="already been promoted"):
        promotion.promote_candidate(candidate["candidate_id"])

    assert len(ci.list_findings()) == 1


def test_missing_candidate_is_blocked(isolated_stores):
    with pytest.raises(ValueError, match="Unknown research candidate"):
        promotion.promote_candidate("does-not-exist")
