
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import database
import dashboard_service
import research_promotion

from fastapi import FastAPI, Header, HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from models import Transaction, ResearchCandidateReview
from risk_engine import analyze_transaction
from policy_engine import evaluate_transaction
from restriction_engine import create_restriction
from beneficiary_profiles import get_beneficiary_profile
from adaptive_trust import calculate_trust
from behavioral_anomaly import analyze_behavioral_anomaly
from ai_risk_engine import analyze_transaction_with_ai

from idempotency import (
    check_transaction,
    reserve_transaction,
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
    get_case_audit_history,
)

from audit_store import verify_all_audit_events

from trust_graph import (
    record_transaction,
    analyze_relationship_risk,
    analyze_transaction_history,
    analyze_transaction_velocity,
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
        "version": "1.0.0",
    }


@app.get("/dashboard", response_class=HTMLResponse)
def browser_dashboard():
    page = Path(__file__).with_name("dashboard.html")
    return HTMLResponse(
        content=page.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/v1/dashboard/summary")
def dashboard_summary():
    """Read-only operational and research summary."""
    return dashboard_service.dashboard_summary()


@app.get("/v1/dashboard/research")
def dashboard_research(limit: int = 50):
    """Read-only ranked research candidates."""
    if not 1 <= limit <= 200:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 200.",
        )

    candidates = dashboard_service.research_collector.list_candidates()
    ranked = dashboard_service.research_analyzer.rank_candidates(
        candidates,
        include_reviewed=True,
    )

    return {
        "total": len(ranked),
        "items": ranked[:limit],
        "ranking_is_independent_verification": False,
    }


@app.post("/v1/research/candidates/{candidate_id}/review")
def review_research_candidate(
    candidate_id: str,
    review: ResearchCandidateReview,
):
    """Record a human review without triggering implementation."""
    try:
        return dashboard_service.research_collector.mark_candidate_reviewed(
            candidate_id,
            evidence_status=review.evidence_status,
            trustng_relevance=review.trustng_relevance,
            lesson_for_africa=review.lesson_for_africa,
            reviewer=review.reviewer,
            notes=review.notes,
        )
    except ValueError as exc:
        status_code = (
            404 if str(exc) == "Unknown research candidate." else 400
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc


@app.post("/v1/research/candidates/{candidate_id}/promote")
def promote_research_candidate(candidate_id: str):
    """Promote eligible research after human review and verification."""
    try:
        return research_promotion.promote_candidate(candidate_id)
    except ValueError as exc:
        status_code = (
            404 if str(exc) == "Unknown research candidate." else 400
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(exc),
        ) from exc


@app.get("/v1/dashboard/proposals")
def dashboard_proposals():
    """Read-only list of improvement proposals."""
    return dashboard_service.continuous_intelligence.list_proposals()


@app.get("/v1/dashboard/benchmarks")
def dashboard_benchmarks():
    """Read-only list of architecture benchmarks."""
    return dashboard_service.architecture_benchmark.list_benchmarks()


@app.post("/evaluate")
def evaluate(transaction: Transaction):
    transaction_id = transaction.transaction_id

    try:
        reservation_result = reserve_transaction(transaction)
    except Exception:
        # The reservation may have committed even if confirmation failed.
        # Never report a definite failure or allow a blind retry.
        return {
            "transaction_id": transaction_id,
            "status": "RECONCILIATION_REQUIRED",
            "message": (
                "Transaction reservation could not be confirmed. "
                "No payment execution was attempted. "
                "Check transaction status before retrying."
            ),
        }

    if reservation_result is not None:
        status = reservation_result.get("status")

        if status == "INVALID":
            return {
                "transaction_id": transaction_id,
                "status": "BLOCKED",
                "message": reservation_result.get(
                    "reason", "Transaction ID is missing"
                ),
            }

        if status == "ID_REUSE":
            return {
                "transaction_id": transaction_id,
                "status": "BLOCKED",
                "message": (
                    "Transaction ID has already been used "
                    "with different transaction data"
                ),
                "reason": reservation_result.get("reason"),
            }

        if status == "REPLAY":
            stored_record = check_transaction(transaction_id)
            previous_result = (
                stored_record.get("result") if stored_record else None
            )

            if (
                isinstance(previous_result, dict)
                and previous_result.get("status") == "PROCESSING"
            ):
                return {
                    "transaction_id": transaction_id,
                    "status": "PROCESSING",
                    "message": (
                        "A request with this transaction ID "
                        "is already being processed."
                    ),
                }

            return {
                "transaction_id": transaction_id,
                "status": "REPLAY",
                "message": "Transaction has already been processed",
                "previous_result": previous_result,
            }

        return {
            "transaction_id": transaction_id,
            "status": "BLOCKED",
            "message": (
                "Could not safely reserve this transaction. "
                "Check its status before retrying."
            ),
        }

    try:
        graph_record = record_transaction(transaction)
        risk_signals = analyze_transaction(transaction)

        relationship_risk = analyze_relationship_risk(transaction.sender)

        sender_history = analyze_transaction_history(
            transaction.sender,
            window_minutes=60,
        )
        beneficiary_history = analyze_transaction_history(
            transaction.receiver,
            window_minutes=60,
        )

        sender_velocity = analyze_transaction_velocity(
            transaction.sender,
            window_minutes=60,
        )
        beneficiary_velocity = analyze_transaction_velocity(
            transaction.receiver,
            window_minutes=60,
        )

        if relationship_risk:
            risk_signals.extend(relationship_risk)

        if sender_velocity:
            risk_signals.append(sender_velocity)

        if beneficiary_velocity:
            risk_signals.append(beneficiary_velocity)

        beneficiary_profile = get_beneficiary_profile(transaction.receiver)

        behavioral_anomalies = analyze_behavioral_anomaly(
            transaction,
            beneficiary_profile,
        )

        if behavioral_anomalies:
            risk_signals.extend(behavioral_anomalies)

        trust_result = calculate_trust(
            transaction,
            beneficiary_profile,
        )

        # Build the AI assessment from the available signals.
        # The AI assessment is advisory; policy remains authoritative.
        ai_assessment = analyze_transaction_with_ai(
            transaction=transaction,
            risk_signals=risk_signals,
            behavioral_anomalies=None,
            relationship_risk=None,
            transaction_history=None,
            transaction_velocity=[
                velocity
                for velocity in (sender_velocity, beneficiary_velocity)
                if velocity
            ],
            trust_result=trust_result,
            transaction_histories=[sender_history, beneficiary_history],
        )

        decision = evaluate_transaction(
            transaction,
            risk_signals,
            trust_result,
        )

        restriction = None

        if decision["decision"] == "RESTRICT":
            restriction = create_restriction(
                account_reference=transaction.sender,
                restrictions=decision["restrictions"],
                reason="; ".join(decision["reasons"]),
                risk_level=decision["risk_level"],
                policy=decision["policy"],
                policy_version=decision["policy_version"],
            )

        # Risk evaluation is not payment authorization or execution.
        # Keep these response fields for compatibility, but clearly indicate
        # that no execution gate, executor, or payment provider was called.
        authorization = None
        execution_check = {
            "execution_allowed": False,
            "status": "NOT_ATTEMPTED",
            "reason": "Risk evaluation does not authorize payment execution.",
        }
        execution_result = {
            "executed": False,
            "status": "NOT_ATTEMPTED",
            "simulation": False,
            "funds_moved": False,
            "message": (
                "Risk evaluation only. No executor or payment provider was called."
            ),
            "transaction_id": transaction.transaction_id,
        }

        response = {
            "transaction_id": transaction.transaction_id,
            "graph": {
                "record": graph_record,
                "relationship_risk": relationship_risk,
                "transaction_history": {
                    "sender": {
                        "entity_id": transaction.sender,
                        "window_minutes": sender_history["window_minutes"],
                        "transaction_count": sender_history["transaction_count"],
                        "unique_senders": sender_history["unique_senders"],
                        "unique_receivers": sender_history["unique_receivers"],
                        "total_amount": sender_history["total_amount"],
                    },
                    "beneficiary": {
                        "entity_id": transaction.receiver,
                        "window_minutes": beneficiary_history["window_minutes"],
                        "transaction_count": beneficiary_history["transaction_count"],
                        "unique_senders": beneficiary_history["unique_senders"],
                        "unique_receivers": beneficiary_history["unique_receivers"],
                        "total_amount": beneficiary_history["total_amount"],
                    },
                },
                "velocity": {
                    "sender": sender_velocity,
                    "beneficiary": beneficiary_velocity,
                },
            },
            "behavioral_anomalies": behavioral_anomalies,
            "risk_signals": risk_signals,
            "trust": trust_result,
            "ai_assessment": ai_assessment,
            "decision": decision,
            "restriction": restriction,
            "authorization": authorization,
            "execution_check": execution_check,
            "execution": execution_result,
        }

        high_risk_signal_exists = any(
            signal.get("severity") == "HIGH"
            for signal in risk_signals
        )

        high_behavioral_anomaly_exists = any(
            signal.get("severity") == "HIGH"
            for signal in behavioral_anomalies
        )

        meaningful_risk_exists = (
            decision["decision"] in ["REVIEW", "RESTRICT"]
            or high_risk_signal_exists
            or high_behavioral_anomaly_exists
        )

        fraud_case = None

        if meaningful_risk_exists:
            fraud_case = create_fraud_case(
                transaction=transaction,
                decision=decision["decision"],
                risk_level=decision["risk_level"],
                risk_signals=risk_signals,
                behavioral_anomalies=behavioral_anomalies,
                trust_result=trust_result,
                graph_result=response["graph"],
            )

        response["fraud_case"] = fraud_case

        store_transaction(transaction, response)

        return response

    except Exception:
        recovery_result = {
            "transaction_id": transaction_id,
            "status": "FAILED",
            "message": (
                "Evaluation failed before execution was attempted. "
                "Do not retry until this transaction status is checked."
            ),
        }
        try:
            store_transaction(transaction, recovery_result)
        except Exception:
            # Persistence failed. Never claim that recovery was recorded.
            return {
                "transaction_id": transaction_id,
                "status": "RECONCILIATION_REQUIRED",
                "message": (
                    "The transaction outcome or recovery record is uncertain. "
                    "Do not retry; investigate the transaction record."
                ),
            }
        return recovery_result


@app.get("/v1/reconciliation/pending")
def list_pending_reconciliation(
    older_than_minutes: int = 5,
    limit: int = 50,
):
    """List aged PENDING execution records for investigation."""
    if not 0 <= older_than_minutes <= 10080:
        raise HTTPException(
            status_code=400,
            detail="older_than_minutes must be between 0 and 10080.",
        )
    if not 1 <= limit <= 200:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 200.",
        )

    candidates = database.list_pending_transaction_executions(
        older_than_minutes=older_than_minutes,
        limit=limit,
    )
    return {
        "status": "OK",
        "count": len(candidates),
        "older_than_minutes": older_than_minutes,
        "items": candidates,
        "note": (
            "A PENDING record is an investigation candidate, not proof "
            "of payment success or failure. Check the payment provider "
            "before resolving an uncertain outcome."
        ),
    }


@app.get("/fraud-cases")
def get_all_fraud_cases(
    status: str = None,
    severity: str = None,
):
    return {
        "cases": list_fraud_cases(
            status=status,
            severity=severity,
        )
    }


@app.get("/fraud-cases/statistics")
def fraud_case_statistics():
    return get_case_statistics()


@app.get("/fraud-cases/{case_id}")
def get_single_fraud_case(case_id: str):
    case = get_fraud_case(case_id)

    if case is None:
        return {
            "success": False,
            "reason": "Fraud case not found",
        }

    return {
        "success": True,
        "case": case,
    }


@app.get("/transactions/{transaction_id}/fraud-cases")
def get_transaction_fraud_cases(transaction_id: str):
    return {
        "transaction_id": transaction_id,
        "cases": get_cases_for_transaction(transaction_id),
    }


@app.post("/fraud-cases/{case_id}/notes")
def add_case_note(
    case_id: str,
    note: str,
    investigator: str = None,
):
    return add_investigation_note(
        case_id=case_id,
        note=note,
        investigator=investigator,
    )


@app.post("/fraud-cases/{case_id}/actions")
def add_case_action(
    case_id: str,
    action: str,
    investigator: str = None,
):
    return record_investigation_action(
        case_id=case_id,
        action=action,
        investigator=investigator,
    )


@app.post("/fraud-cases/{case_id}/resolve")
def resolve_case(
    case_id: str,
    resolution: str,
    investigator: str = None,
):
    return resolve_fraud_case(
        case_id=case_id,
        resolution=resolution,
        investigator=investigator,
    )


@app.post("/fraud-cases/{case_id}/dismiss")
def dismiss_case(
    case_id: str,
    reason: str,
    investigator: str = None,
):
    return dismiss_fraud_case(
        case_id=case_id,
        reason=reason,
        investigator=investigator,
    )


@app.get("/fraud-cases/{case_id}/audit")
def get_fraud_case_audit(case_id: str):
    return get_case_audit_history(case_id=case_id)


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
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    configured_key = os.environ.get("TRUSTNG_API_KEY")

    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="Developer API is not configured with an API key.",
        )

    if not x_api_key or not secrets.compare_digest(
        x_api_key,
        configured_key,
    ):
        raise HTTPException(
            status_code=401,
            detail="A valid X-API-Key is required.",
        )

    result = evaluate(transaction)
    summary_result = result

    if result.get("status") == "REPLAY":
        previous_result = result.get("previous_result")
        if isinstance(previous_result, dict):
            summary_result = previous_result

    policy_decision = summary_result.get("decision") or {}

    return {
        "transaction_id": result.get("transaction_id"),
        "decision": policy_decision.get("decision"),
        "risk_level": policy_decision.get("risk_level"),
        "action": policy_decision.get("action"),
        "reasons": policy_decision.get("reasons", []),
        "trust": summary_result.get("trust"),
        "analysis": result,
    }


@app.middleware("http")
async def protect_internal_routes(request, call_next):
    from starlette.responses import JSONResponse

    public_paths = {
        "/",
        "/v1/health",
        "/dashboard",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/docs/oauth2-redirect",
    }

    if request.url.path in public_paths:
        return await call_next(request)

    configured_key = os.environ.get("TRUSTNG_API_KEY")

    if not configured_key:
        return JSONResponse(
            status_code=503,
            content={"detail": "API is not configured with a key."},
        )

    provided_key = request.headers.get("X-API-Key")

    if not provided_key or not secrets.compare_digest(
        provided_key,
        configured_key,
    ):
        return JSONResponse(
            status_code=401,
            content={"detail": "A valid X-API-Key is required."},
        )

    return await call_next(request)


# Document the API-key requirement enforced by protect_internal_routes.
# The middleware remains the actual authentication enforcement layer.
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schema.setdefault("components", {}).setdefault(
        "securitySchemes", {}
    )["APIKeyHeader"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "Required for protected endpoints. "
            "Use the API key supplied by the TrustNG operator."
        ),
    }

    public_paths = {
        "/",
        "/v1/health",
        "/dashboard",
    }

    for path, methods in schema.get("paths", {}).items():
        for operation in methods.values():
            if not isinstance(operation, dict):
                continue

            if path in public_paths:
                operation["security"] = []
            else:
                operation["security"] = [{"APIKeyHeader": []}]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
