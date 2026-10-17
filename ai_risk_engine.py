from datetime import datetime, timezone


def _normalize_level(level):
    if not level:
        return "UNKNOWN"
    return str(level).upper()


def _signal_points(severity):
    return {
        "HIGH": 35,
        "MEDIUM": 15,
        "LOW": 5,
    }.get(_normalize_level(severity), 0)


def _calculate_history_score(transaction_history):
    if not isinstance(transaction_history, dict):
        return 0

    count = transaction_history.get("transaction_count", 0)
    senders = transaction_history.get("unique_senders", 0)
    receivers = transaction_history.get("unique_receivers", 0)

    if not isinstance(count, (int, float)) or isinstance(count, bool) or count < 0:
        return 0

    if not isinstance(senders, (int, float)) or isinstance(senders, bool) or senders < 0:
        senders = 0

    if not isinstance(receivers, (int, float)) or isinstance(receivers, bool) or receivers < 0:
        receivers = 0

    if count >= 10:
        return 25
    if count >= 5:
        return 15
    if count >= 3 and (senders >= 3 or receivers >= 3):
        return 10

    return 0


def _signal_identity(signal):
    return (
        signal.get("type"),
        _normalize_level(signal.get("severity")),
        signal.get("entity"),
        signal.get("message"),
    )


def _collect_signals(
    risk_signals=None,
    behavioral_anomalies=None,
    relationship_risk=None,
    transaction_velocity=None,
):
    collected = []
    seen = set()

    for group in (
        risk_signals,
        behavioral_anomalies,
        relationship_risk,
        transaction_velocity,
    ):
        if isinstance(group, dict):
            group = [group]

        for signal in group or []:
            if not isinstance(signal, dict):
                continue

            identity = _signal_identity(signal)

            if identity not in seen:
                seen.add(identity)
                collected.append(signal)

    return collected


def _normalize_histories(transaction_history=None, transaction_histories=None):
    histories = []
    for value in (transaction_history, transaction_histories):
        if isinstance(value, dict):
            histories.append(value)
        elif isinstance(value, (list, tuple)):
            histories.extend(item for item in value if isinstance(item, dict))
    return histories


def _has_velocity_signal(signals):
    return any("VELOCITY" in str(signal.get("type", "")).upper() for signal in signals)


def _calculate_ai_score(
    risk_signals=None,
    behavioral_anomalies=None,
    relationship_risk=None,
    transaction_history=None,
    transaction_velocity=None,
    trust_result=None,
    transaction_histories=None,
):
    signals = _collect_signals(
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        relationship_risk=relationship_risk,
        transaction_velocity=transaction_velocity,
    )

    score = sum(
        _signal_points(signal.get("severity"))
        for signal in signals
    )

    # Avoid counting the same recent activity twice.
    velocity_present = bool(transaction_velocity) or _has_velocity_signal(signals)
    if not velocity_present:
        history_scores = [
            _calculate_history_score(history)
            for history in _normalize_histories(transaction_history, transaction_histories)
        ]
        score += max(history_scores, default=0)

    if trust_result:
        level = _normalize_level(trust_result.get("trust_level"))

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
    trust_result=None,
    transaction_histories=None,
):
    reasons = []

    signals = _collect_signals(
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        relationship_risk=relationship_risk,
        transaction_velocity=transaction_velocity,
    )

    for signal in signals:
        if _normalize_level(signal.get("severity")) in ("HIGH", "MEDIUM"):
            message = signal.get("message")
            if message and message not in reasons:
                reasons.append(message)

    velocity_present = bool(transaction_velocity) or _has_velocity_signal(signals)
    if not velocity_present:
        for history in _normalize_histories(transaction_history, transaction_histories):
            if _calculate_history_score(history):
                count = history.get("transaction_count", 0)
                window = history.get("window_minutes", "unknown")
                reason = (
                    f"Recent transaction activity is elevated "
                    f"({count} transactions in {window} minutes)"
                )
                if reason not in reasons:
                    reasons.append(reason)

    if trust_result:
        level = _normalize_level(trust_result.get("trust_level"))
        if level in ("LOW", "MEDIUM"):
            reason = f"Beneficiary trust level is {level}"
            if reason not in reasons:
                reasons.append(reason)

    return reasons


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
    trust_result=None,
    transaction_histories=None,
):
    """
    Advisory rule-weighted assessment only.
    This is not a trained or statistically calibrated predictive model.
    TrustNG policy remains responsible for transaction decisions.
    """
    score = _calculate_ai_score(
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        relationship_risk=relationship_risk,
        transaction_history=transaction_history,
        transaction_velocity=transaction_velocity,
        trust_result=trust_result,
        transaction_histories=transaction_histories,
    )

    risk_level = _determine_risk_level(score)

    reasons = _build_reasons(
        risk_signals=risk_signals,
        behavioral_anomalies=behavioral_anomalies,
        relationship_risk=relationship_risk,
        transaction_history=transaction_history,
        transaction_velocity=transaction_velocity,
        trust_result=trust_result,
        transaction_histories=transaction_histories,
    )

    return {
        "engine": "TrustNG-AI-Risk-Intelligence",
        "version": "1.0",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "transaction_id": transaction.transaction_id,
        "ai_risk_score": score,
        "ai_risk_level": risk_level,
        "confidence": None,
        "confidence_status": "NOT_CALIBRATED",
        "reasons": reasons,
        "recommendation": _determine_recommendation(risk_level, reasons),
        "authority": {
            "can_authorize_transaction": False,
            "can_execute_transaction": False,
            "can_release_funds": False,
            "can_override_policy": False,
            "final_decision_owner": "TrustNG-Policy-and-Authorization-Layers",
        },
    }
