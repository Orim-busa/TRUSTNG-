from datetime import datetime
import uuid


# ============================================================
# TRUST GRAPH
# ============================================================

NODES = {}

RELATIONSHIPS = []


# ============================================================
# TRANSACTION HISTORY
# ============================================================

TRANSACTION_HISTORY = {}


# ============================================================
# ENTITY REGISTRATION
# ============================================================

def register_entity(
    entity_id,
    entity_type,
    attributes=None
):
    """
    Register an entity in the Trust Graph.
    """

    if not entity_id:
        raise ValueError("Entity ID is required")

    if not entity_type:
        raise ValueError("Entity type is required")

    entity_type = entity_type.upper()

    if entity_id in NODES:
        return NODES[entity_id]

    node = {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "attributes": attributes or {},
        "created_at": datetime.utcnow().isoformat()
    }

    NODES[entity_id] = node

    return node


# ============================================================
# ENTITY LOOKUP
# ============================================================

def get_entity(entity_id):
    """
    Retrieve an entity from the Trust Graph.
    """

    return NODES.get(entity_id)


# ============================================================
# RELATIONSHIP DUPLICATE CHECK
# ============================================================

def relationship_exists(
    source_id,
    relationship_type,
    target_id,
    transaction_id=None
):
    """
    Check whether an equivalent relationship already exists.

    Transaction-specific relationships are compared using the
    transaction_id stored in their attributes.
    """

    relationship_type = relationship_type.upper()

    for relationship in RELATIONSHIPS:

        if (
            relationship["source"] != source_id
            or relationship["target"] != target_id
            or relationship["relationship_type"]
            != relationship_type
        ):
            continue

        if transaction_id is None:
            return True

        attributes = relationship.get("attributes", {})

        if attributes.get("transaction_id") == transaction_id:
            return True

    return False


# ============================================================
# CREATE RELATIONSHIP
# ============================================================

def add_relationship(
    source_id,
    relationship_type,
    target_id,
    attributes=None
):
    """
    Create a relationship between two entities.
    """

    if source_id not in NODES:
        raise ValueError(
            f"Source entity '{source_id}' does not exist"
        )

    if target_id not in NODES:
        raise ValueError(
            f"Target entity '{target_id}' does not exist"
        )

    if not relationship_type:
        raise ValueError(
            "Relationship type is required"
        )

    relationship_type = relationship_type.upper()
    attributes = attributes or {}

    transaction_id = attributes.get("transaction_id")

    if relationship_exists(
        source_id=source_id,
        relationship_type=relationship_type,
        target_id=target_id,
        transaction_id=transaction_id
    ):
        for relationship in RELATIONSHIPS:

            if (
                relationship["source"] == source_id
                and relationship["target"] == target_id
                and relationship["relationship_type"]
                == relationship_type
            ):

                if transaction_id is None:
                    return relationship

                if (
                    relationship.get("attributes", {})
                    .get("transaction_id")
                    == transaction_id
                ):
                    return relationship

    relationship = {
        "relationship_id": str(uuid.uuid4()),
        "source": source_id,
        "relationship_type": relationship_type,
        "target": target_id,
        "attributes": attributes,
        "created_at": datetime.utcnow().isoformat()
    }

    RELATIONSHIPS.append(relationship)

    return relationship


# ============================================================
# FIND RELATED ENTITIES
# ============================================================

def get_related_entities(
    entity_id,
    relationship_type=None
):
    """
    Find entities connected to an entity.
    """

    if entity_id not in NODES:
        return []

    results = []

    for relationship in RELATIONSHIPS:

        if relationship["source"] == entity_id:

            if (
                relationship_type is None
                or relationship["relationship_type"]
                == relationship_type.upper()
            ):
                target = NODES.get(
                    relationship["target"]
                )

                if target:
                    results.append(target)

        elif relationship["target"] == entity_id:

            if (
                relationship_type is None
                or relationship["relationship_type"]
                == relationship_type.upper()
            ):
                source = NODES.get(
                    relationship["source"]
                )

                if source:
                    results.append(source)

    return results


# ============================================================
# RECORD SECURITY EVENT
# ============================================================

def record_security_event(
    entity_id,
    event_type,
    severity,
    details=None
):
    """
    Attach a security event to an entity.
    """

    if entity_id not in NODES:
        raise ValueError(
            f"Entity '{entity_id}' does not exist"
        )

    event_id = f"security_event_{uuid.uuid4()}"

    event = register_entity(
        entity_id=event_id,
        entity_type="SECURITY_EVENT",
        attributes={
            "event_type": event_type,
            "severity": severity,
            "details": details or {}
        }
    )

    relationship = add_relationship(
        source_id=entity_id,
        relationship_type="FLAGGED_FOR",
        target_id=event_id
    )

    return {
        "event": event,
        "relationship": relationship
    }


# ============================================================
# GET ENTITY HISTORY
# ============================================================

def get_entity_history(entity_id):
    """
    Return all relationships involving an entity.
    """

    if entity_id not in NODES:
        return []

    history = []

    for relationship in RELATIONSHIPS:

        if (
            relationship["source"] == entity_id
            or relationship["target"] == entity_id
        ):
            history.append(relationship)

    return history


# ============================================================
# GET TRANSACTION HISTORY
# ============================================================

def get_transaction_history(transaction_id=None):
    """
    Retrieve transaction history.

    If transaction_id is supplied, return that transaction.
    Otherwise return all recorded transactions.
    """

    if transaction_id is not None:
        return TRANSACTION_HISTORY.get(
            transaction_id
        )

    return dict(TRANSACTION_HISTORY)


# ============================================================
# TRANSACTION INGESTION
# ============================================================

def record_transaction(transaction):
    """
    Add a TrustNG transaction and its known relationships
    to the Trust Graph.

    This does not move money.
    """

    transaction_id = transaction.transaction_id

    # --------------------------------------------------------
    # Duplicate transaction protection
    # --------------------------------------------------------

    if transaction_id in TRANSACTION_HISTORY:

        return {
            "transaction_id": transaction_id,
            "sender": transaction.sender,
            "beneficiary": transaction.receiver,
            "device": transaction.device_id,
            "status": "ALREADY_RECORDED"
        }

    # --------------------------------------------------------
    # Store transaction history
    # --------------------------------------------------------

    TRANSACTION_HISTORY[transaction_id] = {
        "transaction_id": transaction_id,
        "sender": transaction.sender,
        "receiver": transaction.receiver,
        "asset": transaction.asset,
        "amount": transaction.amount,
        "channel": transaction.channel,
        "country": transaction.country,
        "device_id": transaction.device_id,
        "recorded_at": datetime.utcnow().isoformat()
    }

    # --------------------------------------------------------
    # Register sender
    # --------------------------------------------------------

    register_entity(
        entity_id=transaction.sender,
        entity_type="USER"
    )

    # --------------------------------------------------------
    # Register beneficiary
    # --------------------------------------------------------

    register_entity(
        entity_id=transaction.receiver,
        entity_type="BENEFICIARY"
    )

    # --------------------------------------------------------
    # Register transaction
    # --------------------------------------------------------

    register_entity(
        entity_id=transaction_id,
        entity_type="TRANSACTION",
        attributes={
            "asset": transaction.asset,
            "amount": transaction.amount,
            "channel": transaction.channel,
            "country": transaction.country,
            "recorded_at": TRANSACTION_HISTORY[
                transaction_id
            ]["recorded_at"]
        }
    )

    # --------------------------------------------------------
    # Sender -> Beneficiary
    # --------------------------------------------------------

    add_relationship(
        source_id=transaction.sender,
        relationship_type="SENDS_TO",
        target_id=transaction.receiver,
        attributes={
            "transaction_id": transaction_id,
            "asset": transaction.asset,
            "amount": transaction.amount
        }
    )

    # --------------------------------------------------------
    # Transaction -> Sender
    # --------------------------------------------------------

    add_relationship(
        source_id=transaction_id,
        relationship_type="INITIATED_BY",
        target_id=transaction.sender,
        attributes={
            "transaction_id": transaction_id
        }
    )

    # --------------------------------------------------------
    # Transaction -> Beneficiary
    # --------------------------------------------------------

    add_relationship(
        source_id=transaction_id,
        relationship_type="SENDS_TO",
        target_id=transaction.receiver,
        attributes={
            "transaction_id": transaction_id
        }
    )

    # --------------------------------------------------------
    # Device relationships
    # --------------------------------------------------------

    if transaction.device_id:

        register_entity(
            entity_id=transaction.device_id,
            entity_type="DEVICE"
        )

        add_relationship(
            source_id=transaction.sender,
            relationship_type="USES",
            target_id=transaction.device_id,
            attributes={
                "transaction_id": transaction_id
            }
        )

        add_relationship(
            source_id=transaction_id,
            relationship_type="EXECUTED_ON",
            target_id=transaction.device_id,
            attributes={
                "transaction_id": transaction_id
            }
        )

    return {
        "transaction_id": transaction_id,
        "sender": transaction.sender,
        "beneficiary": transaction.receiver,
        "device": transaction.device_id,
        "status": "RECORDED"
    }


# ============================================================
# RELATIONSHIP RISK ANALYSIS
# ============================================================

def analyze_relationship_risk(entity_id):
    """
    Analyze the network surrounding an entity.

    This function produces relationship-based risk signals.
    It does not make the final transaction decision.
    """

    signals = []

    if entity_id not in NODES:
        return signals

    # --------------------------------------------------------
    # SHARED DEVICE ANALYSIS
    # --------------------------------------------------------

    device_ids = set()

    for relationship in RELATIONSHIPS:

        if (
            relationship["relationship_type"] == "USES"
            and relationship["target"] in NODES
            and NODES[
                relationship["target"]
            ]["entity_type"] == "DEVICE"
        ):
            if relationship["source"] == entity_id:
                device_ids.add(
                    relationship["target"]
                )

    for device_id in device_ids:

        device_users = set()

        for relationship in RELATIONSHIPS:

            if (
                relationship["relationship_type"]
                == "USES"
                and relationship["target"]
                == device_id
            ):
                device_users.add(
                    relationship["source"]
                )

        if len(device_users) >= 3:

            signals.append({
                "type": "SHARED_DEVICE_NETWORK",
                "severity": "HIGH",
                "entity": device_id,
                "value": len(device_users),
                "message": (
                    "Device is associated with multiple users"
                )
            })

    # --------------------------------------------------------
    # BENEFICIARY NETWORK ANALYSIS
    # --------------------------------------------------------

    beneficiary_ids = set()

    for relationship in RELATIONSHIPS:

        if (
            relationship["source"] == entity_id
            and relationship["relationship_type"]
            == "SENDS_TO"
            and relationship["target"] in NODES
            and NODES[
                relationship["target"]
            ]["entity_type"] == "BENEFICIARY"
        ):
            beneficiary_ids.add(
                relationship["target"]
            )

    for beneficiary_id in beneficiary_ids:

        unique_senders = set()

        for relationship in RELATIONSHIPS:

            if (
                relationship["target"] == beneficiary_id
                and relationship["relationship_type"]
                == "SENDS_TO"
            ):
                source_id = relationship["source"]

                if source_id in NODES:
                    source_type = NODES[
                        source_id
                    ]["entity_type"]

                    if source_type == "USER":
                        unique_senders.add(
                            source_id
                        )

        if len(unique_senders) >= 5:

            signals.append({
                "type": "LARGE_BENEFICIARY_NETWORK",
                "severity": "HIGH",
                "entity": beneficiary_id,
                "value": len(unique_senders),
                "message": (
                    "Beneficiary receives transactions "
                    "from many distinct senders"
                )
            })

    # --------------------------------------------------------
    # SECURITY EVENT ANALYSIS
    # --------------------------------------------------------

    security_event_ids = set()

    for relationship in RELATIONSHIPS:

        if (
            relationship["source"] == entity_id
            and relationship["relationship_type"]
            == "FLAGGED_FOR"
        ):
            security_event_ids.add(
                relationship["target"]
            )

    if security_event_ids:

        signals.append({
            "type": "SECURITY_EVENT_ASSOCIATED",
            "severity": "HIGH",
            "entity": entity_id,
            "value": len(security_event_ids),
            "message": (
                "Entity is associated with security events"
            )
        })

    return signals


# ============================================================
# TRANSACTION HISTORY ANALYSIS
# ============================================================

def analyze_transaction_history(
    entity_id,
    window_minutes=60
):
    """
    Analyze recent transaction activity involving an entity.

    This is an intelligence layer only.
    It does not make the final transaction decision.
    """

    now = datetime.utcnow()

    recent_transactions = []

    for transaction in TRANSACTION_HISTORY.values():

        timestamp = transaction.get("recorded_at")

        if not timestamp:
            continue

        try:
            recorded_at = datetime.fromisoformat(
                timestamp
            )
        except ValueError:
            continue

        age_seconds = (
            now - recorded_at
        ).total_seconds()

        if age_seconds < 0:
            continue

        if age_seconds <= window_minutes * 60:

            if (
                transaction.get("sender") == entity_id
                or transaction.get("receiver") == entity_id
            ):
                recent_transactions.append(
                    transaction
                )

    unique_senders = {
        transaction["sender"]
        for transaction in recent_transactions
        if transaction.get("sender")
    }

    unique_receivers = {
        transaction["receiver"]
        for transaction in recent_transactions
        if transaction.get("receiver")
    }

    total_amount = sum(
        transaction.get("amount", 0)
        for transaction in recent_transactions
    )

    return {
        "entity_id": entity_id,
        "window_minutes": window_minutes,
        "transaction_count": len(
            recent_transactions
        ),
        "unique_senders": len(
            unique_senders
        ),
        "unique_receivers": len(
            unique_receivers
        ),
        "total_amount": total_amount,
        "transactions": recent_transactions
    }


# ============================================================
# TRANSACTION VELOCITY ANALYSIS
# ============================================================

VELOCITY_THRESHOLDS = {
    "MEDIUM": 5,
    "HIGH": 10
}


def analyze_transaction_velocity(
    entity_id,
    window_minutes=60
):
    """
    Detect unusually high transaction activity
    involving an entity within a time window.

    This produces intelligence signals only.
    It does not make the final transaction decision.
    """

    history = analyze_transaction_history(
        entity_id=entity_id,
        window_minutes=window_minutes
    )

    transaction_count = history["transaction_count"]

    if transaction_count >= VELOCITY_THRESHOLDS["HIGH"]:

        return {
            "type": "HIGH_TRANSACTION_VELOCITY",
            "severity": "HIGH",
            "entity": entity_id,
            "value": transaction_count,
            "window_minutes": window_minutes,
            "message": (
                "Entity has unusually high transaction "
                "activity within a short time window"
            )
        }

    if transaction_count >= VELOCITY_THRESHOLDS["MEDIUM"]:

        return {
            "type": "ELEVATED_TRANSACTION_VELOCITY",
            "severity": "MEDIUM",
            "entity": entity_id,
            "value": transaction_count,
            "window_minutes": window_minutes,
            "message": (
                "Entity has elevated transaction "
                "activity within a short time window"
            )
        }

    return None
