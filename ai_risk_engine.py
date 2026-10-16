from datetime import datetime, timezone


def _normalize_level(level):
    if not level:
        return "UNKNOWN"

    return str(level).upper()


def _calculate_ai_score(
    risk_signals=None,
    behavioral_anomalies=None,
    relationship_risk=None,
    transaction_history=None,
    transaction_velocity=None,
    trust_result=None
):
    score = 0

    for signal in risk_signals or []:
        severity = _normalize_level(
            signal.get("severity")
        )

        if severity == "HIGH":
            score += 35
        elif severity == "MEDIUM":
            score += 15
        elif severity == "LOW":
            score += 5

    for anomaly in behavioral_anomalies or []:
        severity = _normalize_level(
            anomaly.get("severity")
        )

        if severity == "HIGH":
            score += 30
        elif severity == "MEDIUM":
            score += 15
        elif severity == "LOW":
            score += 5

    if relationship_risk:
        level = _normalize_level(
            relationship_risk.get("risk_level")
        )

        if level == "HIGH":
            score += 35
        elif level == "MEDIUM":
            score += 20
        elif level == "LOW":
            score += 5

    if transaction_history:
        level = _normalize_level(
            transaction_history.get("risk_level")
        )

        if level == "HIGH":
            score += 25
        elif level == "MEDIUM":
            score += 15
        elif level == "LOW":
            score += 5

    if transaction_velocity:
        level = _normalize_level(
            transaction_velocity.get("risk_level")
        )

        if level == "HIGH":
            score += 30
        elif level == "MEDIUM":
            score += 15
        elif level == "LOW":
            score += 5

    if trust_result:
        level = _normalize_level(
            trust_result.get("trust_level")
        )

        if level == "LOW":
            score += 30
        elif level == "MEDIUM":
            score += 15
        elif level == "HIGH":
            score -= 10

    return max(0, min(100, score))


def _determine_risk_level(score):
    if score >= 70:
        return "HIGH"

    if score >= 40:
        return "MEDIUM"

    return "LOW"


def _build_reasons(
    risk_signals=None,
    behavioral_anomalies=None,
    relationship_risk=None,
    transaction_history=None,
    transaction_velocity=None,
    trust_result=None
):
    reasons = []

    for signal in risk_signals or []:
        severity = _normalize_level(
            signal.get("severity")
        )

        if severity in ("HIGH", "MEDIUM"):
            message = signal.get("message")

            if message:
                reasons.append(message)

    for anomaly in behavioral_anomalies or []:
        severity = _normalize_level(
            anomaly.get("severity")
        )

        if severity in ("HIGH", "MEDIUM"):
            message = anomaly.get("message")

            if message:
                reasons.append(message)

    if relationship_risk:
        level = _normalize_level(
            relationship_risk.get("risk_level")
        )

        if level in ("HIGH", "MEDIUM"):
            message = relationship_risk.get("message")

            if message:
                reasons.append(message)

    if transaction_history:
        level = _normalize_level(
            transaction_history.get("risk_level")
        )

        if level in ("HIGH", "MEDIUM"):
            message = transaction_history.get("message")

            if message:
                reasons.append(message)

    if transaction_velocity:
        level = _normalize_level(
            transaction_velocity.get("risk_level")
        )

        if level in ("HIGH", "MEDIUM"):
            message = transaction_velocity.get("message")

            if message:
                reasons.append(message)

    if trust_result:
        level = _normalize_level(
            trust_result.get("trust_level")
        )

        if level in ("LOW", "MEDIUM"):
            reasons.append(
                f"Beneficiary trust level is {level}"
            )

    unique_reasons = []

    for reason in reasons:
        if reason not in unique_reasons:
            unique_reasons.append(reason)

    return unique_reasons


def _determine_recommendation(risk_level, reasons):
    if risk_level == "HIGH":
        return "ENHANCED_VERIFICATION"

    if risk_level == "MEDIUM":
        return "REVIEW_TRANSACTION"

    if reasons:
        return "MONITOR_TRANSACTION"

    return "ALLOW_WITH_STANDARD_MONITORING"


def analyze_transaction_with_ai(
    transaction,
    risk_signals=None,
    behavioral_anomalies=None,
    relationship_risk=None,
    transaction_history=None,
    transaction_velocity=None,
    trust_result=None
):
    """
    TrustNG rule-weighted risk intelligence engine.

    This engine produces an advisory risk assessment.
    It does not authorize, execute, restrict, or release
    funds, and it cannot override TrustNG policy.

    Confidence is not statistically calibrated because
    this version does not use a trained predictive model.
    """

    score = _calculate_ai_score(
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        relationship_risk=relationship_risk,
        transaction_history=transaction_history,
        transaction_velocity=transaction_velocity,
        trust_result=trust_result
    )

    risk_level = _determine_risk_level(score)

    reasons = _build_reasons(
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        relationship_risk=relationship_risk,
        transaction_history=transaction_history,
        transaction_velocity=transaction_velocity,
        trust_result=trust_result
    )

    recommendation = _determine_recommendation(
        risk_level=risk_level,
        reasons=reasons
    )

    return {
        "engine": "TrustNG-AI-Risk-Intelligence",
        "version": "1.0",
        "analyzed_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "transaction_id": transaction.transaction_id,
        "ai_risk_score": score,
        "ai_risk_level": risk_level,
        "confidence": None,
        "confidence_status": "NOT_CALIBRATED",
        "reasons": reasons,
        "recommendation": recommendation,
        "authority": {
            "can_authorize_transaction": False,
            "can_execute_transaction": False,
            "can_release_funds": False,
            "can_override_policy": False,
            "final_decision_owner": (
                "TrustNG-Policy-and-Authorization-Layers"
            )
        }
    }
