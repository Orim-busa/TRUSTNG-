"""Human review records for TrustNG architecture benchmark findings.

Review decisions do not verify evidence, certify compliance, authorize payments,
change production code, or trigger deployment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid
import hashlib

REVIEW_DECISIONS = {
    "PENDING",
    "APPROVED_FOR_EVALUATION",
    "REJECTED",
}

DEFAULT_REPORT = Path("intelligence_data/architecture_benchmark_report.json")
DEFAULT_REVIEWS = Path("intelligence_data/architecture_benchmark_reviews.json")
DEFAULT_REVIEW_CHECKPOINT = Path("intelligence_data/architecture_benchmark_review_checkpoint.json")
DEFAULT_ALIASES = Path("intelligence_data/architecture_benchmark_finding_aliases.json")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _canonical_review_hash(record: dict[str, Any]) -> str:
    """Hash a review record without its own hash field."""
    payload = {
        key: value
        for key, value in record.items()
        if key != "record_hash"
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()



def _write_review_checkpoint(
    reviews_path: Path,
    records: list[Any],
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Store a local checkpoint of the latest hashed review."""
    checkpoint_path = checkpoint_path or reviews_path.with_name(
        "architecture_benchmark_review_checkpoint.json"
    )
    latest = next(
        (
            item for item in reversed(records)
            if isinstance(item, dict)
            and isinstance(item.get("record_hash"), str)
            and item.get("record_hash")
        ),
        None,
    )
    if latest is None:
        raise ValueError("Cannot checkpoint a chain without hashed records.")

    payload = {
        "checkpoint_version": 1,
        "reviews_file": reviews_path.name,
        "record_count": len(records),
        "latest_review_id": latest.get("review_id"),
        "latest_record_hash": latest["record_hash"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "limitation": "Local checkpoint; an attacker able to rewrite both files can alter it.",
    }
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(checkpoint_path)
    return payload


def review_integrity_report(
    reviews_path: Path = DEFAULT_REVIEWS,
    checkpoint_path: Path | None = None,
) -> dict[str, Any]:
    """Check structure, hash validity, chain continuity, and legacy gaps."""
    if not reviews_path.exists():
        checkpoint_path = checkpoint_path or reviews_path.with_name(
            "architecture_benchmark_review_checkpoint.json"
        )
        checkpoint_exists = checkpoint_path.exists()
        return {
            "file_exists": False,
            "record_count": 0,
            "checkpoint": {
                "checkpoint_exists": checkpoint_exists,
                "checkpoint_valid": False,
                "latest_review_matches": None,
                "checkpoint_error": (
                    "Checkpoint exists but no review file is available."
                    if checkpoint_exists else None
                ),
            },
            "checkpoint_verified": False,
            "duplicate_review_ids": [],
            "invalid_records": [],
            "legacy_unchained_records": 0,
            "legacy_record_indexes": [],
            "hashed_record_count": 0,
            "hash_mismatches": [],
            "broken_chain_links": [],
            "chain_continuity_passed": False,
            "structural_checks_passed": True,
            "hashes_valid": False,
            "chain_links_valid": False,
            "hash_chain_checks_passed": False,
            "tamper_evident": False,
            "limitations": [
                "No review file exists to verify.",
                "A hash chain is tamper-evident, not tamper-proof.",
            ],
        }

    records = load_json(reviews_path)
    if not isinstance(records, list):
        raise ValueError("Review records file must contain a JSON array.")

    seen_ids = set()
    duplicate_ids = []
    invalid_records = []
    legacy_indexes = []
    hash_mismatches = []
    broken_links = []
    hashed_count = 0
    previous_hash = None
    chain_started = False

    for index, item in enumerate(records):
        if not isinstance(item, dict):
            invalid_records.append({
                "index": index,
                "issue": "record_is_not_an_object",
            })
            continue

        review_id = item.get("review_id")
        if not isinstance(review_id, str) or not review_id.strip():
            invalid_records.append({
                "index": index,
                "issue": "missing_review_id",
            })
        elif review_id in seen_ids:
            duplicate_ids.append(review_id)
        else:
            seen_ids.add(review_id)

        stored_hash = item.get("record_hash")
        if not isinstance(stored_hash, str) or not stored_hash:
            legacy_indexes.append(index)
            continue

        hashed_count += 1
        expected_hash = _canonical_review_hash(item)
        if stored_hash != expected_hash:
            hash_mismatches.append({
                "index": index,
                "review_id": review_id,
                "issue": "record_hash_mismatch",
            })

        expected_previous = previous_hash if chain_started else None
        actual_previous = item.get("previous_record_hash")
        if actual_previous != expected_previous:
            broken_links.append({
                "index": index,
                "review_id": review_id,
                "issue": (
                    "chain_link_mismatch_after_legacy_gap"
                    if legacy_indexes and legacy_indexes[-1] < index
                    else "chain_link_mismatch"
                ),
                "expected_previous_record_hash": expected_previous,
                "stored_previous_record_hash": actual_previous,
            })

        previous_hash = stored_hash
        chain_started = True

    checkpoint_path = checkpoint_path or reviews_path.with_name(
        "architecture_benchmark_review_checkpoint.json"
    )
    checkpoint_status = {
        "checkpoint_exists": checkpoint_path.exists(),
        "checkpoint_valid": False,
        "latest_review_matches": None,
        "checkpoint_error": None,
    }
    if checkpoint_path.exists():
        try:
            checkpoint = load_json(checkpoint_path)
            latest_hashed = next(
                (
                    item for item in reversed(records)
                    if isinstance(item, dict)
                    and isinstance(item.get("record_hash"), str)
                    and item.get("record_hash")
                ),
                None,
            )
            if not isinstance(checkpoint, dict):
                raise ValueError("Checkpoint must be a JSON object.")
            if latest_hashed is None:
                checkpoint_status["checkpoint_error"] = (
                    "No hashed review records exist."
                )
            else:
                matches = (
                    checkpoint.get("checkpoint_version") == 1
                    and checkpoint.get("reviews_file") == reviews_path.name
                    and checkpoint.get("record_count") == len(records)
                    and checkpoint.get("latest_review_id") == latest_hashed.get("review_id")
                    and checkpoint.get("latest_record_hash") == latest_hashed.get("record_hash")
                )
                checkpoint_status["latest_review_matches"] = matches
                checkpoint_status["checkpoint_valid"] = matches
                if not matches:
                    checkpoint_status["checkpoint_error"] = (
                        "Checkpoint does not match the current review-file head."
                    )
        except (ValueError, OSError) as exc:
            checkpoint_status["checkpoint_error"] = str(exc)

    structural_ok = not duplicate_ids and not invalid_records
    links_ok = not broken_links
    hashes_ok = not hash_mismatches
    continuity_ok = (
        hashed_count > 0
        and not legacy_indexes
        and links_ok
        and hashes_ok
    )

    return {
        "file_exists": True,
        "record_count": len(records),
        "checkpoint": checkpoint_status,
        "checkpoint_verified": checkpoint_status["checkpoint_valid"],
        "duplicate_review_ids": sorted(set(duplicate_ids)),
        "invalid_records": invalid_records,
        "legacy_unchained_records": len(legacy_indexes),
        "legacy_record_indexes": legacy_indexes,
        "hashed_record_count": hashed_count,
        "hash_mismatches": hash_mismatches,
        "broken_chain_links": broken_links,
        "structural_checks_passed": structural_ok,
        "hashes_valid": hashes_ok,
        "chain_links_valid": links_ok,
        "chain_continuity_passed": continuity_ok,
        "hash_chain_checks_passed": (
            hashed_count > 0
            and hashes_ok
            and links_ok
            and structural_ok
            and checkpoint_status["checkpoint_valid"]
        ),
        "tamper_evident": (
            hashed_count > 0
            and hashes_ok
            and links_ok
            and structural_ok
            and checkpoint_status["checkpoint_valid"]
        ),
        "limitations": [
            "Legacy records without hashes cannot be verified cryptographically.",
            "A broken link can reveal missing or reordered records within the stored chain.",
            "The checkpoint is stored locally and can be rewritten by an attacker who can alter both files.",
            "An attacker able to rewrite the entire file may rebuild the chain.",
            "The chain does not verify evidence, certify compliance, or authorize payments.",
            "This report does not modify stored review records.",
        ],
    }


def record_review(
    finding_id: str,
    reviewer: str,
    decision: str,
    notes: str,
    evidence_reference: str = "",
    report_path: Path = DEFAULT_REPORT,
    reviews_path: Path = DEFAULT_REVIEWS,
    confirm_legacy_id_mapping: bool = False,
    aliases_path: Path = DEFAULT_ALIASES,
) -> dict[str, Any]:
    if not finding_id.strip():
        raise ValueError("Finding ID is required.")
    if not reviewer.strip():
        raise ValueError("Reviewer name is required.")
    if decision not in REVIEW_DECISIONS:
        raise ValueError(
            "Decision must be PENDING, APPROVED_FOR_EVALUATION, or REJECTED."
        )
    if not notes.strip():
        raise ValueError("Review notes are required.")

    report = load_json(report_path)
    findings = report.get("findings", [])
    requested_finding_id = finding_id
    finding = next(
        (item for item in findings if item.get("finding_id") == finding_id),
        None,
    )
    alias_used = None

    if finding is None and aliases_path.exists():
        alias_data = load_json(aliases_path)
        if isinstance(alias_data, dict):
            aliases = alias_data.get("aliases")
        else:
            aliases = alias_data

        if not isinstance(aliases, list):
            raise ValueError(
                "Finding-ID aliases file must be a JSON array or an object "
                "containing an 'aliases' array."
            )

        alias = next(
            (
                item for item in aliases
                if isinstance(item, dict)
                and item.get("legacy_finding_id") == finding_id
            ),
            None,
        )
        if alias is not None:
            if alias.get("link_status") != "PROVISIONAL_NEEDS_HUMAN_CONFIRMATION":
                raise ValueError(
                    f"Legacy ID mapping has unsupported status: "
                    f"{alias.get('link_status')!r}"
                )
            if not confirm_legacy_id_mapping:
                raise ValueError(
                    f"Legacy finding ID {finding_id} has a provisional mapping to "
                    f"{alias.get('current_finding_id')}. Confirm it explicitly with "
                    "--confirm-legacy-id-mapping after human review."
                )

            current_id = alias.get("current_finding_id", "")
            finding = next(
                (item for item in findings if item.get("finding_id") == current_id),
                None,
            )
            if finding is None:
                raise ValueError(
                    f"Mapped current finding ID is not present in report: {current_id}"
                )
            alias_used = alias
            finding_id = current_id

    if finding is None:
        raise ValueError(f"Finding ID not found in report: {requested_finding_id}")

    reviews_path.parent.mkdir(parents=True, exist_ok=True)
    if reviews_path.exists():
        records = load_json(reviews_path)
        if not isinstance(records, list):
            raise ValueError("Review records file must contain a JSON array.")
    else:
        records = []

    previous_review = next(
        (
            item for item in reversed(records)
            if isinstance(item, dict)
            and item.get("finding_id") == finding_id
        ),
        None,
    )

    record = {
        "review_id": f"BR-{uuid.uuid4().hex[:12].upper()}",
        "finding_id": finding_id,
        "previous_review_id": (
            previous_review.get("review_id") if previous_review else None
        ),
        "review_sequence": 1 + sum(
            1 for item in records
            if isinstance(item, dict)
            and item.get("finding_id") == finding_id
        ),
        "audit_event": "REVIEW_RECORDED",
        "domain": finding.get("domain"),
        "reviewer": reviewer.strip(),
        "decision": decision,
        "notes": notes.strip(),
        "evidence_reference": evidence_reference.strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "evidence_verified": False,
        "compliance_certified": False,
        "payment_authorized": False,
        "funds_moved": False,
    }
    if alias_used is not None:
        record["legacy_finding_id"] = requested_finding_id
        record["finding_id_mapping_status"] = alias_used.get("link_status")
        record["legacy_mapping_review_id"] = alias_used.get("legacy_review_id")
        record["legacy_mapping_confirmed_for_this_review"] = True

    # Link new records to the latest hashed record. Existing legacy records
    # remain unchanged and are not retroactively represented as hashed.
    previous_hashed_record = next(
        (
            item for item in reversed(records)
            if isinstance(item, dict)
            and isinstance(item.get("record_hash"), str)
            and item.get("record_hash")
        ),
        None,
    )
    record["audit_chain_version"] = 1
    record["previous_record_hash"] = (
        previous_hashed_record["record_hash"]
        if previous_hashed_record is not None
        else None
    )
    record["record_hash"] = _canonical_review_hash(record)
    records.append(record)

    # Replace the review file atomically so an interrupted write cannot
    # leave a partially written JSON file.
    reviews_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = reviews_path.with_suffix(
        reviews_path.suffix + f".{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(reviews_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    try:
        _write_review_checkpoint(reviews_path, records)
    except Exception as exc:
        raise RuntimeError(
            f"Review {record['review_id']} was saved, but checkpoint creation "
            "failed. Integrity verification will not pass until the checkpoint "
            "is repaired."
        ) from exc

    return record




def list_review_history(
    finding_id: str,
    report_path: Path = DEFAULT_REPORT,
    reviews_path: Path = DEFAULT_REVIEWS,
    aliases_path: Path = DEFAULT_ALIASES,
) -> dict[str, Any]:
    """Show review history for a finding without rewriting historical records."""
    if not finding_id.strip():
        raise ValueError("Finding ID is required.")

    report = load_json(report_path)
    findings = report.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("Benchmark report findings must be a JSON array.")

    aliases_data = load_json(aliases_path)
    aliases = (
        aliases_data.get("aliases")
        if isinstance(aliases_data, dict)
        else aliases_data
    )
    if not isinstance(aliases, list):
        raise ValueError("Finding-ID aliases must be a JSON array.")

    reviews = list_reviews(reviews_path)

    matching_aliases = [
        item for item in aliases
        if isinstance(item, dict)
        and finding_id in (
            item.get("legacy_finding_id"),
            item.get("current_finding_id"),
        )
    ]

    related_ids = {finding_id}
    for alias in matching_aliases:
        related_ids.add(alias.get("legacy_finding_id"))
        related_ids.add(alias.get("current_finding_id"))
    related_ids.discard(None)

    matching_reviews = [
        item for item in reviews
        if isinstance(item, dict)
        and (
            item.get("finding_id") in related_ids
            or item.get("legacy_finding_id") in related_ids
        )
    ]

    matching_reviews.sort(
        key=lambda item: (
            str(item.get("reviewed_at", "")),
            str(item.get("review_id", "")),
        )
    )

    # Enrich the returned view only; never rewrite historical review records.
    enriched_reviews = []
    previous_review_id = None

    for sequence, item in enumerate(matching_reviews, start=1):
        enriched = dict(item)
        enriched.setdefault("review_sequence", sequence)
        enriched.setdefault("previous_review_id", previous_review_id)
        enriched.setdefault("audit_event", "REVIEW_RECORDED")
        enriched_reviews.append(enriched)
        previous_review_id = enriched.get("review_id")

    matching_findings = [
        item for item in findings
        if isinstance(item, dict)
        and item.get("finding_id") in related_ids
    ]

    return {
        "requested_finding_id": finding_id,
        "related_finding_ids": sorted(related_ids),
        "current_findings_found": [
            item.get("finding_id") for item in matching_findings
        ],
        "review_count": len(enriched_reviews),
        "reviews": enriched_reviews,
        "audit_trail_metadata": {
            "ordering": "reviewed_at_ascending_then_review_id",
            "sequence_scope": "returned_matching_reviews",
            "tamper_evident": False,
            "historical_records_rewritten": False,
        },
        "mapping_statuses": [
            {
                "legacy_finding_id": alias.get("legacy_finding_id"),
                "current_finding_id": alias.get("current_finding_id"),
                "link_status": alias.get("link_status"),
                "human_confirmation_required": (
                    alias.get("link_status")
                    == "PROVISIONAL_NEEDS_HUMAN_CONFIRMATION"
                ),
            }
            for alias in matching_aliases
        ],
        "evidence_verified": False,
        "compliance_certified": False,
        "payment_authorized": False,
        "funds_moved": False,
    }

def list_review_mappings(
    report_path: Path = DEFAULT_REPORT,
    reviews_path: Path = DEFAULT_REVIEWS,
    aliases_path: Path = DEFAULT_ALIASES,
) -> list[dict[str, Any]]:
    """Read-only view of legacy review IDs and their proposed current mappings."""
    report = load_json(report_path)
    findings = report.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("Benchmark report findings must be a JSON array.")

    aliases_data = load_json(aliases_path)
    aliases = (
        aliases_data.get("aliases")
        if isinstance(aliases_data, dict)
        else aliases_data
    )
    if not isinstance(aliases, list):
        raise ValueError("Finding-ID aliases must be a JSON array.")

    reviews = list_reviews(reviews_path)
    results = []

    for alias in aliases:
        if not isinstance(alias, dict):
            continue

        legacy_review_id = alias.get("legacy_review_id")
        legacy_review = next(
            (
                item for item in reviews
                if isinstance(item, dict)
                and item.get("review_id") == legacy_review_id
            ),
            None,
        )
        current_id = alias.get("current_finding_id")
        current_finding = next(
            (
                item for item in findings
                if isinstance(item, dict)
                and item.get("finding_id") == current_id
            ),
            None,
        )

        results.append({
            "legacy_finding_id": alias.get("legacy_finding_id"),
            "current_finding_id": current_id,
            "link_status": alias.get("link_status"),
            "basis": alias.get("basis"),
            "legacy_review_id": legacy_review_id,
            "legacy_review_found": legacy_review is not None,
            "legacy_review_decision": (
                legacy_review.get("decision") if legacy_review else None
            ),
            "legacy_review_finding_id": (
                legacy_review.get("finding_id") if legacy_review else None
            ),
            "current_finding_found": current_finding is not None,
            "human_confirmation_required": (
                alias.get("link_status")
                == "PROVISIONAL_NEEDS_HUMAN_CONFIRMATION"
            ),
            "evidence_verified": False,
            "compliance_certified": False,
            "payment_authorized": False,
            "funds_moved": False,
        })

    return results

def list_reviews(reviews_path: Path = DEFAULT_REVIEWS) -> list[dict[str, Any]]:
    if not reviews_path.exists():
        return []
    records = load_json(reviews_path)
    if not isinstance(records, list):
        raise ValueError("Review records file must contain a JSON array.")
    return records
