import json
import os
from datetime import datetime


AUDIT_FILE = "trustng_audit_log.json"


def _load_audit_log():
    if not os.path.exists(AUDIT_FILE):
        return []

    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

            if isinstance(data, list):
                return data

            return []

    except (json.JSONDecodeError, OSError):
        return []


def _save_audit_log(events):
    temporary_file = AUDIT_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(events, file, indent=2)

    os.replace(temporary_file, AUDIT_FILE)


def append_audit_event(event):
    events = _load_audit_log()

    stored_event = dict(event)

    stored_event["stored_at"] = datetime.utcnow().isoformat()

    events.append(stored_event)

    _save_audit_log(events)

    return stored_event


def get_audit_events():
    return _load_audit_log()


def get_audit_events_for_case(case_id):
    events = _load_audit_log()

    return [
        event
        for event in events
        if event.get("case_id") == case_id
    ]


def get_audit_events_for_transaction(transaction_id):
    events = _load_audit_log()

    return [
        event
        for event in events
        if event.get("transaction_id") == transaction_id
    ]


def get_audit_event_count():
    events = _load_audit_log()

    return len(events)


def verify_audit_event(event):
    from audit_integrity import create_audit_fingerprint

    event_type = event.get("event_type")
    case_id = event.get("case_id")

    actor = (
        event.get("investigator")
        or event.get("actor")
        or "UNKNOWN"
    )

    content = (
        event.get("note")
        or event.get("action")
        or event.get("resolution")
        or ""
    )

    stored_fingerprint = event.get("audit_fingerprint")

    if not stored_fingerprint:
        return {
            "valid": False,
            "reason": "Audit fingerprint is missing"
        }

    expected_fingerprint = create_audit_fingerprint(
        event_type=event_type,
        case_id=case_id,
        actor=actor,
        content=content
    )

    if stored_fingerprint != expected_fingerprint:
        return {
            "valid": False,
            "reason": "Audit event integrity check failed"
        }

    return {
        "valid": True,
        "reason": "Audit event integrity verified"
    }


def verify_all_audit_events():
    events = _load_audit_log()

    results = []

    for event in events:
        verification = verify_audit_event(event)

        results.append({
            "case_id": event.get("case_id"),
            "event_type": event.get("event_type"),
            "stored_at": event.get("stored_at"),
            "valid": verification["valid"],
            "reason": verification["reason"]
        })

    invalid_events = [
        result
        for result in results
        if not result["valid"]
    ]

    return {
        "total_events": len(results),
        "valid_events": len(results) - len(invalid_events),
        "invalid_events": len(invalid_events),
        "integrity_status": (
            "COMPROMISED"
            if invalid_events
            else "INTEGRITY_VERIFIED"
        ),
        "events": results
    }