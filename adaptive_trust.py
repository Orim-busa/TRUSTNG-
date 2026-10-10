def calculate_trust(transaction, beneficiary_profile):
    trust_factors = []

    trust_score = 0

    # 1. Beneficiary identity
    verification_level = beneficiary_profile.get(
        "verification_level",
        "UNKNOWN"
    )

    if verification_level == "VERIFIED":
        trust_score += 25

        trust_factors.append({
            "type": "BENEFICIARY_VERIFIED",
            "value": verification_level,
            "weight": 25,
            "message": "Beneficiary has been verified"
        })

    elif verification_level == "BASIC":
        trust_score += 10

        trust_factors.append({
            "type": "BENEFICIARY_BASIC_VERIFICATION",
            "value": verification_level,
            "weight": 10,
            "message": "Beneficiary has basic verification"
        })

    else:
        trust_factors.append({
            "type": "BENEFICIARY_UNVERIFIED",
            "value": verification_level,
            "weight": 0,
            "message": "Beneficiary has not been fully verified"
        })

    # 2. Successful transaction history
    successful_transactions = beneficiary_profile.get(
        "successful_transactions",
        0
    )

    if successful_transactions >= 100:
        trust_score += 25

        trust_factors.append({
            "type": "STRONG_TRANSACTION_HISTORY",
            "value": successful_transactions,
            "weight": 25,
            "message": "Beneficiary has a strong successful transaction history"
        })

    elif successful_transactions >= 20:
        trust_score += 15

        trust_factors.append({
            "type": "ESTABLISHED_TRANSACTION_HISTORY",
            "value": successful_transactions,
            "weight": 15,
            "message": "Beneficiary has an established successful transaction history"
        })

    else:
        trust_factors.append({
            "type": "LIMITED_TRANSACTION_HISTORY",
            "value": successful_transactions,
            "weight": 0,
            "message": "Beneficiary has limited transaction history"
        })

    # 3. Dispute history
    disputes = beneficiary_profile.get(
        "disputes",
        0
    )

    if disputes == 0:
        trust_score += 20

        trust_factors.append({
            "type": "NO_DISPUTES",
            "value": disputes,
            "weight": 20,
            "message": "No recorded disputes"
        })

    elif disputes <= 2:
        trust_score += 5

        trust_factors.append({
            "type": "LOW_DISPUTE_HISTORY",
            "value": disputes,
            "weight": 5,
            "message": "Beneficiary has a small number of disputes"
        })

    else:
        trust_factors.append({
            "type": "HIGH_DISPUTE_HISTORY",
            "value": disputes,
            "weight": 0,
            "message": "Beneficiary has a significant dispute history"
        })

    # 4. Suspicious activity
    suspicious_events = beneficiary_profile.get(
        "suspicious_events",
        0
    )

    if suspicious_events == 0:
        trust_score += 10

        trust_factors.append({
            "type": "NO_SUSPICIOUS_EVENTS",
            "value": suspicious_events,
            "weight": 10,
            "message": "No recorded suspicious events"
        })

    elif suspicious_events <= 2:
        trust_score -= 10

        trust_factors.append({
            "type": "SOME_SUSPICIOUS_EVENTS",
            "value": suspicious_events,
            "weight": -10,
            "message": "Beneficiary has recorded suspicious events"
        })

    else:
        trust_score -= 25

        trust_factors.append({
            "type": "HIGH_SUSPICIOUS_ACTIVITY",
            "value": suspicious_events,
            "weight": -25,
            "message": "Beneficiary has significant suspicious activity"
        })

    # 5. Account age
    account_age_days = beneficiary_profile.get(
        "account_age_days",
        0
    )

    if account_age_days >= 365:
        trust_score += 20

        trust_factors.append({
            "type": "ESTABLISHED_ACCOUNT",
            "value": account_age_days,
            "weight": 20,
            "message": "Beneficiary account has existed for at least one year"
        })

    elif account_age_days >= 30:
        trust_score += 10

        trust_factors.append({
            "type": "MATURE_ACCOUNT",
            "value": account_age_days,
            "weight": 10,
            "message": "Beneficiary account has an established age"
        })

    else:
        trust_factors.append({
            "type": "NEW_ACCOUNT",
            "value": account_age_days,
            "weight": 0,
            "message": "Beneficiary account is relatively new"
        })

    # 6. Security history
    failed_transactions = beneficiary_profile.get(
        "failed_transactions",
        0
    )

    account_changes = beneficiary_profile.get(
        "account_changes",
        0
    )

    device_changes = beneficiary_profile.get(
        "device_changes",
        0
    )

    chargebacks = beneficiary_profile.get(
        "chargebacks",
        0
    )

    security_penalty = 0

    # 6A. Failed transaction history
    if failed_transactions >= 10:
        security_penalty -= 15

        trust_factors.append({
            "type": "HIGH_FAILED_TRANSACTIONS",
            "value": failed_transactions,
            "weight": -15,
            "message": "Beneficiary has a high number of failed transactions"
        })

    elif failed_transactions >= 5:
        security_penalty -= 5

        trust_factors.append({
            "type": "ELEVATED_FAILED_TRANSACTIONS",
            "value": failed_transactions,
            "weight": -5,
            "message": "Beneficiary has an elevated number of failed transactions"
        })

    else:
        trust_factors.append({
            "type": "NORMAL_FAILED_TRANSACTIONS",
            "value": failed_transactions,
            "weight": 0,
            "message": "Beneficiary has no significant failed transaction pattern"
        })

    # 6B. Account change history
    if account_changes >= 5:
        security_penalty -= 15

        trust_factors.append({
            "type": "HIGH_ACCOUNT_CHANGES",
            "value": account_changes,
            "weight": -15,
            "message": "Beneficiary has a high number of account changes"
        })

    elif account_changes >= 3:
        security_penalty -= 5

        trust_factors.append({
            "type": "ELEVATED_ACCOUNT_CHANGES",
            "value": account_changes,
            "weight": -5,
            "message": "Beneficiary has multiple account changes"
        })

    else:
        trust_factors.append({
            "type": "STABLE_ACCOUNT",
            "value": account_changes,
            "weight": 0,
            "message": "Beneficiary account has no significant change pattern"
        })

    # 6C. Device change history
    if device_changes >= 5:
        security_penalty -= 15

        trust_factors.append({
            "type": "HIGH_DEVICE_CHANGES",
            "value": device_changes,
            "weight": -15,
            "message": "Beneficiary has a high number of device changes"
        })

    elif device_changes >= 3:
        security_penalty -= 5

        trust_factors.append({
            "type": "ELEVATED_DEVICE_CHANGES",
            "value": device_changes,
            "weight": -5,
            "message": "Beneficiary has multiple device changes"
        })

    else:
        trust_factors.append({
            "type": "STABLE_DEVICE_HISTORY",
            "value": device_changes,
            "weight": 0,
            "message": "Beneficiary has no significant device change pattern"
        })

    # 6D. Chargeback history
    if chargebacks >= 3:
        security_penalty -= 20

        trust_factors.append({
            "type": "HIGH_CHARGEBACK_HISTORY",
            "value": chargebacks,
            "weight": -20,
            "message": "Beneficiary has a high chargeback history"
        })

    elif chargebacks >= 1:
        security_penalty -= 5

        trust_factors.append({
            "type": "CHARGEBACK_HISTORY",
            "value": chargebacks,
            "weight": -5,
            "message": "Beneficiary has recorded chargebacks"
        })

    else:
        trust_factors.append({
            "type": "NO_CHARGEBACK_HISTORY",
            "value": chargebacks,
            "weight": 0,
            "message": "Beneficiary has no recorded chargebacks"
        })

    trust_score += security_penalty

    # 7. Relationship history
    known_senders = beneficiary_profile.get(
        "known_senders",
        0
    )

    successful_sender_relationships = beneficiary_profile.get(
        "successful_sender_relationships",
        0
    )

    if successful_sender_relationships >= 10:
        trust_score += 10

        trust_factors.append({
            "type": "STRONG_SENDER_RELATIONSHIPS",
            "value": successful_sender_relationships,
            "weight": 10,
            "message": "Beneficiary has many successful sender relationships"
        })

    elif successful_sender_relationships >= 3:
        trust_score += 5

        trust_factors.append({
            "type": "ESTABLISHED_SENDER_RELATIONSHIPS",
            "value": successful_sender_relationships,
            "weight": 5,
            "message": "Beneficiary has established successful sender relationships"
        })

    else:
        trust_factors.append({
            "type": "LIMITED_SENDER_RELATIONSHIPS",
            "value": successful_sender_relationships,
            "weight": 0,
            "message": "Beneficiary has limited successful sender relationships"
        })

    if known_senders >= 20:
        trust_score += 5

        trust_factors.append({
            "type": "BROAD_SENDER_NETWORK",
            "value": known_senders,
            "weight": 5,
            "message": "Beneficiary has a broad known sender network"
        })

    elif known_senders == 0:
        trust_factors.append({
            "type": "NO_KNOWN_SENDERS",
            "value": known_senders,
            "weight": 0,
            "message": "Beneficiary has no recorded known senders"
        })

    else:
        trust_factors.append({
            "type": "LIMITED_KNOWN_SENDERS",
            "value": known_senders,
            "weight": 0,
            "message": "Beneficiary has a limited known sender network"
        })

    # 8. Current transaction vs beneficiary behaviour
    average_amount = beneficiary_profile.get(
        "average_transaction_amount",
        0
    )

    usual_channels = [
        channel.upper()
        for channel in beneficiary_profile.get(
            "usual_channels",
            []
        )
    ]

    usual_countries = [
        country.upper()
        for country in beneficiary_profile.get(
            "usual_countries",
            []
        )
    ]

    if average_amount > 0 and transaction.amount >= average_amount * 2:
        trust_score -= 10

        trust_factors.append({
            "type": "HIGH_AMOUNT_DEVIATION",
            "value": transaction.amount,
            "weight": -10,
            "message": "Transaction amount is unusually high for this beneficiary"
        })

    if usual_channels and transaction.channel.upper() not in usual_channels:
        trust_score -= 10

        trust_factors.append({
            "type": "UNUSUAL_BENEFICIARY_CHANNEL",
            "value": transaction.channel,
            "weight": -10,
            "message": "Transaction uses an unusual channel for this beneficiary"
        })

    if usual_countries and transaction.country.upper() not in usual_countries:
        trust_score -= 10

        trust_factors.append({
            "type": "UNUSUAL_BENEFICIARY_COUNTRY",
            "value": transaction.country,
            "weight": -10,
            "message": "Transaction uses an unusual country for this beneficiary"
        })

    # Prevent the score from going below zero
    if trust_score < 0:
        trust_score = 0

    # Determine trust level
    if trust_score >= 80:
        trust_level = "HIGH"

    elif trust_score >= 50:
        trust_level = "MEDIUM"

    else:
        trust_level = "LOW"

    return {
        "beneficiary": transaction.receiver,
        "trust_score": trust_score,
        "trust_level": trust_level,
        "factors": trust_factors
    }