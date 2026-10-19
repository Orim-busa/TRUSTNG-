"""Provider-neutral sandbox adapter.

This module is intentionally isolated from the live transaction executor.
It makes no network requests and cannot move real funds.
"""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any


class ProviderAdapterError(ValueError):
    """Raised when a sandbox payment request is invalid."""


def _stable_idempotency_key(transaction_id: str) -> str:
    """Create a stable, opaque key for a transaction ID."""
    digest = hashlib.sha256(
        f"trustng-sandbox-v1:{transaction_id}".encode("utf-8")
    ).hexdigest()
    return f"tn-sandbox-{digest}"


def _build_payload(transaction: Any) -> dict[str, Any]:
    """Validate a transaction and produce a deterministic payload."""
    def required_text(field: str, *, uppercase: bool = False) -> str:
        value = getattr(transaction, field, None)
        if value is None:
            raise ProviderAdapterError(f"{field} is required")
        normalized = str(value).strip()
        if not normalized or normalized.lower() == "none":
            raise ProviderAdapterError(f"{field} is required")
        return normalized.upper() if uppercase else normalized

    transaction_id = required_text("transaction_id")
    sender = required_text("sender")
    receiver = required_text("receiver")
    asset = required_text("asset", uppercase=True)
    channel = required_text("channel")
    country = required_text("country", uppercase=True)
    device_id = getattr(transaction, "device_id", None)

    if sender == receiver:
        raise ProviderAdapterError("sender and receiver must differ")

    try:
        amount = Decimal(str(getattr(transaction, "amount", "")))
    except (InvalidOperation, ValueError, TypeError):
        raise ProviderAdapterError("amount must be a valid decimal") from None

    if not amount.is_finite() or amount <= 0:
        raise ProviderAdapterError("amount must be finite and greater than zero")

    if device_id is not None:
        device_id = str(device_id).strip() or None

    return {
        "transaction_id": transaction_id,
        "sender": sender,
        "receiver": receiver,
        "asset": asset,
        "amount": format(amount.normalize(), "f"),
        "channel": channel,
        "country": country,
        "device_id": device_id,
    }


class SandboxPaymentAdapter:
    """In-memory sandbox only; never sends requests to a real provider."""

    def __init__(self, *, sandbox: bool = True) -> None:
        if sandbox is not True:
            raise ProviderAdapterError(
                "Only sandbox mode is supported by this adapter"
            )

        self.sandbox = True
        self._records: dict[str, dict[str, Any]] = {}

    def prepare(self, transaction: Any) -> dict[str, Any]:
        """Validate and prepare a request without submitting it."""
        payload = _build_payload(transaction)
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        )
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return {
            "provider": "trustng-sandbox",
            "sandbox": True,
            "idempotency_key": _stable_idempotency_key(
                payload["transaction_id"]
            ),
            "fingerprint": fingerprint,
            "request": payload,
        }

    def inspect(self, transaction: Any) -> dict[str, Any]:
        """Inspect an in-memory sandbox result without submitting."""
        prepared = self.prepare(transaction)
        existing = self._records.get(prepared["idempotency_key"])

        if existing is None:
            return {
                "status": "NOT_FOUND",
                "sandbox": True,
                "outcome_uncertain": True,
            }

        if existing["fingerprint"] != prepared["fingerprint"]:
            return {
                "status": "IDEMPOTENCY_CONFLICT",
                "sandbox": True,
                "outcome_uncertain": False,
            }

        result = dict(existing["result"])
        result["replayed"] = True
        return result

    def submit(
        self,
        transaction: Any,
        *,
        simulate_uncertain_outcome: bool = False,
    ) -> dict[str, Any]:
        """Simulate a submission, without network activity or money movement."""
        prepared = self.prepare(transaction)
        key = prepared["idempotency_key"]
        fingerprint = prepared["fingerprint"]

        existing = self._records.get(key)
        if existing is not None:
            if existing["fingerprint"] != fingerprint:
                return {
                    "provider": "trustng-sandbox",
                    "sandbox": True,
                    "transaction_id": prepared["request"]["transaction_id"],
                    "idempotency_key": key,
                    "status": "IDEMPOTENCY_CONFLICT",
                    "outcome_uncertain": False,
                    "replayed": False,
                    "message": (
                        "This transaction ID was already used with "
                        "different transaction details."
                    ),
                }

            result = dict(existing["result"])
            result["replayed"] = True
            return result

        if simulate_uncertain_outcome:
            status = "RECONCILIATION_REQUIRED"
            uncertain = True
            message = (
                "The simulated outcome is uncertain. Reconcile before "
                "considering any further action."
            )
        else:
            status = "SIMULATED_SUCCESS"
            uncertain = False
            message = (
                "Sandbox simulation only. No provider was contacted and "
                "no funds were moved."
            )

        result = {
            "provider": "trustng-sandbox",
            "sandbox": True,
            "transaction_id": prepared["request"]["transaction_id"],
            "idempotency_key": key,
            "fingerprint": fingerprint,
            "status": status,
            "outcome_uncertain": uncertain,
            "replayed": False,
            "message": message,
        }

        # Persist in this adapter instance before returning the result.
        # This is an in-memory sandbox, not durable production storage.
        self._records[key] = {
            "fingerprint": fingerprint,
            "result": dict(result),
        }
        return result
