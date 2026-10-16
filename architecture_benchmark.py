"""TrustNG architecture benchmarking.

Records human-prepared comparisons with public financial systems and standards.
This module does not fetch evidence, verify claims, modify production, or execute
financial actions.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import research_collector


DATA_DIR = research_collector.DATA_DIR
BENCHMARKS_FILE = DATA_DIR / "architecture_benchmarks.json"

CAPABILITIES = {
    "api_security": "API authentication, authorization, certificates, and access control",
    "identity_and_consent": "Participant identity, customer consent, and permission management",
    "transaction_risk": "Transaction risk assessment and decision controls",
    "fraud_monitoring": "Fraud detection, investigation, and suspicious activity monitoring",
    "payment_integrity": "Idempotency, transaction integrity, and duplicate prevention",
    "auditability": "Tamper-evident audit trails and decision explanations",
    "operational_resilience": "Availability, recovery, incident handling, and service continuity",
    "ai_governance": "AI evaluation, explainability, model monitoring, and human oversight",
    "privacy_and_data": "Data minimization, retention, access, and privacy protection",
    "cross_border_payments": "Cross-border payment validation and interoperability",
    "developer_conformance": "API specifications, sandbox testing, and conformance validation",
    "third_party_risk": "External provider, dependency, and supply-chain risk management",
}

REVIEW_DECISIONS = {"approved_for_testing", "rejected", "needs_more_evidence"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read():
    if not BENCHMARKS_FILE.exists():
        return []
    with BENCHMARKS_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("Architecture benchmark store must be a JSON list.")
    return data


def _write(items):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = BENCHMARKS_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(items, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(BENCHMARKS_FILE)


def capability_catalog():
    return [
        {"capability_id": key, "description": value}
        for key, value in CAPABILITIES.items()
    ]


def list_benchmarks(status=None, capability_id=None):
    items = _read()
    if status is not None:
        items = [item for item in items if item["status"] == status]
    if capability_id is not None:
        items = [
            item for item in items
            if item["capability_id"] == capability_id
        ]
    return items


def create_benchmark(
    *,
    source_name,
    capability_id,
    source_url,
    source_observation,
    trustng_current_state,
    identified_gap,
    proposed_adaptation,
    risks,
    cost_estimate,
    dependencies,
    validation_plan,
    rollback_plan,
):
    """Record a comparison; all observations remain unverified until reviewed."""

    if capability_id not in CAPABILITIES:
        raise ValueError("Unknown capability_id.")

    sources = research_collector.source_catalog()
    source = next(
        (item for item in sources if item["name"] == source_name),
        None,
    )
    if source is None:
        raise ValueError("Source is not present in the approved source catalogue.")

    parsed = urlparse(source_url)
    approved_url = urlparse(source["url"])
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or source_url != source["url"]
        or parsed.hostname != approved_url.hostname
    ):
        raise ValueError(
            "Use the exact HTTPS URL recorded for the selected catalogue source."
        )

    fields = {
        "source_observation": source_observation,
        "trustng_current_state": trustng_current_state,
        "identified_gap": identified_gap,
        "proposed_adaptation": proposed_adaptation,
        "risks": risks,
        "cost_estimate": cost_estimate,
        "dependencies": dependencies,
        "validation_plan": validation_plan,
        "rollback_plan": rollback_plan,
    }
    for name, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string.")

    items = _read()
    benchmark = {
        "benchmark_id": str(uuid.uuid4()),
        "created_at": _now(),
        "updated_at": _now(),
        "source_name": source_name,
        "source_jurisdiction": source["jurisdiction"],
        "source_type": source["source_type"],
        "source_url": source_url,
        "capability_id": capability_id,
        "capability_description": CAPABILITIES[capability_id],
        **{key: value.strip() for key, value in fields.items()},
        "evidence_status": "requires_independent_verification",
        "status": "draft",
        "review": None,
        "test_results": [],
        "implementation_authorized": False,
        "production_changes_authorized": False,
    }
    items.append(benchmark)
    _write(items)
    return benchmark


def review_benchmark(benchmark_id, decision, reviewer, notes):
    """Record a human review. Approval permits testing only, not deployment."""

    if decision not in REVIEW_DECISIONS:
        raise ValueError("Unsupported review decision.")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("A reviewer identity is required.")
    if not isinstance(notes, str) or not notes.strip():
        raise ValueError("Review notes are required.")

    items = _read()
    for item in items:
        if item["benchmark_id"] != benchmark_id:
            continue
        if item["status"] in {"rejected", "approved_for_testing"}:
            raise ValueError("This benchmark has already received a final review.")

        item["review"] = {
            "decision": decision,
            "reviewer": reviewer.strip(),
            "notes": notes.strip(),
            "reviewed_at": _now(),
        }
        item["status"] = decision
        item["updated_at"] = _now()
        item["implementation_authorized"] = False
        item["production_changes_authorized"] = False
        _write(items)
        return item

    raise ValueError("Unknown benchmark_id.")


def record_test_result(benchmark_id, summary, passed, evidence):
    """Record controlled test results without authorizing production changes."""

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Test summary is required.")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Test evidence is required.")
    if not isinstance(passed, bool):
        raise ValueError("passed must be True or False.")

    items = _read()
    for item in items:
        if item["benchmark_id"] != benchmark_id:
            continue
        if item["status"] != "approved_for_testing":
            raise ValueError("Human approval for testing is required first.")

        item["test_results"].append({
            "summary": summary.strip(),
            "passed": passed,
            "evidence": evidence.strip(),
            "recorded_at": _now(),
        })
        item["updated_at"] = _now()
        item["implementation_authorized"] = False
        item["production_changes_authorized"] = False
        _write(items)
        return item

    raise ValueError("Unknown benchmark_id.")


def benchmark_policy():
    return {
        "purpose": "Compare documented external capabilities against TrustNG.",
        "automatic_source_verification": False,
        "automatic_code_changes": False,
        "automatic_production_deployment": False,
        "automatic_financial_execution": False,
        "human_review_required_before_testing": True,
        "testing_approval_authorizes_production": False,
        "required_proposal_fields": [
            "source_observation",
            "trustng_current_state",
            "identified_gap",
            "proposed_adaptation",
            "risks",
            "cost_estimate",
            "dependencies",
            "validation_plan",
            "rollback_plan",
        ],
    }


if __name__ == "__main__":
    print(json.dumps({
        "capabilities": len(CAPABILITIES),
        "benchmarks_recorded": len(list_benchmarks()),
        "catalogue_sources": len(research_collector.source_catalog()),
        "policy": benchmark_policy(),
    }, indent=2))
