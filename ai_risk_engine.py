from datetime import datetime


def _normalize_level(level):
    if not level:
        return "UNKNOWN"

    return str(level).upper()


def _calculate_ai_score(
    risk_signals,
    behavioral_anomalies,
    relationship_risk,
    transaction_history,
    transaction_velocity,
    trust_result
):
    score = 0

    # ----------------------------------------
    # 1. Base risk signals
    # ----------------------------------------

    for signal in risk_signals or []:
        severity = _normalize_level(signal.get("severity"))

        if severity == "HIGH":
            score += 35
        elif severity == "MEDIUM":
            score += 15
        elif severity == "LOW":
            score += 5

    # ----------------------------------------
    # 2. Behavioral anomalies
    # ----------------------------------------

    for anomaly in behavioral_anomalies or []:
        severity = _normalize_level(anomaly.get("severity"))

        if severity == "HIGH":
            score += 30
        elif severity == "MEDIUM":
            score += 15
        elif severity == "LOW":
            score += 5

    # ----------------------------------------
    # 3. Relationship / graph risk
    # ----------------------------------------

    relationship_level = _normalize_level(
        (relationship_risk or {}).get("risk_level")
    )

    if relationship_level == "HIGH":
        score += 35
    elif relationship_level == "MEDIUM":
        score += 20
    elif relationship_level == "LOW":
        score += 5

    # ----------------------------------------
    # 4. Transaction history
    # ----------------------------------------

    history_level = _normalize_level(
        (transaction_history or {}).get("risk_level")
    )

    if history_level == "HIGH":
        score += 25
    elif history_level == "MEDIUM":
        score += 15
    elif history_level == "LOW":
        score += 5

    # ----------------------------------------
    # 5. Transaction velocity
    # ----------------------------------------

    velocity_level = _normalize_level(
        (transaction_velocity or {}).get("risk_level")
    )

    if velocity_level == "HIGH":
        score += 30
    elif velocity_level == "MEDIUM":
        score += 15
    elif velocity_level == "LOW":
        score += 5

    # ----------------------------------------
    # 6. Beneficiary trust
    # ----------------------------------------

    trust_level = _normalize_level(
        (trust_result or {}).get("trust_level")
    )

    if trust_level == "LOW":
        score += 30
    elif trust_level == "MEDIUM":
        score += 15
    elif trust_level == "HIGH":
        score -= 10

    return max(0, min(score, 100))


def _determine_risk_level(score):
    if score >= 70:
        return "HIGH"

    if score >= 40:
        return "MEDIUM"

    return "LOW"


def _build_reasons(
    risk_signals,
    behavioral_anomalies,
    relationship_risk,
    transaction_history,
    transaction_velocity,
    trust_result
):
    reasons = []

    for signal in risk_signals or []:
        severity = _normalize_level(signal.get("severity"))

        if severity in ["HIGH", "MEDIUM"]:
            message = signal.get("message")

            if message:
                reasons.append(message)

    for anomaly in behavioral_anomalies or []:
        severity = _normalize_level(anomaly.get("severity"))

        if severity in ["HIGH", "MEDIUM"]:
            message = anomaly.get("message")

            if message:
                reasons.append(message)

    relationship_message = (relationship_risk or {}).get("message")

    if relationship_message:
        reasons.append(relationship_message)

    history_message = (transaction_history or {}).get("message")

    if history_message:
        reasons.append(history_message)

    velocity_message = (transaction_velocity or {}).get("message")

    if velocity_message:
        reasons.append(velocity_message)

    trust_level = _normalize_level(
        (trust_result or {}).get("trust_level")
    )

    if trust_level == "LOW":
        reasons.append(
            "Beneficiary trust level is LOW"
        )

    elif trust_level == "MEDIUM":
        reasons.append(
            "Beneficiary trust level is MEDIUM"
        )

    # Remove duplicate reasons while preserving order.
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
    TrustNG AI Risk Intelligence Engine.

    This component does NOT execute, authorize,
    restrict, or release money.

    It analyzes evidence produced by TrustNG's
    security systems and produces an AI-style
    risk assessment and recommendation.
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

    if risk_level == "HIGH":
        confidence = "HIGH"
    elif risk_level == "MEDIUM":
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "engine": "TrustNG-AI-Risk-Intelligence",
        "version": "1.0",
        "analyzed_at": datetime.utcnow().isoformat(),

        "transaction_id": transaction.transaction_id,

        "ai_risk_score": score,
        "ai_risk_level": risk_level,
        "confidence": confidence,

        "reasons": reasons,

        "recommendation": recommendation,

        "authority": {
            "can_authorize_transaction": False,
            "can_execute_transaction": False,
            "can_release_funds": False,
            "can_override_policy": False,
            "final_decision_owner": "TrustNG-Policy-and-Authorization-Layers"
        }
    }