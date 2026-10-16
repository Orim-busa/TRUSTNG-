"""Read-only summary data for the TrustNG browser dashboard."""

from collections import Counter
from datetime import datetime, timezone

import architecture_benchmark
import continuous_intelligence
import research_analyzer
import research_collector


def _counts(records, field):
    return dict(sorted(Counter(
        item.get(field, "unknown") for item in records
    ).items()))


def dashboard_summary():
    """Build a dashboard summary from existing TrustNG records.

    This function does not collect feeds, write files, approve proposals,
    change risk decisions, or execute transactions.
    """
    candidates = research_collector.list_candidates()
    ranked = research_analyzer.rank_candidates(candidates)
    findings = continuous_intelligence.list_findings()
    proposals = continuous_intelligence.list_proposals()
    benchmarks = architecture_benchmark.list_benchmarks()
    sources = research_collector.source_catalog()

    priority_counts = _counts(ranked, "suggested_priority")

    latest_candidates = [
        {
            "candidate_id": item.get("candidate_id"),
            "title": item.get("title", ""),
            "source_name": item.get("source_name", ""),
            "source_region": item.get("source_region", ""),
            "discovered_at": item.get("discovered_at", ""),
            "review_status": item.get("review_status", "unreviewed"),
            "evidence_status": item.get("evidence_status", "not_verified"),
        }
        for item in candidates[:5]
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": {
            "name": "TrustNG",
            "dashboard_data_status": "available",
            "mode": "read_only",
            "automatic_production_changes": False,
            "automatic_financial_execution": False,
            "human_review_required": True,
        },
        "research": {
            "candidate_total": len(candidates),
            "candidate_review_status": _counts(
                candidates, "review_status"
            ),
            "candidate_evidence_status": _counts(
                candidates, "evidence_status"
            ),
            "unreviewed_ranked_candidates": len(ranked),
            "suggested_priority_counts": {
                "high": priority_counts.get("high", 0),
                "medium": priority_counts.get("medium", 0),
                "low": priority_counts.get("low", 0),
            },
            "ranking_is_independent_verification": False,
            "latest_candidates": latest_candidates,
        },
        "findings": {
            "total": len(findings),
            "verification_status": _counts(
                findings, "verification_status"
            ),
        },
        "proposals": {
            "total": len(proposals),
            "status_counts": _counts(proposals, "status"),
            "production_changes_authorized": sum(
                item.get("production_changes_authorized") is True
                for item in proposals
            ),
        },
        "architecture_benchmarks": {
            "total": len(benchmarks),
            "status_counts": _counts(benchmarks, "status"),
            "production_changes_authorized": sum(
                item.get("production_changes_authorized") is True
                for item in benchmarks
            ),
        },
        "sources": {
            "catalogue_total": len(sources),
            "collection_enabled": sum(
                item.get("collection_enabled") is True
                for item in sources
            ),
            "reference_only": sum(
                item.get("collection_enabled") is False
                for item in sources
            ),
        },
        "currency_and_economic_indicators": {
            "status": "not_configured",
            "message": (
                "Verified currency and economic data feeds have not "
                "been connected to the dashboard yet."
            ),
        },
    }
