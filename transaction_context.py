def analyze_transaction_context(transaction):
    context_signals = []

    # 1. Transaction amount
    if transaction.amount > 100000:
        context_signals.append({
            "type": "HIGH_TRANSACTION_AMOUNT",
            "value": transaction.amount,
            "severity": "MEDIUM",
            "message": "Current transaction amount is high"
        })

    # 2. Transaction channel
    if transaction.channel.upper() not in ["BANK", "MOBILE", "CARD"]:
        context_signals.append({
            "type": "UNUSUAL_CHANNEL",
            "value": transaction.channel,
            "severity": "MEDIUM",
            "message": "Transaction is using an unusual channel"
        })

    # 3. Foreign jurisdiction
    if transaction.country.upper() != "NG":
        context_signals.append({
            "type": "FOREIGN_TRANSACTION",
            "value": transaction.country,
            "severity": "MEDIUM",
            "message": "Transaction involves a foreign jurisdiction"
        })

    # 4. Missing device identity
    if transaction.device_id is None:
        context_signals.append({
            "type": "MISSING_DEVICE_ID",
            "value": None,
            "severity": "MEDIUM",
            "message": "Current transaction has no device identity"
        })

    return context_signals