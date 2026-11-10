"""
TrustNG Architecture Benchmarking Engine.

Purpose:
- Compare documented capability observations with TrustNG's declared state.
- Record capability gaps, adaptation proposals, risks, and validation plans.
- Require human review before any proposed change is adopted.

This module does not fetch external sources, certify compliance, modify production
configuration, authorize payments, or execute transfers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import json
import uuid


class CapabilityStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    PLANNED = "PLANNED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNKNOWN = "UNKNOWN"


class EvidenceStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNVERIFIED = "UNVERIFIED"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED_FOR_EVALUATION = "APPROVED_FOR_EVALUATION"
    REJECTED = "REJECTED"


BENCHMARK_DOMAINS = {
    "api_security": "API security and access control",
    "identity_consent": "Identity verification and consent",
    "transaction_risk": "Transaction risk assessment",
    "fraud_monitoring": "Fraud monitoring and investigation",
    "payment_integrity": "Payment integrity and idempotency",
    "auditability": "Audit trails and evidence integrity",
    "resilience": "Failure handling and recovery",
    "ai_governance": "AI governance and explainability",
    "privacy": "Data minimization and privacy",
    "cross_border": "Cross-border payment risk",
    "developer_conformance": "Developer API conformance",
    "third_party_risk": "Third-party and provider risk",
}


@dataclass
class SourceObservation:
    source_name: str
    source_url: str
    capability: str
    observation: str
    evidence_status: str = EvidenceStatus.NEEDS_REVIEW.value
    publication_date: str | None = None
    document_title: str = ""
    document_section: str = ""
    evidence_excerpt: str = ""
    evidence_reference: str = ""
    reviewed_by: str | None = None
    notes: str = ""

    def validate(self) -> None:
        if not self.source_name.strip():
            raise ValueError("Source name is required.")
        if not self.source_url.strip():
            raise ValueError("Source URL or document reference is required.")
        if not self.capability.strip() or not self.observation.strip():
            raise ValueError("Capability and observation are required.")
        if self.evidence_status not in {item.value for item in EvidenceStatus}:
            raise ValueError("Unsupported evidence status.")
        if self.evidence_status == EvidenceStatus.VERIFIED and not self.reviewed_by:
            raise ValueError("Verified evidence must identify its reviewer.")


@dataclass
class TrustNGCapability:
    domain: str
    status: str
    current_state: str
    limitations: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if self.domain not in BENCHMARK_DOMAINS:
            raise ValueError(f"Unknown benchmark domain: {self.domain}")
        if self.status not in {item.value for item in CapabilityStatus}:
            raise ValueError(f"Unsupported capability status: {self.status}")
        if not self.current_state.strip():
            raise ValueError("Current state description is required.")


@dataclass
class BenchmarkFinding:
    finding_id: str
    domain: str
    domain_name: str
    source_name: str
    source_url: str
    source_observation: str
    evidence_status: str
    trustng_status: str
    trustng_current_state: str
    gap: str
    proposed_adaptation: str
    risk_if_unaddressed: str
    validation_plan: list[str]
    rollback_plan: str
    document_title: str = ""
    document_publication_date: str | None = None
    document_section: str = ""
    evidence_excerpt: str = ""
    evidence_reference: str = ""
    evidence_reviewer_notes: str = ""
    review_status: str = ReviewStatus.PENDING.value
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArchitectureBenchmark:
    """In-memory benchmark builder; persistence can be added by a later integration."""

    def __init__(self) -> None:
        self._capabilities: dict[str, TrustNGCapability] = {}
        self._observations: list[SourceObservation] = []
        self._findings: list[BenchmarkFinding] = []

    def set_trustng_capability(self, capability: TrustNGCapability) -> None:
        capability.validate()
        self._capabilities[capability.domain] = capability

    def add_source_observation(self, observation: SourceObservation) -> None:
        observation.validate()
        self._observations.append(observation)

    def build_findings(self) -> list[BenchmarkFinding]:
        """Build reviewable findings; evidence is never silently treated as verified."""
        findings: list[BenchmarkFinding] = []

        for observation in self._observations:
            domain = observation.capability
            capability = self._capabilities.get(domain)

            if capability is None:
                status = CapabilityStatus.UNKNOWN.value
                current_state = "TrustNG capability state has not been recorded."
                gap = "Current TrustNG state is unknown; assess before comparing."
                proposal = "Document the current implementation and its boundaries."
                risk = "An unknown state may conceal a security or reliability gap."
            else:
                status = capability.status
                current_state = capability.current_state

                if capability.status == CapabilityStatus.IMPLEMENTED.value:
                    gap = (
                        "No gap inferred from status alone; validate the implementation "
                        "against the documented observation."
                    )
                    proposal = "Perform a documented conformance review."
                    risk = "A claimed implementation may not cover every relevant case."
                elif capability.status == CapabilityStatus.PARTIAL.value:
                    gap = "Capability is only partially implemented."
                    proposal = "Define and prioritize the missing control coverage."
                    risk = "Uncovered cases may create inconsistent protection."
                elif capability.status == CapabilityStatus.PLANNED.value:
                    gap = "Capability is planned but not yet implemented."
                    proposal = "Design, review, and implement the capability in stages."
                    risk = "Protection should not be assumed before implementation."
                elif capability.status == CapabilityStatus.NOT_IMPLEMENTED.value:
                    gap = "Capability is not currently implemented."
                    proposal = "Assess feasibility and business value before implementation."
                    risk = "The missing capability may leave a relevant threat unaddressed."
                else:
                    gap = "Capability status is unknown and needs assessment."
                    proposal = "Inspect the current design and record evidence."
                    risk = "Unknown controls cannot be relied on for risk decisions."

                if capability.limitations:
                    gap += " Known limitations: " + "; ".join(capability.limitations)

            if observation.evidence_status != EvidenceStatus.VERIFIED.value:
                gap += (
                    " Source evidence has not been fully verified; do not treat this "
                    "comparison as a compliance conclusion."
                )

            findings.append(
                BenchmarkFinding(
                    finding_id="AB-" + __import__("hashlib").sha256(
                        "|".join((
                            observation.source_name.strip(),
                            observation.source_url.strip().rstrip("/"),
                            observation.capability.strip(),
                            observation.document_title.strip(),
                            observation.document_section.strip(),
                            observation.observation.strip(),
                        )).encode("utf-8")
                    ).hexdigest()[:12].upper(),
                    domain=domain,
                    domain_name=BENCHMARK_DOMAINS.get(domain, domain),
                    source_name=observation.source_name,
                    source_url=observation.source_url,
                    source_observation=observation.observation,
                    evidence_status=observation.evidence_status,
                    document_title=observation.document_title,
                    document_publication_date=observation.publication_date,
                    document_section=observation.document_section,
                    evidence_excerpt=observation.evidence_excerpt,
                    evidence_reference=observation.evidence_reference,
                    evidence_reviewer_notes=observation.notes,
                    trustng_status=status,
                    trustng_current_state=current_state,
                    gap=gap,
                    proposed_adaptation=proposal,
                    risk_if_unaddressed=risk,
                    validation_plan=[
                        "Confirm the source and the date/version of its requirement.",
                        "Map the requirement to the exact TrustNG component and code path.",
                        "Define acceptance criteria and security failure cases.",
                        "Obtain human review before implementation.",
                        "Validate in a sandbox before considering production adoption.",
                    ],
                    rollback_plan=(
                        "Keep the existing behavior as the default; deploy no change "
                        "until reviewed. If an approved implementation fails validation, "
                        "revert the isolated change and preserve audit evidence."
                    ),
                )
            )

        self._findings.extend(findings)
        return findings

    def findings(self) -> list[dict[str, Any]]:
        return [finding.to_dict() for finding in self._findings]

    def summary(self) -> dict[str, Any]:
        by_domain: dict[str, int] = {}
        for finding in self._findings:
            by_domain[finding.domain] = by_domain.get(finding.domain, 0) + 1

        return {
            "engine": "TrustNG Architecture Benchmarking Engine",
            "version": "0.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "capability_domains": len(BENCHMARK_DOMAINS),
            "recorded_capabilities": len(self._capabilities),
            "source_observations": len(self._observations),
            "findings": len(self._findings),
            "review_required": True,
            "automatic_production_changes": False,
            "payment_authorized": False,
            "funds_moved": False,
            "findings_by_domain": by_domain,
        }

    def export_json(self, include_findings: bool = True) -> str:
        result: dict[str, Any] = {"summary": self.summary()}
        if include_findings:
            result["findings"] = self.findings()
        return json.dumps(result, indent=2, ensure_ascii=False)


def create_default_benchmark() -> ArchitectureBenchmark:
    """Create a cautious baseline from the currently declared TrustNG architecture."""
    engine = ArchitectureBenchmark()

    baseline = [
        TrustNGCapability(
            "api_security", "IMPLEMENTED",
            "API-key protection exists for selected internal endpoints.",
            ["Confirm route-by-route enforcement and key rotation procedures."],
        ),
        TrustNGCapability(
            "identity_consent", "PARTIAL",
            "Sandbox OTP and recipient email ownership verification exist.",
            ["Email or phone possession does not establish legal identity."],
        ),
        TrustNGCapability(
            "transaction_risk", "IMPLEMENTED",
            "Risk evaluation returns advisory decisions and does not execute payments.",
            ["Validate decision consistency across all transaction entry points."],
        ),
        TrustNGCapability(
            "fraud_monitoring", "PARTIAL",
            "Fraud-case and investigation routes exist.",
            ["Confirm alert coverage, case access controls, and operational monitoring."],
        ),
        TrustNGCapability(
            "payment_integrity", "PARTIAL",
            "Idempotency and uncertain-outcome recovery safeguards exist in sandbox flows.",
            ["No live payment execution is claimed."],
        ),
        TrustNGCapability(
            "auditability", "PARTIAL",
            "Audit-related routes and investigation records exist.",
            ["Review event coverage, tamper resistance, retention, and access controls."],
        ),
        TrustNGCapability(
            "resilience", "PARTIAL",
            "Provider-operation recovery and reconciliation paths exist.",
            ["Confirm timeout, retry, and database-failure behavior."],
        ),
        TrustNGCapability(
            "ai_governance", "PARTIAL",
            "AI risk intelligence is advisory and confidence is not calibrated.",
            ["Do not present advisory scores as proven accuracy or authorization."],
        ),
        TrustNGCapability(
            "privacy", "PARTIAL",
            "Some account references use random tokens and data-minimization safeguards.",
            ["Review retention, deletion, logs, and access to personal data."],
        ),
        TrustNGCapability(
            "cross_border", "PLANNED",
            "Africa-focused risk infrastructure is a project goal.",
            ["Country-specific legal and operational requirements need review."],
        ),
        TrustNGCapability(
            "developer_conformance", "PARTIAL",
            "API documentation and health endpoints exist.",
            ["Add formal versioning, conformance criteria, and integration guidance."],
        ),
        TrustNGCapability(
            "third_party_risk", "PARTIAL",
            "A sandbox provider adapter exists.",
            ["No live provider capability or production approval is implied."],
        ),
    ]

    for capability in baseline:
        engine.set_trustng_capability(capability)

    return engine


def build_catalogue_backed_report(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a review-only report from exact entries in the official source catalogue.

    Each observation must provide source_name, source_url, capability, and
    observation. Catalogue membership does not verify the evidence itself.
    This function does not fetch sources or authorize production changes.
    """
    from research_collector import RESEARCH_SOURCES

    approved = {
        (item["name"], item["url"]): item
        for item in RESEARCH_SOURCES
        if isinstance(item.get("name"), str)
        and isinstance(item.get("url"), str)
        and item["url"].startswith("https://")
    }

    engine = create_default_benchmark()

    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("Each source observation must be an object.")

        required = ("source_name", "source_url", "capability", "observation")
        if any(not isinstance(item.get(key), str) or not item[key].strip()
               for key in required):
            raise ValueError(
                "Each observation requires source_name, source_url, capability, and observation."
            )

        catalogue_entry = approved.get((item["source_name"], item["source_url"]))
        if catalogue_entry is None:
            raise ValueError(
                "Source is not in the approved source catalogue with its exact HTTPS URL."
            )

        capability = item["capability"]
        if capability not in BENCHMARK_DOMAINS:
            raise ValueError(f"Unknown benchmark domain: {capability}")

        status = item.get("evidence_status", EvidenceStatus.NEEDS_REVIEW.value)
        if status != EvidenceStatus.NEEDS_REVIEW.value:
            raise ValueError(
                "Catalogue-backed observations must start as NEEDS_REVIEW. "
                "Independent verification must be recorded separately."
            )

        engine.add_source_observation(
            SourceObservation(
                source_name=catalogue_entry["name"],
                source_url=catalogue_entry["url"],
                capability=capability,
                observation=item["observation"].strip(),
                evidence_status=EvidenceStatus.NEEDS_REVIEW.value,
                publication_date=item.get("publication_date"),
                document_title=item.get("document_title", ""),
                document_section=item.get("document_section", ""),
                evidence_excerpt=item.get("evidence_excerpt", ""),
                evidence_reference=item.get("evidence_reference", ""),
                notes=item.get("notes", ""),
            )
        )

    engine.build_findings()
    report = json.loads(engine.export_json())
    report["source_catalogue"] = {
        "name": "research_collector.RESEARCH_SOURCES",
        "catalogue_entries_available": len(RESEARCH_SOURCES),
        "observations_submitted": len(observations),
        "source_fetching_performed": False,
        "catalogue_membership_means_evidence_verified": False,
    }
    report["governance"] = {
        "human_review_required": True,
        "automatic_code_changes": False,
        "automatic_production_deployment": False,
        "payment_authorized": False,
        "funds_moved": False,
    }
    return report


def run_benchmark_cli(argv: list[str] | None = None) -> int:
    """List or export the existing research catalogue without verifying it."""
    import argparse
    from pathlib import Path
    from research_collector import RESEARCH_SOURCES

    parser = argparse.ArgumentParser(
        description="TrustNG architecture benchmark catalogue inventory"
    )
    parser.add_argument(
        "command",
        choices=("list-sources", "export-catalogue", "generate-report", "review-finding", "list-reviews", "list-review-mappings", "review-history", "review-integrity"),
    )
    parser.add_argument(
        "--output",
        default="intelligence_data/architecture_benchmark_catalogue.json",
        help="Output path for catalogue export",
    )
    parser.add_argument(
        "--report-output",
        default="intelligence_data/architecture_benchmark_report.json",
        help="Separate output path for generated benchmark reports",
    )
    parser.add_argument(
        "--observations-file",
        default="intelligence_data/benchmark_observations.json",
        help="JSON array of catalogue-backed observations for generate-report",
    )
    parser.add_argument("--finding-id", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument(
        "--decision",
        choices=("PENDING", "APPROVED_FOR_EVALUATION", "REJECTED"),
        default="PENDING",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument("--evidence-reference", default="")
    parser.add_argument(
        "--confirm-legacy-id-mapping",
        action="store_true",
        help="Explicitly confirm a provisional legacy finding-ID mapping for this new review only",
    )
    parser.add_argument(
        "--reviews-file",
        default="intelligence_data/architecture_benchmark_reviews.json",
    )
    args = parser.parse_args(argv)

    if args.command == "review-history" and not args.finding_id.strip():
        parser.error("review-history requires --finding-id")

    if args.command == "review-integrity":
        from benchmark_review import review_integrity_report
        try:
            result = review_integrity_report(Path(args.reviews_file))
        except (ValueError, OSError) as exc:
            raise SystemExit(f"Review integrity report failed: {exc}") from exc
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command in ("review-finding", "list-reviews", "list-review-mappings", "review-history"):
        from benchmark_review import record_review, list_reviews, list_review_mappings, list_review_history

        try:
            if args.command == "list-reviews":
                print(json.dumps(list_reviews(Path(args.reviews_file)), indent=2))
                return 0
            if args.command == "list-review-mappings":
                mappings = list_review_mappings(
                    report_path=Path("intelligence_data/architecture_benchmark_report.json"),
                    reviews_path=Path(args.reviews_file),
                    aliases_path=Path("intelligence_data/architecture_benchmark_finding_aliases.json"),
                )
                print(json.dumps(mappings, indent=2, ensure_ascii=False))
                return 0
            if args.command == "review-history":
                history = list_review_history(
                    finding_id=args.finding_id,
                    report_path=Path("intelligence_data/architecture_benchmark_report.json"),
                    reviews_path=Path(args.reviews_file),
                    aliases_path=Path("intelligence_data/architecture_benchmark_finding_aliases.json"),
                )
                if any(
                    item.get("human_confirmation_required", False)
                    for item in history.get("mapping_statuses", [])
                    if isinstance(item, dict)
                ):
                    print(
                        "WARNING: A provisional finding-ID mapping requires "
                        "human confirmation; do not treat it as verified."
                    )
                print(json.dumps(history, indent=2, ensure_ascii=False))
                return 0

            record = record_review(
                finding_id=args.finding_id,
                reviewer=args.reviewer,
                decision=args.decision,
                notes=args.notes,
                evidence_reference=args.evidence_reference,
                report_path=Path(args.output)
                if args.output != "intelligence_data/architecture_benchmark_catalogue.json"
                else Path("intelligence_data/architecture_benchmark_report.json"),
                reviews_path=Path(args.reviews_file),
                confirm_legacy_id_mapping=args.confirm_legacy_id_mapping,
            )
        except (ValueError, OSError) as exc:
            raise SystemExit(f"Review operation failed: {exc}") from exc

        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0

    sources = [
        {
            "name": item["name"],
            "url": item["url"],
            "jurisdiction": item.get("jurisdiction"),
            "region": item.get("region"),
            "topic": item.get("topic"),
            "source_type": item.get("source_type"),
            "evidence_status": EvidenceStatus.UNVERIFIED.value,
            "review_status": ReviewStatus.PENDING.value,
        }
        for item in RESEARCH_SOURCES
    ]

    report = {
        "report": "TrustNG Architecture Benchmark Catalogue Inventory",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_domains": BENCHMARK_DOMAINS,
        "source_count": len(sources),
        "sources": sources,
        "evidence_verified": False,
        "limitations": [
            "Catalogue inventory only; no external source was fetched.",
            "Catalogue membership does not verify evidence.",
            "Human review is required before evidence is marked verified.",
        ],
        "governance": {
            "automatic_code_changes": False,
            "automatic_production_deployment": False,
            "payment_authorized": False,
            "funds_moved": False,
        },
    }

    if args.command == "list-sources":
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    output = Path(args.output)

    if args.command == "generate-report":
        output = Path(args.report_output)
        import json as json_module

        observations_path = Path(args.observations_file)
        if not observations_path.is_file():
            raise SystemExit(
                f"Observations file not found: {observations_path}. "
                "Create a JSON array of observations first."
            )

        try:
            observations = json_module.loads(
                observations_path.read_text(encoding="utf-8")
            )
        except json_module.JSONDecodeError as exc:
            raise SystemExit(f"Invalid observations JSON: {exc}") from exc

        if not isinstance(observations, list):
            raise SystemExit("Observations file must contain a JSON array.")

        try:
            generated_report = build_catalogue_backed_report(observations)
        except (ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f"Cannot generate benchmark report: {exc}") from exc

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json_module.dumps(generated_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"Generated review-only benchmark report with "
            f"{len(observations)} observations: {output}"
        )
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(sources)} catalogue entries to {output}")
    return 0


# --- Backward-compatible persistent benchmark API restored from the original implementation ---
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
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in (
        "list-sources", "export-catalogue", "generate-report",
        "review-finding", "list-reviews", "list-review-mappings", "review-history",
        "review-integrity",
    ):
        raise SystemExit(run_benchmark_cli())
    engine = create_default_benchmark()
    print(json.dumps(engine.summary(), indent=2))
