POLICY_ID = "NG-TRANSFER-001"
POLICY_VERSION = "1.0"


def evaluate_transaction(transaction, risk_signals, trust_result=None):

    reasons = [
        signal["message"]
        for signal in risk_signals
    ]

    severities = [
        signal["severity"]
        for signal in risk_signals
    ]

    trust_level = None

    if trust_result:
        trust_level = trust_result.get("trust_level")

    if "HIGH" in severities:
        return {
            "decision": "RESTRICT",
            "risk_level": "HIGH",
            "reasons": reasons,
            "policy": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "action": "RESTRICT_TRANSACTION",
            "restrictions": [
                "SEND",
                "WITHDRAW"
            ]
        }

    if trust_level == "LOW":
        reasons.append(
            "Beneficiary trust level is LOW"
        )

        return {
            "decision": "REVIEW",
            "risk_level": "MEDIUM",
            "reasons": reasons,
            "policy": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "action": "HOLD_FOR_REVIEW",
            "restrictions": []
        }

    if "MEDIUM" in severities:
        return {
            "decision": "REVIEW",
            "risk_level": "MEDIUM",
            "reasons": reasons,
            "policy": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "action": "HOLD_FOR_REVIEW",
            "restrictions": []
        }

    return {
        "decision": "ALLOW",
        "risk_level": "LOW",
        "reasons": [],
        "policy": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "action": "ALLOW_TRANSACTION",
        "restrictions": []
    }