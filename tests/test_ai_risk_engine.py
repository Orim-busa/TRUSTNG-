from types import SimpleNamespace

from ai_risk_engine import analyze_transaction_with_ai


def make_transaction():
    return SimpleNamespace(transaction_id="tx-ai-test")


def test_low_risk_transaction():
    result = analyze_transaction_with_ai(
        transaction=make_transaction()
    )

    assert result["ai_risk_score"] == 0
    assert result["ai_risk_level"] == "LOW"
    assert result["recommendation"] == "ALLOW_WITH_STANDARD_MONITORING"


def test_medium_risk_transaction():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        risk_signals=[
            {
                "severity": "HIGH",
                "message": "Unusual transaction pattern",
            }
        ],
        trust_result={"trust_level": "LOW"},
    )

    assert result["ai_risk_score"] == 65
    assert result["ai_risk_level"] == "MEDIUM"
    assert result["recommendation"] == "REVIEW_TRANSACTION"
    assert "Unusual transaction pattern" in result["reasons"]


def test_high_risk_transaction():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        risk_signals=[
            {"severity": "HIGH", "message": "Risk signal one"},
            {"severity": "HIGH", "message": "Risk signal two"},
        ],
    )

    assert result["ai_risk_score"] == 70
    assert result["ai_risk_level"] == "HIGH"
    assert result["recommendation"] == "ENHANCED_VERIFICATION"


def test_score_never_exceeds_100():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        risk_signals=[
            {"severity": "HIGH", "message": "Risk one"},
            {"severity": "HIGH", "message": "Risk two"},
            {"severity": "HIGH", "message": "Risk three"},
        ],
    )

    assert result["ai_risk_score"] == 100


def test_confidence_is_not_misrepresented():
    result = analyze_transaction_with_ai(
        transaction=make_transaction()
    )

    assert result["confidence"] is None
    assert result["confidence_status"] == "NOT_CALIBRATED"


def test_assessment_includes_transaction_and_timestamp():
    result = analyze_transaction_with_ai(
        transaction=make_transaction()
    )

    assert result["transaction_id"] == "tx-ai-test"
    assert result["engine"] == "TrustNG-AI-Risk-Intelligence"
    assert result["version"] == "1.0"
    assert result["analyzed_at"]


def test_transaction_history_contributes_to_risk_score():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        transaction_history={
            "transaction_count": 10,
            "unique_senders": 4,
            "unique_receivers": 3,
            "window_minutes": 60,
        },
    )

    assert result["ai_risk_score"] == 25
    assert result["ai_risk_level"] == "LOW"
    assert any(
        "Recent transaction activity is elevated" in reason
        for reason in result["reasons"]
    )


def test_duplicate_risk_signal_is_not_counted_twice():
    signal = {
        "type": "UNUSUAL_PATTERN",
        "severity": "HIGH",
        "entity": "user-1",
        "message": "Unusual transaction pattern",
    }

    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        risk_signals=[signal],
        behavioral_anomalies=[signal],
    )

    assert result["ai_risk_score"] == 35
    assert result["reasons"].count(
        "Unusual transaction pattern"
    ) == 1


def test_ai_assessment_cannot_override_policy():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        risk_signals=[
            {
                "severity": "HIGH",
                "message": "High-risk signal",
            }
        ],
    )

    assert result["authority"]["can_authorize_transaction"] is False
    assert result["authority"]["can_execute_transaction"] is False
    assert result["authority"]["can_release_funds"] is False
    assert result["authority"]["can_override_policy"] is False


def test_multiple_histories_use_highest_history_score_once():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        transaction_histories=[
            {
                "transaction_count": 10,
                "unique_senders": 4,
                "unique_receivers": 3,
                "window_minutes": 60,
            },
            {
                "transaction_count": 5,
                "unique_senders": 2,
                "unique_receivers": 2,
                "window_minutes": 60,
            },
        ],
    )

    assert result["ai_risk_score"] == 25
    assert len([
        reason for reason in result["reasons"]
        if "Recent transaction activity is elevated" in reason
    ]) == 2


def test_velocity_signal_prevents_duplicate_history_scoring():
    result = analyze_transaction_with_ai(
        transaction=make_transaction(),
        risk_signals=[
            {
                "type": "TRANSACTION_VELOCITY",
                "severity": "MEDIUM",
                "entity": "user-1",
                "message": "Elevated transaction velocity",
            }
        ],
        transaction_histories=[
            {
                "transaction_count": 10,
                "unique_senders": 4,
                "unique_receivers": 3,
                "window_minutes": 60,
            }
        ],
    )

    assert result["ai_risk_score"] == 15
    assert not any(
        "Recent transaction activity is elevated" in reason
        for reason in result["reasons"]
    )
