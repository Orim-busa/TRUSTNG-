"""Controlled promotion of reviewed research into TrustNG findings."""

import research_collector
import continuous_intelligence


def promote_candidate(candidate_id):
    """Promote independently verified research into the findings store."""

    candidates = research_collector.list_candidates()
    candidate = next(
        (
            item for item in candidates
            if item["candidate_id"] == candidate_id
        ),
        None,
    )

    if candidate is None:
        raise ValueError("Unknown research candidate.")

    if candidate.get("review_status") != "reviewed":
        raise ValueError("Candidate must receive human review first.")

    if candidate.get("evidence_status") != "independently_verified":
        raise ValueError(
            "Only independently verified candidates can be promoted."
        )

    if not candidate.get("trustng_relevance"):
        raise ValueError("Candidate is missing its TrustNG relevance rating.")

    if not candidate.get("lesson_for_africa"):
        raise ValueError("Candidate is missing its recorded lesson.")

    existing = continuous_intelligence.list_findings()
    source_url = candidate["article_url"]

    if any(
        finding.get("source_url") == source_url
        for finding in existing
    ):
        raise ValueError("This source URL has already been promoted.")

    summary = candidate.get("summary", "").strip()
    if not summary:
        summary = (
            "The source was independently reviewed. Read the original "
            "material and document the specific evidence before relying "
            "on its claims."
        )

    finding = continuous_intelligence.record_finding(
        title=candidate["title"],
        summary=summary,
        source_name=candidate["source_name"],
        source_url=source_url,
        source_region=candidate["source_region"],
        source_type="externally_collected_research",
        evidence_strength="moderate",
        relevance_to_trustng=candidate["trustng_relevance"],
        limitations=(
            "Human review is recorded, but relevance and conclusions "
            "must still be assessed in TrustNG's context. Verify the "
            "source contents and applicability before making decisions."
        ),
        lesson_for_africa=candidate["lesson_for_africa"],
    )

    return {
        "finding_id": finding["finding_id"],
        "candidate_id": candidate_id,
        "source_url": source_url,
        "verification_status": finding["verification_status"],
        "proposal_created": False,
        "production_changes_authorized": False,
    }
