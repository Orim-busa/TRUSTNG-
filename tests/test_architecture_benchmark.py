import pytest

import architecture_benchmark as ab


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(ab, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ab, "BENCHMARKS_FILE", tmp_path / "benchmarks.json")


def make_benchmark(**overrides):
    values = {
        "source_name": "Saudi Central Bank - Open Banking",
        "capability_id": "developer_conformance",
        "source_url": "https://openbanking.sama.gov.sa/index-en.html",
        "source_observation": "Documented sandbox and conformance testing.",
        "trustng_current_state": "TrustNG has API tests but no external conformance suite.",
        "identified_gap": "No reusable conformance test pack.",
        "proposed_adaptation": "Build a simulated participant conformance suite.",
        "risks": "Incomplete tests could create false confidence.",
        "cost_estimate": "Initial engineering and maintenance time.",
        "dependencies": "Test client, API schemas, isolated test environment.",
        "validation_plan": "Run positive, negative, and regression tests.",
        "rollback_plan": "Remove the isolated test module without changing production.",
    }
    values.update(overrides)
    return ab.create_benchmark(**values)


def test_capability_catalog_is_populated():
    ids = {item["capability_id"] for item in ab.capability_catalog()}
    assert "api_security" in ids
    assert "transaction_risk" in ids
    assert "ai_governance" in ids


def test_create_benchmark_starts_as_unverified_draft(isolated_store):
    item = make_benchmark()
    assert item["status"] == "draft"
    assert item["evidence_status"] == "requires_independent_verification"
    assert item["production_changes_authorized"] is False
    assert ab.list_benchmarks()[0]["benchmark_id"] == item["benchmark_id"]


def test_unknown_source_is_rejected(isolated_store):
    with pytest.raises(ValueError, match="approved source catalogue"):
        make_benchmark(source_name="Unknown source")


def test_non_catalogue_url_is_rejected(isolated_store):
    with pytest.raises(ValueError, match="exact HTTPS URL"):
        make_benchmark(source_url="https://attacker.example/research")


def test_unknown_capability_is_rejected(isolated_store):
    with pytest.raises(ValueError, match="Unknown capability"):
        make_benchmark(capability_id="invented_capability")


def test_cannot_record_tests_before_human_approval(isolated_store):
    item = make_benchmark()
    with pytest.raises(ValueError, match="Human approval"):
        ab.record_test_result(
            item["benchmark_id"], "Test run", True, "local pytest"
        )


def test_review_allows_testing_but_not_production(isolated_store):
    item = make_benchmark()
    reviewed = ab.review_benchmark(
        item["benchmark_id"],
        "approved_for_testing",
        "human reviewer",
        "Proceed only in an isolated test environment.",
    )
    assert reviewed["status"] == "approved_for_testing"
    assert reviewed["production_changes_authorized"] is False


def test_test_results_require_approval_and_remain_nonproduction(isolated_store):
    item = make_benchmark()
    ab.review_benchmark(
        item["benchmark_id"],
        "approved_for_testing",
        "human reviewer",
        "Approved for isolated tests.",
    )
    result = ab.record_test_result(
        item["benchmark_id"],
        "Regression suite passed.",
        True,
        "pytest output stored in test report",
    )
    assert result["test_results"][-1]["passed"] is True
    assert result["production_changes_authorized"] is False


def test_review_requires_reviewer_and_notes(isolated_store):
    item = make_benchmark()
    with pytest.raises(ValueError, match="reviewer identity"):
        ab.review_benchmark(item["benchmark_id"], "rejected", "", "Not suitable")


def test_policy_never_authorizes_automatic_production_changes():
    policy = ab.benchmark_policy()
    assert policy["automatic_code_changes"] is False
    assert policy["automatic_production_deployment"] is False
    assert policy["testing_approval_authorizes_production"] is False
