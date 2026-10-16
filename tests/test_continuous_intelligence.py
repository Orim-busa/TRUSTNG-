import json

import pytest

import continuous_intelligence as ci


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ci, "FINDINGS_FILE", tmp_path / "findings.json")
    monkeypatch.setattr(ci, "PROPOSALS_FILE", tmp_path / "proposals.json")


def add_finding(region="international"):
    return ci.record_finding(
        title="Example payment security lesson",
        summary="A documented approach worth evaluating.",
        source_name="Example research source",
        source_url="https://example.com/research",
        source_region=region,
        source_type="technical_paper",
        evidence_strength="strong",
        relevance_to_trustng=5,
        limitations="Applicability to African payment systems needs testing.",
        lesson_for_africa="Validate the approach against local payment rails.",
    )


def add_proposal(finding):
    return ci.create_proposal(
        title="Evaluate stronger transaction monitoring",
        problem="Existing monitoring may miss emerging patterns.",
        proposed_change="Run a controlled evaluation of an improved detector.",
        expected_benefits="Potentially earlier detection of suspicious activity.",
        disadvantages_and_risks="False positives and operational costs.",
        estimated_cost="Needs a measured cost estimate before implementation.",
        dependencies="Representative test data and an isolated test environment.",
        security_and_privacy_impact="Use minimized and protected test data.",
        testing_plan="Compare against a baseline using held-out test cases.",
        implementation_steps="Prototype, test, review results, then decide.",
        rollback_plan="Keep the existing detector and revert the isolated change.",
        finding_ids=[finding["finding_id"]],
        expected_impact=4,
    )


def test_record_and_filter_findings(isolated_store):
    international = add_finding()
    african = add_finding("africa")

    assert len(ci.list_findings()) == 2
    assert ci.list_findings("international")[0]["finding_id"] == (
        international["finding_id"]
    )
    assert ci.list_findings("africa")[0]["finding_id"] == (
        african["finding_id"]
    )


def test_reject_invalid_source_url(isolated_store):
    with pytest.raises(ValueError):
        ci.record_finding(
            title="Bad source",
            summary="Example",
            source_name="Unknown",
            source_url="not-a-url",
            source_region="international",
            source_type="article",
            evidence_strength="low",
            relevance_to_trustng=1,
            limitations="Not verified",
            lesson_for_africa="Needs investigation",
        )


def test_proposal_requires_existing_finding(isolated_store):
    with pytest.raises(ValueError):
        ci.create_proposal(
            title="Proposal",
            problem="Problem",
            proposed_change="Change",
            expected_benefits="Benefits",
            disadvantages_and_risks="Risks",
            estimated_cost="Unknown",
            dependencies="None known",
            security_and_privacy_impact="Needs review",
            testing_plan="Test first",
            implementation_steps="Review first",
            rollback_plan="Revert change",
            finding_ids=["does-not-exist"],
            expected_impact=3,
        )


def test_human_review_does_not_enable_production_changes(isolated_store):
    finding = add_finding()
    proposal = add_proposal(finding)

    reviewed = ci.review_proposal(
        proposal["proposal_id"],
        decision="approved",
        notes="Approved for controlled evaluation only.",
        reviewer="human-reviewer",
    )

    assert reviewed["status"] == "approved"
    assert reviewed["production_changes_authorized"] is False


def test_testing_requires_approval(isolated_store):
    finding = add_finding()
    proposal = add_proposal(finding)

    with pytest.raises(ValueError):
        ci.record_test_result(
            proposal["proposal_id"],
            summary="Test run",
            passed=True,
            evidence="Test report",
        )


def test_failed_tests_cannot_be_recorded_as_implementation(isolated_store):
    finding = add_finding()
    proposal = add_proposal(finding)

    ci.review_proposal(
        proposal["proposal_id"],
        decision="approved",
        notes="Approved for isolated testing.",
        reviewer="human-reviewer",
    )

    ci.record_test_result(
        proposal["proposal_id"],
        summary="Baseline comparison failed.",
        passed=False,
        evidence="Evaluation report",
    )

    with pytest.raises(ValueError):
        ci.record_implementation_outcome(
            proposal["proposal_id"],
            outcome="Should not be recorded",
            evidence="No passing test",
        )


def test_policy_prioritizes_international_research(isolated_store):
    policy = ci.research_policy()

    assert policy["international_research_target_percent"] == 80
    assert policy["african_research_target_percent"] == 20
    assert policy["autonomous_production_changes"] is False
    assert policy["automated_external_research_enabled"] is False


def test_stores_records_as_json(isolated_store):
    finding = add_finding()

    stored = json.loads(ci.FINDINGS_FILE.read_text(encoding="utf-8"))

    assert stored[0]["finding_id"] == finding["finding_id"]
