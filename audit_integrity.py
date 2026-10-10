import hashlib


def create_audit_fingerprint(event_type, case_id, actor, content):
    """
    Create a unique fingerprint for an investigation event.

    The fingerprint allows TrustNG to detect when the
    same investigator tries to record the exact same
    event more than once.
    """

    normalized_event = str(event_type).strip().upper()
    normalized_case = str(case_id).strip()
    normalized_actor = str(actor or "").strip()
    normalized_content = str(content).strip()

    raw_data = (
        f"{normalized_event}|"
        f"{normalized_case}|"
        f"{normalized_actor}|"
        f"{normalized_content}"
    )

    return hashlib.sha256(raw_data.encode("utf-8")).hexdigest()


def find_duplicate_audit_event(events, event_type, case_id, actor, content):
    """
    Check whether the same audit event already exists.

    Returns:
        True  -> duplicate found
        False -> no duplicate found
    """

    fingerprint = create_audit_fingerprint(
        event_type=event_type,
        case_id=case_id,
        actor=actor,
        content=content
    )

    for event in events:
        if event.get("audit_fingerprint") == fingerprint:
            return True

    return False


def attach_audit_fingerprint(
    event,
    event_type,
    case_id,
    actor,
    content
):
    """
    Add a tamper-detection fingerprint to an audit event.
    """

    event["audit_fingerprint"] = create_audit_fingerprint(
        event_type=event_type,
        case_id=case_id,
        actor=actor,
        content=content
    )

    return event