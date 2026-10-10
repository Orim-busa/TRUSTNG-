from datetime import datetime
import uuid

from audit_integrity import (
    find_duplicate_audit_event,
    attach_audit_fingerprint
)

from audit_store import append_audit_event


FRAUD_CASES = {}

CASE_STATUS_OPEN = "OPEN"
CASE_STATUS_UNDER_REVIEW = "UNDER_REVIEW"
CASE_STATUS_RESOLVED = "RESOLVED"
CASE_STATUS_DISMISSED = "DISMISSED"


def determine_case_severity(
    decision=None,
    risk_level=None,
    risk_signals=None,
    behavioral_anomalies=None
):
    risk_level = str(risk_level or "").upper()

    if risk_level == "HIGH":
        return "HIGH"

    for signal in risk_signals or []:
        if str(signal.get("severity", "")).upper() == "HIGH":
            return "HIGH"

    for anomaly in behavioral_anomalies or []:
        if str(anomaly.get("severity", "")).upper() == "HIGH":
            return "HIGH"

    if str(decision or "").upper() == "RESTRICT":
        return "HIGH"

    if str(decision or "").upper() == "REVIEW":
        return "MEDIUM"

    return "LOW"


def create_evidence(
    transaction,
    decision,
    risk_level,
    risk_signals,
    behavioral_anomalies,
    trust_result=None,
    graph_result=None
):
    return {
        "transaction": transaction.model_dump()
        if hasattr(transaction, "model_dump")
        else transaction.dict(),

        "decision": decision,
        "risk_level": risk_level,

        "risk_signals": risk_signals or [],

        "behavioral_anomalies": behavioral_anomalies or [],

        "trust": trust_result,

        "graph": graph_result,

        "captured_at": datetime.utcnow().isoformat()
    }


def create_fraud_case(
    transaction,
    decision,
    risk_level,
    risk_signals,
    behavioral_anomalies,
    trust_result=None,
    graph_result=None
):
    case_id = f"CASE-{uuid.uuid4().hex[:10].upper()}"

    now = datetime.utcnow().isoformat()

    severity = determine_case_severity(
        decision=decision,
        risk_level=risk_level,
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies
    )

    evidence = create_evidence(
        transaction=transaction,
        decision=decision,
        risk_level=risk_level,
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        trust_result=trust_result,
        graph_result=graph_result
    )

    case = {
        "case_id": case_id,
        "transaction_id": transaction.transaction_id,
        "status": CASE_STATUS_OPEN,
        "severity": severity,

        "created_at": now,
        "updated_at": now,

        "evidence": evidence,

        "investigation": {
            "notes": [],
            "actions": []
        },

        "resolution": None
    }

    FRAUD_CASES[case_id] = case

    return case


def get_fraud_case(case_id):
    return FRAUD_CASES.get(case_id)


def get_cases_for_transaction(transaction_id):
    return [
        case
        for case in FRAUD_CASES.values()
        if case.get("transaction_id") == transaction_id
    ]


def list_fraud_cases(status=None, severity=None):
    cases = list(FRAUD_CASES.values())

    if status:
        status = status.upper()

        cases = [
            case
            for case in cases
            if case.get("status") == status
        ]

    if severity:
        severity = severity.upper()

        cases = [
            case
            for case in cases
            if case.get("severity") == severity
        ]

    return cases


def add_investigation_note(
    case_id,
    note,
    investigator=None
):
    case = get_fraud_case(case_id)

    if not case:
        return {
            "success": False,
            "reason": "Fraud case not found",
            "case_id": case_id
        }

    investigator_name = investigator or "UNKNOWN"

    duplicate = find_duplicate_audit_event(
        events=case["investigation"]["notes"],
        event_type="NOTE",
        case_id=case_id,
        actor=investigator_name,
        content=note
    )

    if duplicate:
        return {
            "success": False,
            "reason": "Duplicate investigation note detected",
            "case_id": case_id
        }

    now = datetime.utcnow().isoformat()

    event = {
        "timestamp": now,
        "investigator": investigator_name,
        "note": note,
        "case_id": case_id,
        "event_type": "NOTE"
    }

    attach_audit_fingerprint(
        event=event,
        event_type="NOTE",
        case_id=case_id,
        actor=investigator_name,
        content=note
    )

    case["investigation"]["notes"].append(event)

    append_audit_event(event)

    case["status"] = CASE_STATUS_UNDER_REVIEW
    case["updated_at"] = now

    return {
        "success": True,
        "case_id": case_id,
        "status": case["status"],
        "note": event
    }


def record_investigation_action(
    case_id,
    action,
    investigator=None
):
    case = get_fraud_case(case_id)

    if not case:
        return {
            "success": False,
            "reason": "Fraud case not found",
            "case_id": case_id
        }

    investigator_name = investigator or "UNKNOWN"

    duplicate = find_duplicate_audit_event(
        events=case["investigation"]["actions"],
        event_type="ACTION",
        case_id=case_id,
        actor=investigator_name,
        content=action
    )

    if duplicate:
        return {
            "success": False,
            "reason": "Duplicate investigation action detected",
            "case_id": case_id
        }

    now = datetime.utcnow().isoformat()

    event = {
        "timestamp": now,
        "investigator": investigator_name,
        "action": action,
        "case_id": case_id,
        "event_type": "ACTION"
    }

    attach_audit_fingerprint(
        event=event,
        event_type="ACTION",
        case_id=case_id,
        actor=investigator_name,
        content=action
    )

    case["investigation"]["actions"].append(event)

    append_audit_event(event)

    case["status"] = CASE_STATUS_UNDER_REVIEW
    case["updated_at"] = now

    return {
        "success": True,
        "case_id": case_id,
        "status": case["status"],
        "action": event
    }


def resolve_fraud_case(
    case_id,
    resolution,
    investigator=None
):
    case = get_fraud_case(case_id)

    if not case:
        return {
            "success": False,
            "reason": "Fraud case not found",
            "case_id": case_id
        }

    investigator_name = investigator or "UNKNOWN"
    now = datetime.utcnow().isoformat()

    case["status"] = CASE_STATUS_RESOLVED

    case["resolution"] = {
        "status": "RESOLVED",
        "resolution": resolution,
        "investigator": investigator_name,
        "resolved_at": now
    }

    case["updated_at"] = now

    event = {
        "timestamp": now,
        "investigator": investigator_name,
        "action": "CASE_RESOLVED",
        "case_id": case_id,
        "event_type": "RESOLUTION",
        "resolution": resolution
    }

    attach_audit_fingerprint(
        event=event,
        event_type="RESOLUTION",
        case_id=case_id,
        actor=investigator_name,
        content=resolution
    )

    append_audit_event(event)

    return {
        "success": True,
        "case_id": case_id,
        "status": case["status"],
        "resolution": case["resolution"]
    }


def dismiss_fraud_case(
    case_id,
    reason,
    investigator=None
):
    case = get_fraud_case(case_id)

    if not case:
        return {
            "success": False,
            "reason": "Fraud case not found",
            "case_id": case_id
        }

    investigator_name = investigator or "UNKNOWN"
    now = datetime.utcnow().isoformat()

    case["status"] = CASE_STATUS_DISMISSED

    case["resolution"] = {
        "status": "DISMISSED",
        "reason": reason,
        "investigator": investigator_name,
        "dismissed_at": now
    }

    case["updated_at"] = now

    event = {
        "timestamp": now,
        "investigator": investigator_name,
        "action": "CASE_DISMISSED",
        "case_id": case_id,
        "event_type": "RESOLUTION",
        "resolution": reason
    }

    attach_audit_fingerprint(
        event=event,
        event_type="RESOLUTION",
        case_id=case_id,
        actor=investigator_name,
        content=reason
    )

    append_audit_event(event)

    return {
        "success": True,
        "case_id": case_id,
        "status": case["status"],
        "resolution": case["resolution"]
    }


def get_case_statistics():
    cases = list(FRAUD_CASES.values())

    statistics = {
        "total_cases": len(cases),
        "open_cases": 0,
        "under_review_cases": 0,
        "resolved_cases": 0,
        "dismissed_cases": 0,
        "high_severity_cases": 0,
        "medium_severity_cases": 0,
        "low_severity_cases": 0
    }

    for case in cases:
        status = case.get("status")
        severity = case.get("severity")

        if status == CASE_STATUS_OPEN:
            statistics["open_cases"] += 1

        elif status == CASE_STATUS_UNDER_REVIEW:
            statistics["under_review_cases"] += 1

        elif status == CASE_STATUS_RESOLVED:
            statistics["resolved_cases"] += 1

        elif status == CASE_STATUS_DISMISSED:
            statistics["dismissed_cases"] += 1

        if severity == "HIGH":
            statistics["high_severity_cases"] += 1

        elif severity == "MEDIUM":
            statistics["medium_severity_cases"] += 1

        elif severity == "LOW":
            statistics["low_severity_cases"] += 1

    return statistics


def get_case_audit_history(case_id):
    case = get_fraud_case(case_id)

    if not case:
        return {
            "success": False,
            "reason": "Fraud case not found",
            "case_id": case_id
        }

    return {
        "success": True,
        "case_id": case_id,
        "status": case["status"],
        "created_at": case["created_at"],
        "updated_at": case["updated_at"],
        "investigation": case["investigation"],
        "resolution": case["resolution"]
    }