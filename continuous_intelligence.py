"""
TrustNG Continuous Intelligence & Infrastructure Evolution.

Version 0.1:
- Stores research findings and improvement proposals.
- Prioritizes international research while retaining African and
  internal TrustNG learning.
- Requires evidence and records trade-offs.
- Supports human review but never changes production systems.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


DATA_DIR = Path(
    os.environ.get(
        "TRUSTNG_INTELLIGENCE_DIR",
        str(Path(__file__).resolve().parent / "intelligence_data"),
    )
)

FINDINGS_FILE = DATA_DIR / "research_findings.json"
PROPOSALS_FILE = DATA_DIR / "improvement_proposals.json"

VALID_REGIONS = {"international", "africa", "internal"}
VALID_EVIDENCE = {"low", "moderate", "strong"}
VALID_STATUSES = {
    "proposed",
    "under_review",
    "approved",
    "rejected",
    "testing",
    "implemented",
    "rolled_back",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_records(path):
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError(f"Invalid record store: {path.name}")

    return records


def _write_records(path, records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())

    temporary_path.replace(path)


def _required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")

    return value.strip()


def _validate_source_url(url):
    url = _required_text(url, "source_url")
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_url must be a valid HTTP(S) URL.")

    return url


def record_finding(
    *,
    title,
    summary,
    source_name,
    source_url,
    source_region,
    source_type,
    evidence_strength,
    relevance_to_trustng,
    limitations,
    lesson_for_africa,
):
    """
    Store one research finding.

    source_region:
        international - research outside Africa
        africa        - African research and context
        internal      - TrustNG tests, incidents, and observations

    A finding is not automatically treated as proven fact.
    """

    if source_region not in VALID_REGIONS:
        raise ValueError(
            f"source_region must be one of {sorted(VALID_REGIONS)}"
        )

    if evidence_strength not in VALID_EVIDENCE:
        raise ValueError(
            f"evidence_strength must be one of {sorted(VALID_EVIDENCE)}"
        )

    relevance = int(relevance_to_trustng)
    if not 1 <= relevance <= 5:
        raise ValueError("relevance_to_trustng must be between 1 and 5.")

    if source_region == "internal":
        normalized_url = None
    else:
        normalized_url = _validate_source_url(source_url)

    finding = {
        "finding_id": str(uuid.uuid4()),
        "created_at": _now(),
        "title": _required_text(title, "title"),
        "summary": _required_text(summary, "summary"),
        "source_name": _required_text(source_name, "source_name"),
        "source_url": normalized_url,
        "source_region": source_region,
        "source_type": _required_text(source_type, "source_type"),
        "evidence_strength": evidence_strength,
        "relevance_to_trustng": relevance,
        "limitations": _required_text(limitations, "limitations"),
        "lesson_for_africa": _required_text(
            lesson_for_africa, "lesson_for_africa"
        ),
        "verification_status": (
            "internally_recorded"
            if source_region == "internal"
            else "requires_independent_verification"
        ),
    }

    records = _read_records(FINDINGS_FILE)
    records.append(finding)
    _write_records(FINDINGS_FILE, records)

    return finding


def list_findings(source_region=None):
    """Return findings, optionally filtered by region."""

    if source_region is not None and source_region not in VALID_REGIONS:
        raise ValueError("Unknown source region.")

    findings = _read_records(FINDINGS_FILE)

    if source_region is not None:
        findings = [
            item for item in findings
            if item["source_region"] == source_region
        ]

    return sorted(
        findings,
        key=lambda item: item["created_at"],
        reverse=True,
    )


def create_proposal(
    *,
    title,
    problem,
    proposed_change,
    expected_benefits,
    disadvantages_and_risks,
    estimated_cost,
    dependencies,
    security_and_privacy_impact,
    testing_plan,
    implementation_steps,
    rollback_plan,
    finding_ids,
    expected_impact,
):
    """
    Create a human-reviewable improvement proposal.

    This function does not approve or deploy the proposal.
    """

    impact = int(expected_impact)
    if not 1 <= impact <= 5:
        raise ValueError("expected_impact must be between 1 and 5.")

    if not isinstance(finding_ids, list):
        raise ValueError("finding_ids must be a list.")

    findings = _read_records(FINDINGS_FILE)
    known_ids = {item["finding_id"] for item in findings}

    for finding_id in finding_ids:
        if finding_id not in known_ids:
            raise ValueError(f"Unknown finding_id: {finding_id}")

    proposal = {
        "proposal_id": str(uuid.uuid4()),
        "created_at": _now(),
        "title": _required_text(title, "title"),
        "problem": _required_text(problem, "problem"),
        "proposed_change": _required_text(
            proposed_change, "proposed_change"
        ),
        "expected_benefits": _required_text(
            expected_benefits, "expected_benefits"
        ),
        "disadvantages_and_risks": _required_text(
            disadvantages_and_risks, "disadvantages_and_risks"
        ),
        "estimated_cost": _required_text(estimated_cost, "estimated_cost"),
        "dependencies": _required_text(dependencies, "dependencies"),
        "security_and_privacy_impact": _required_text(
            security_and_privacy_impact, "security_and_privacy_impact"
        ),
        "testing_plan": _required_text(testing_plan, "testing_plan"),
        "implementation_steps": _required_text(
            implementation_steps, "implementation_steps"
        ),
        "rollback_plan": _required_text(rollback_plan, "rollback_plan"),
        "finding_ids": finding_ids,
        "expected_impact": impact,
        "status": "proposed",
        "human_decision": None,
        "decision_notes": None,
        "decision_at": None,
        "deployment_record": None,
        "priority_score": _calculate_priority(
            findings, finding_ids, impact
        ),
        "production_changes_authorized": False,
    }

    proposals = _read_records(PROPOSALS_FILE)
    proposals.append(proposal)
    _write_records(PROPOSALS_FILE, proposals)

    return proposal


def _calculate_priority(findings, finding_ids, impact):
    """
    Rank proposals using expected impact and evidence quality.
    This is a triage score, not a probability of success.
    """

    evidence_points = {"low": 1, "moderate": 2, "strong": 3}
    by_id = {item["finding_id"]: item for item in findings}
    linked = [by_id[item] for item in finding_ids]

    evidence_score = max(
        (evidence_points[item["evidence_strength"]] for item in linked),
        default=0,
    )

    relevance_score = max(
        (item["relevance_to_trustng"] for item in linked),
        default=0,
    )

    return impact * 5 + evidence_score * 3 + relevance_score * 2


def list_proposals(status=None):
    """Return proposals, highest priority first."""

    if status is not None and status not in VALID_STATUSES:
        raise ValueError("Unknown proposal status.")

    proposals = _read_records(PROPOSALS_FILE)

    if status is not None:
        proposals = [
            item for item in proposals if item["status"] == status
        ]

    return sorted(
        proposals,
        key=lambda item: (
            item["priority_score"],
            item["created_at"],
        ),
        reverse=True,
    )


def review_proposal(proposal_id, *, decision, notes, reviewer):
    """
    Record an explicit human decision.

    Approval only records permission to proceed to a separately
    controlled implementation workflow. It does not deploy code.
    """

    allowed_decisions = {"approved", "rejected", "under_review"}

    if decision not in allowed_decisions:
        raise ValueError(
            f"decision must be one of {sorted(allowed_decisions)}"
        )

    reviewer = _required_text(reviewer, "reviewer")
    notes = _required_text(notes, "notes")

    proposals = _read_records(PROPOSALS_FILE)

    for proposal in proposals:
        if proposal["proposal_id"] != proposal_id:
            continue

        if proposal["status"] in {"implemented", "rolled_back"}:
            raise ValueError("Completed proposals cannot be reviewed again.")

        proposal["status"] = decision
        proposal["human_decision"] = decision
        proposal["decision_notes"] = notes
        proposal["reviewer"] = reviewer
        proposal["decision_at"] = _now()

        # No code execution, deployment, or financial action occurs here.
        proposal["production_changes_authorized"] = False

        _write_records(PROPOSALS_FILE, proposals)
        return proposal

    raise ValueError(f"Unknown proposal_id: {proposal_id}")


def record_test_result(proposal_id, *, summary, passed, evidence):
    """Record test evidence without deploying the proposal."""

    proposals = _read_records(PROPOSALS_FILE)

    for proposal in proposals:
        if proposal["proposal_id"] != proposal_id:
            continue

        if proposal["status"] not in {"approved", "testing"}:
            raise ValueError(
                "A human must approve a proposal before testing is recorded."
            )

        result = {
            "recorded_at": _now(),
            "summary": _required_text(summary, "summary"),
            "passed": bool(passed),
            "evidence": _required_text(evidence, "evidence"),
        }

        proposal.setdefault("test_results", []).append(result)
        proposal["status"] = "testing"

        _write_records(PROPOSALS_FILE, proposals)
        return result

    raise ValueError(f"Unknown proposal_id: {proposal_id}")


def record_implementation_outcome(
    proposal_id,
    *,
    outcome,
    evidence,
    rollback_performed=False,
):
    """
    Record an outcome reported by a human operator.

    This records a claim; it does not deploy, roll back, or verify
    production by itself.
    """

    proposals = _read_records(PROPOSALS_FILE)

    for proposal in proposals:
        if proposal["proposal_id"] != proposal_id:
            continue

        if proposal["status"] != "testing":
            raise ValueError("Proposal must have recorded testing first.")

        if not any(
            result["passed"]
            for result in proposal.get("test_results", [])
        ):
            raise ValueError(
                "At least one passing test result is required first."
            )

        proposal["deployment_record"] = {
            "recorded_at": _now(),
            "outcome": _required_text(outcome, "outcome"),
            "evidence": _required_text(evidence, "evidence"),
            "rollback_performed": bool(rollback_performed),
        }

        proposal["status"] = (
            "rolled_back" if rollback_performed else "implemented"
        )

        # A record of implementation is not proof of deployment.
        proposal["production_changes_authorized"] = False

        _write_records(PROPOSALS_FILE, proposals)
        return proposal

    raise ValueError(f"Unknown proposal_id: {proposal_id}")


def research_policy():
    """
    Initial research allocation targets, not measured outcomes.
    """

    return {
        "name": "TrustNG Continuous Intelligence & Infrastructure Evolution",
        "international_research_target_percent": 80,
        "african_research_target_percent": 20,
        "internal_trustng_learning": (
            "Tracked separately and added to prioritization as evidence "
            "from tests, incidents, and operational outcomes becomes available."
        ),
        "source_verification_required": True,
        "human_approval_required_before_implementation": True,
        "autonomous_production_changes": False,
        "autonomous_financial_execution": False,
        "automated_external_research_enabled": False,
    }
