def analyze_transaction(transaction):
    signals = []

    if transaction.amount > 100000:
        signals.append({
            "type": "LARGE_AMOUNT",
            "severity": "MEDIUM",
            "message": "Transaction amount is unusually large"
        })

    if transaction.amount > 1000000:
        signals.append({
            "type": "VERY_LARGE_AMOUNT",
            "severity": "HIGH",
            "message": "Transaction amount exceeds high-risk threshold"
        })

    if transaction.asset.upper() == "BTC":
        signals.append({
            "type": "CRYPTO_ASSET",
            "severity": "MEDIUM",
            "message": "Transaction involves a crypto asset"
        })

    if transaction.device_id is None:
        signals.append({
            "type": "MISSING_DEVICE_ID",
            "severity": "LOW",
            "message": "Device identity was not provided"
        })

    if transaction.country.upper() != "NG":
        signals.append({
            "type": "CROSS_BORDER",
            "severity": "MEDIUM",
            "message": "Transaction involves a foreign jurisdiction"
        })

    return signals