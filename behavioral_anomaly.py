def analyze_behavioral_anomaly(transaction, beneficiary_profile):
    """
    Detect whether the current transaction is significantly
    different from the beneficiary's established behavior.

    This layer only produces risk signals.
    It does not make the final transaction decision.
    """

    signals = []

    average_amount = beneficiary_profile.get(
        "average_transaction_amount",
        0
    )

    usual_channels = beneficiary_profile.get(
        "usual_channels",
        []
    )

    usual_countries = beneficiary_profile.get(
        "usual_countries",
        []
    )

    # ---------------------------------------------------------
    # 1. Transaction amount anomaly
    # ---------------------------------------------------------

    if average_amount > 0:

        if transaction.amount >= average_amount * 5:
            signals.append({
                "type": "EXTREME_AMOUNT_ANOMALY",
                "severity": "HIGH",
                "value": transaction.amount,
                "expected_average": average_amount,
                "message": (
                    "Transaction amount is significantly above "
                    "the beneficiary's normal transaction pattern"
                )
            })

        elif transaction.amount >= average_amount * 2:
            signals.append({
                "type": "AMOUNT_ANOMALY",
                "severity": "MEDIUM",
                "value": transaction.amount,
                "expected_average": average_amount,
                "message": (
                    "Transaction amount is above "
                    "the beneficiary's normal transaction pattern"
                )
            })

    # ---------------------------------------------------------
    # 2. Channel anomaly
    # ---------------------------------------------------------

    if usual_channels:

        normal_channels = [
            channel.upper()
            for channel in usual_channels
        ]

        if transaction.channel.upper() not in normal_channels:
            signals.append({
                "type": "CHANNEL_ANOMALY",
                "severity": "MEDIUM",
                "value": transaction.channel,
                "expected_channels": usual_channels,
                "message": (
                    "Transaction channel differs from "
                    "the beneficiary's usual channels"
                )
            })

    # ---------------------------------------------------------
    # 3. Country anomaly
    # ---------------------------------------------------------

    if usual_countries:

        normal_countries = [
            country.upper()
            for country in usual_countries
        ]

        if transaction.country.upper() not in normal_countries:
            signals.append({
                "type": "COUNTRY_ANOMALY",
                "severity": "MEDIUM",
                "value": transaction.country,
                "expected_countries": usual_countries,
                "message": (
                    "Transaction country differs from "
                    "the beneficiary's usual countries"
                )
            })

    return signals