import dashboard_service


def test_dashboard_summary_uses_existing_records(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.research_collector,
        "list_candidates",
        lambda: [
            {
                "candidate_id": "candidate-1",
                "title": "Payment security",
                "source_name": "Example regulator",
                "source_region": "international",
                "discovered_at": "2026-10-14T10:00:00Z",
                "review_status": "unreviewed",
                "evidence_status": "not_verified",
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_service.research_analyzer,
        "rank_candidates",
        lambda candidates: [
            {
                "candidate_id": "candidate-1",
                "suggested_priority": "high",
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_service.continuous_intelligence,
        "list_findings",
        lambda: [],
    )
    monkeypatch.setattr(
        dashboard_service.continuous_intelligence,
        "list_proposals",
        lambda: [],
    )
    monkeypatch.setattr(
        dashboard_service.architecture_benchmark,
        "list_benchmarks",
        lambda: [],
    )
    monkeypatch.setattr(
        dashboard_service.research_collector,
        "source_catalog",
        lambda: [
            {"collection_enabled": True},
            {"collection_enabled": False},
        ],
    )

    result = dashboard_service.dashboard_summary()

    assert result["research"]["candidate_total"] == 1
    assert result["research"]["suggested_priority_counts"]["high"] == 1
    assert result["research"]["ranking_is_independent_verification"] is False
    assert result["findings"]["total"] == 0
    assert result["proposals"]["total"] == 0
    assert result["architecture_benchmarks"]["total"] == 0
    assert result["sources"]["collection_enabled"] == 1
    assert result["currency_and_economic_indicators"]["status"] == "not_configured"


def test_dashboard_summary_marks_controls_as_read_only(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.research_collector, "list_candidates", lambda: []
    )
    monkeypatch.setattr(
        dashboard_service.research_analyzer, "rank_candidates", lambda candidates: []
    )
    monkeypatch.setattr(
        dashboard_service.continuous_intelligence, "list_findings", lambda: []
    )
    monkeypatch.setattr(
        dashboard_service.continuous_intelligence, "list_proposals", lambda: []
    )
    monkeypatch.setattr(
        dashboard_service.architecture_benchmark, "list_benchmarks", lambda: []
    )
    monkeypatch.setattr(
        dashboard_service.research_collector, "source_catalog", lambda: []
    )

    result = dashboard_service.dashboard_summary()

    assert result["system"]["mode"] == "read_only"
    assert result["system"]["automatic_production_changes"] is False
    assert result["system"]["automatic_financial_execution"] is False
    assert result["system"]["human_review_required"] is True
