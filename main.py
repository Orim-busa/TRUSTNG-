import os
import secrets
from contextlib import asynccontextmanager

import database

from fastapi import FastAPI, Header, HTTPException

from models import Transaction
from risk_engine import analyze_transaction
from policy_engine import evaluate_transaction
from restriction_engine import create_restriction
from beneficiary_profiles import get_beneficiary_profile
from adaptive_trust import calculate_trust
from authorization_engine import create_authorization
from execution_gate import validate_execution
from transaction_executor import execute_transaction
from behavioral_anomaly import analyze_behavioral_anomaly

from idempotency import (
    check_transaction,
    check_transaction_integrity,
    store_transaction,
    database_mode_enabled,
)

from fraud_cases import (
    create_fraud_case,
    get_fraud_case,
    get_cases_for_transaction,
    list_fraud_cases,
    add_investigation_note,
    record_investigation_action,
    resolve_fraud_case,
    dismiss_fraud_case,
    get_case_statistics,
    get_case_audit_history
)

from audit_store import verify_all_audit_events

from trust_graph import (
    record_transaction,
    analyze_relationship_risk,
    analyze_transaction_history,
    analyze_transaction_velocity
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if database_mode_enabled():
        database.initialize_database()
    yield


app = FastAPI(
    title="TrustNG",
    description="TrustNG transaction risk and policy infrastructure",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {
        "service": "TrustNG",
        "status": "running",
        "version": "1.0.0"
    }


@app.post("/evaluate")
def evaluate(transaction: Transaction):

    idempotency_check = check_transaction_integrity(
        transaction
    )

    if idempotency_check:

        if idempotency_check["status"] == "REPLAY":

            transaction_id = idempotency_check[
                "transaction_id"
            ]

            stored_record = check_transaction(
                transaction_id
            )

            if stored_record:
                return {
                    "transaction_id": transaction_id,
                    "status": "REPLAY",
                    "message": (
                        "Transaction has already "
                        "been processed"
                    ),
                    "previous_result": stored_record[
                        "result"
                    ]
                }

        if idempotency_check["status"] == "ID_REUSE":

            return {
                "transaction_id": transaction.transaction_id,
                "status": "BLOCKED",
                "message": (
                    "Transaction ID has already been "
                    "used with different transaction data"
                ),
                "reason": idempotency_check[
                    "reason"
                ]
            }

        if idempotency_check["status"] == "INVALID":

            return {
                "status": "BLOCKED",
                "message": idempotency_check[
                    "reason"
                ]
            }

    graph_record = record_transaction(
        transaction
    )

    risk_signals = analyze_transaction(
        transaction
    )

    relationship_risk = analyze_relationship_risk(
        transaction.sender
    )

    sender_history = analyze_transaction_history(
        transaction.sender,
        window_minutes=60
    )

    beneficiary_history = analyze_transaction_history(
        transaction.receiver,
        window_minutes=60
    )

    sender_velocity = analyze_transaction_velocity(
        transaction.sender,
        window_minutes=60
    )

    beneficiary_velocity = analyze_transaction_velocity(
        transaction.receiver,
        window_minutes=60
    )

    if relationship_risk:
        risk_signals.extend(
            relationship_risk
        )

    if sender_velocity:
        risk_signals.append(
            sender_velocity
        )

    if beneficiary_velocity:
        risk_signals.append(
            beneficiary_velocity
        )

    beneficiary_profile = get_beneficiary_profile(
        transaction.receiver
    )

    behavioral_anomalies = analyze_behavioral_anomaly(
        transaction,
        beneficiary_profile
    )

    if behavioral_anomalies:
        risk_signals.extend(
            behavioral_anomalies
        )

    trust_result = calculate_trust(
        transaction,
        beneficiary_profile
    )

    decision = evaluate_transaction(
        transaction,
        risk_signals,
        trust_result
    )

    restriction = None

    if decision["decision"] == "RESTRICT":

        restriction = create_restriction(
            account_reference=transaction.sender,
            restrictions=decision["restrictions"],
            reason="; ".join(
                decision["reasons"]
            ),
            risk_level=decision["risk_level"],
            policy=decision["policy"],
            policy_version=decision["policy_version"]
        )

    authorization = create_authorization(
        transaction_id=transaction.transaction_id,
        sender=transaction.sender,
        receiver=transaction.receiver,
        asset=transaction.asset,
        amount=transaction.amount,
        channel=transaction.channel,
        country=transaction.country,
        device_id=transaction.device_id,
        decision=decision["decision"],
        risk_level=decision["risk_level"],
        trust_level=trust_result["trust_level"],
        restrictions=decision["restrictions"]
    )

    execution_check = validate_execution(
        transaction=transaction,
        authorization=authorization,
        restriction=restriction
    )

    execution_result = execute_transaction(
        transaction=transaction,
        execution_check=execution_check
    )

    response = {

        "transaction_id": transaction.transaction_id,

        "graph": {

            "record": graph_record,

            "relationship_risk": relationship_risk,

            "transaction_history": {

                "sender": {
                    "entity_id": transaction.sender,

                    "window_minutes": sender_history[
                        "window_minutes"
                    ],

                    "transaction_count": sender_history[
                        "transaction_count"
                    ],

                    "unique_senders": sender_history[
                        "unique_senders"
                    ],

                    "unique_receivers": sender_history[
                        "unique_receivers"
                    ],

                    "total_amount": sender_history[
                        "total_amount"
                    ]
                },

                "beneficiary": {
                    "entity_id": transaction.receiver,

                    "window_minutes": beneficiary_history[
                        "window_minutes"
                    ],

                    "transaction_count": beneficiary_history[
                        "transaction_count"
                    ],

                    "unique_senders": beneficiary_history[
                        "unique_senders"
                    ],

                    "unique_receivers": beneficiary_history[
                        "unique_receivers"
                    ],

                    "total_amount": beneficiary_history[
                        "total_amount"
                    ]
                }
            },

            "velocity": {
                "sender": sender_velocity,
                "beneficiary": beneficiary_velocity
            }
        },

        "behavioral_anomalies": behavioral_anomalies,

        "risk_signals": risk_signals,

        "trust": trust_result,

        "decision": decision,

        "restriction": restriction,

        "authorization": authorization,

        "execution_check": execution_check,

        "execution": execution_result
    }

    fraud_case = None

    high_risk_signal_exists = any(
        signal.get("severity") == "HIGH"
        for signal in risk_signals
    )

    high_behavioral_anomaly_exists = any(
        signal.get("severity") == "HIGH"
        for signal in behavioral_anomalies
    )

    meaningful_risk_exists = (
        decision["decision"] in [
            "REVIEW",
            "RESTRICT"
        ]
        or high_risk_signal_exists
        or high_behavioral_anomaly_exists
    )

    if meaningful_risk_exists:

        fraud_case = create_fraud_case(
            transaction=transaction,
            decision=decision["decision"],
            risk_level=decision["risk_level"],
            risk_signals=risk_signals,
            behavioral_anomalies=behavioral_anomalies,
            trust_result=trust_result,
            graph_result=response["graph"]
        )

    response["fraud_case"] = fraud_case

    store_transaction(
        transaction,
        response
    )

    return response


@app.get("/fraud-cases")
def get_all_fraud_cases(
    status: str = None,
    severity: str = None
):
    return {
        "cases": list_fraud_cases(
            status=status,
            severity=severity
        )
    }


@app.get("/fraud-cases/statistics")
def fraud_case_statistics():
    return get_case_statistics()


@app.get("/fraud-cases/{case_id}")
def get_single_fraud_case(
    case_id: str
):
    case = get_fraud_case(
        case_id
    )

    if case is None:
        return {
            "success": False,
            "reason": "Fraud case not found"
        }

    return {
        "success": True,
        "case": case
    }


@app.get("/transactions/{transaction_id}/fraud-cases")
def get_transaction_fraud_cases(
    transaction_id: str
):
    return {
        "transaction_id": transaction_id,
        "cases": get_cases_for_transaction(
            transaction_id
        )
    }


@app.post("/fraud-cases/{case_id}/notes")
def add_case_note(
    case_id: str,
    note: str,
    investigator: str = None
):
    return add_investigation_note(
        case_id=case_id,
        note=note,
        investigator=investigator
    )


@app.post("/fraud-cases/{case_id}/actions")
def add_case_action(
    case_id: str,
    action: str,
    investigator: str = None
):
    return record_investigation_action(
        case_id=case_id,
        action=action,
        investigator=investigator
    )


@app.post("/fraud-cases/{case_id}/resolve")
def resolve_case(
    case_id: str,
    resolution: str,
    investigator: str = None
):
    return resolve_fraud_case(
        case_id=case_id,
        resolution=resolution,
        investigator=investigator
    )


@app.post("/fraud-cases/{case_id}/dismiss")
def dismiss_case(
    case_id: str,
    reason: str,
    investigator: str = None
):
    return dismiss_fraud_case(
        case_id=case_id,
        reason=reason,
        investigator=investigator
    )


@app.get("/fraud-cases/{case_id}/audit")
def get_fraud_case_audit(
    case_id: str
):
    return get_case_audit_history(
        case_id=case_id
    )


@app.get("/audit/integrity")
def verify_audit_integrity():
    return verify_all_audit_events()

@app.get("/v1/health")
def developer_api_health():
    database_status = "not_configured"

    if database_mode_enabled():
        try:
            database_status = (
                "connected"
                if database.check_database_connection()
                else "unavailable"
            )
        except Exception:
            database_status = "unavailable"

    return {
        "service": "TrustNG Developer API",
        "status": "running",
        "version": "1.0.0",
        "database": database_status,
    }


@app.post("/v1/transactions/check")
def developer_transaction_check(
    transaction: Transaction,
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
):
    configured_key = os.environ.get("TRUSTNG_API_KEY")

    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="Developer API is not configured with an API key."
        )

    if not x_api_key or not secrets.compare_digest(
        x_api_key,
        configured_key
    ):
        raise HTTPException(
            status_code=401,
            detail="A valid X-API-Key is required."
        )

    result = evaluate(transaction)
    policy_decision = result.get("decision", {})

    return {
        "transaction_id": result.get("transaction_id"),
        "decision": policy_decision.get("decision"),
        "risk_level": policy_decision.get("risk_level"),
        "action": policy_decision.get("action"),
        "reasons": policy_decision.get("reasons", []),
        "trust": result.get("trust"),
        "analysis": result
    }


@app.middleware("http")
async def protect_internal_routes(request, call_next):
    from starlette.responses import JSONResponse

    public_paths = {
        "/",
        "/v1/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/docs/oauth2-redirect"
    }

    if request.url.path in public_paths:
        return await call_next(request)

    configured_key = os.environ.get("TRUSTNG_API_KEY")

    if not configured_key:
        return JSONResponse(
            status_code=503,
            content={"detail": "API is not configured with a key."}
        )

    provided_key = request.headers.get("X-API-Key")

    if not provided_key or not secrets.compare_digest(
        provided_key,
        configured_key
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "A valid X-API-Key is required."}
        )

    return await call_next(request)
