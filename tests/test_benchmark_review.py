import json

import pytest

import benchmark_review as br


def make_report(path):
    path.write_text(
        json.dumps({
            "findings": [{
                "finding_id": "AB-TEST-001",
                "domain": "api_security",
            }]
        }),
        encoding="utf-8",
    )


def test_record_review_writes_verifiable_checkpoint(tmp_path):
    report = tmp_path / "report.json"
    reviews = tmp_path / "reviews.json"
    make_report(report)

    record = br.record_review(
        finding_id="AB-TEST-001",
        reviewer="Test reviewer",
        decision="PENDING",
        notes="Isolated checkpoint test.",
        report_path=report,
        reviews_path=reviews,
        aliases_path=tmp_path / "aliases.json",
    )

    stored = json.loads(reviews.read_text(encoding="utf-8"))
    result = br.review_integrity_report(
        reviews_path=reviews,
        checkpoint_path=tmp_path / "architecture_benchmark_review_checkpoint.json",
    )

    assert stored[0]["review_id"] == record["review_id"]
    assert stored[0]["payment_authorized"] is False
    assert stored[0]["funds_moved"] is False
    assert result["checkpoint_verified"] is True
    assert result["tamper_evident"] is True


def test_checkpoint_failure_preserves_saved_review_and_reports_failure(
    tmp_path, monkeypatch
):
    report = tmp_path / "report.json"
    reviews = tmp_path / "reviews.json"
    make_report(report)

    def fail_checkpoint(*args, **kwargs):
        raise OSError("simulated checkpoint write failure")

    monkeypatch.setattr(br, "_write_review_checkpoint", fail_checkpoint)

    with pytest.raises(RuntimeError, match="was saved, but checkpoint creation failed"):
        br.record_review(
            finding_id="AB-TEST-001",
            reviewer="Test reviewer",
            decision="PENDING",
            notes="Isolated checkpoint failure test.",
            report_path=report,
            reviews_path=reviews,
            aliases_path=tmp_path / "aliases.json",
        )

    stored = json.loads(reviews.read_text(encoding="utf-8"))
    assert len(stored) == 1
    assert stored[0]["payment_authorized"] is False
    assert stored[0]["funds_moved"] is False

    result = br.review_integrity_report(
        reviews_path=reviews,
        checkpoint_path=tmp_path / "architecture_benchmark_review_checkpoint.json",
    )
    assert result["checkpoint_verified"] is False
    assert result["tamper_evident"] is False
def test_duplicate_review_id_cannot_be_reported_as_tamper_evident(tmp_path):
    report = tmp_path / "report.json"
    reviews = tmp_path / "reviews.json"
    checkpoint = tmp_path / "architecture_benchmark_review_checkpoint.json"
    make_report(report)

    br.record_review(
        finding_id="AB-TEST-001",
        reviewer="Test reviewer",
        decision="PENDING",
        notes="First review.",
        report_path=report,
        reviews_path=reviews,
        aliases_path=tmp_path / "aliases.json",
    )

    records = json.loads(reviews.read_text(encoding="utf-8"))
    duplicate = dict(records[0])
    duplicate["previous_record_hash"] = records[0]["record_hash"]
    duplicate["record_hash"] = br._canonical_review_hash(duplicate)
    records.append(duplicate)

    reviews.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    br._write_review_checkpoint(reviews, records)

    result = br.review_integrity_report(
        reviews_path=reviews,
        checkpoint_path=checkpoint,
    )

    assert result["structural_checks_passed"] is False
    assert result["hashes_valid"] is True
    assert result["chain_links_valid"] is True
    assert result["checkpoint_verified"] is True
    assert result["hash_chain_checks_passed"] is False
    assert result["tamper_evident"] is False
